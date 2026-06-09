from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import curses
except ImportError:  # pragma: no cover - Fedora provides curses; Windows usually does not.
    curses = None  # type: ignore[assignment]


APP_NAME = "fedora-postinstall-checklist"
STATE_DIR = Path.home() / ".local" / "state" / APP_NAME
STATE_PATH = STATE_DIR / "state.json"
LOG_PATH = STATE_DIR / "install.log"


@dataclass
class ChecklistItem:
    id: str
    name: str
    check: str
    install: str
    group: str
    notes: str = ""
    selected: bool = True
    depends_on: list[str] = field(default_factory=list)
    installed: bool = False
    manual_done: bool = False
    last_error: str = ""

    @property
    def done(self) -> bool:
        return self.installed or self.manual_done

    @property
    def wanted_missing(self) -> bool:
        return self.selected and not self.done


@dataclass
class PersistedState:
    manual_done: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)


@dataclass
class AppState:
    items: list[ChecklistItem]
    persisted: PersistedState
    selected_index: int = 0
    offset: int = 0
    message: str = "Press a to install selected missing items. Press ? for keys."


def package_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


def normalize_id(name: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in name.lower()).strip("-")


def load_config(path: Path) -> list[ChecklistItem]:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    items: list[ChecklistItem] = []
    seen: set[str] = set()
    for group in raw.get("groups", []):
        group_name = group["name"]
        for item in group.get("items", []):
            item_id = item.get("id") or normalize_id(item["name"])
            if item_id in seen:
                raise ValueError(f"Duplicate checklist id: {item_id}")
            seen.add(item_id)
            items.append(
                ChecklistItem(
                    id=item_id,
                    name=item["name"],
                    check=item["check"],
                    install=item["install"],
                    notes=item.get("notes", ""),
                    selected=item.get("selected", True),
                    depends_on=item.get("depends_on", []),
                    group=group_name,
                )
            )
    if not items:
        raise ValueError(f"No checklist items found in {path}")
    validate_dependencies(items)
    return items


def validate_dependencies(items: list[ChecklistItem]) -> None:
    ids = {item.id for item in items}
    missing = sorted({dep for item in items for dep in item.depends_on if dep not in ids})
    if missing:
        raise ValueError(f"Missing dependency id(s): {', '.join(missing)}")


def load_state() -> PersistedState:
    if not STATE_PATH.exists():
        return PersistedState()
    try:
        with STATE_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return PersistedState(
            manual_done=set(data.get("manual_done", [])),
            skipped=set(data.get("skipped", [])),
        )
    except (OSError, json.JSONDecodeError):
        return PersistedState()


def save_state(state: PersistedState) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "manual_done": sorted(state.manual_done),
                "skipped": sorted(state.skipped),
            },
            file,
            indent=2,
        )


def log_event(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message}\n")


def run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def scan_items(items: list[ChecklistItem], persisted: PersistedState) -> None:
    for item in items:
        result = run_shell(item.check)
        item.installed = result.returncode == 0
        item.manual_done = item.id in persisted.manual_done
        item.selected = item.id not in persisted.skipped
        item.last_error = "" if item.installed else (result.stderr or result.stdout).strip()


def install_item(item: ChecklistItem) -> tuple[bool, str]:
    log_event(f"START {item.id}: {item.install}")
    result = run_shell(item.install)
    if result.stdout.strip():
        log_event(f"STDOUT {item.id}: {result.stdout.strip()}")
    if result.stderr.strip():
        log_event(f"STDERR {item.id}: {result.stderr.strip()}")

    if result.returncode == 0:
        check_result = run_shell(item.check)
        item.installed = check_result.returncode == 0
        if item.installed:
            log_event(f"OK {item.id}")
            return True, f"Installed {item.name}."
        log_event(f"CHECK_FAILED {item.id}")
        return False, f"Install finished, but {item.name} was not detected."

    output = (result.stderr or result.stdout).strip()
    log_event(f"FAILED {item.id}: exit {result.returncode}")
    return False, output or f"Install command failed for {item.name}."


def ordered_items(items: list[ChecklistItem]) -> list[ChecklistItem]:
    by_id = {item.id: item for item in items}
    visited: set[str] = set()
    visiting: set[str] = set()
    ordered: list[ChecklistItem] = []

    def visit(item: ChecklistItem) -> None:
        if item.id in visited:
            return
        if item.id in visiting:
            raise ValueError(f"Dependency cycle includes {item.id}")
        visiting.add(item.id)
        for dep in item.depends_on:
            visit(by_id[dep])
        visiting.remove(item.id)
        visited.add(item.id)
        ordered.append(item)

    for item in items:
        visit(item)
    return ordered


def selected_missing_items(items: list[ChecklistItem]) -> list[ChecklistItem]:
    return [item for item in ordered_items(items) if item.wanted_missing]


def format_install_command(command: str) -> str:
    return command.replace("sudo ", "")


def print_plan(items: list[ChecklistItem]) -> int:
    missing = selected_missing_items(items)
    if not missing:
        print("Nothing selected is missing.")
        return 0
    print("Install plan:")
    for index, item in enumerate(missing, start=1):
        print(f"{index:2}. {item.name} [{item.group}]")
        print(f"    {format_install_command(item.install)}")
    return 0


def print_summary(items: list[ChecklistItem]) -> int:
    width = max(len(item.name) for item in items)
    missing = 0
    current_group = ""
    for item in items:
        if item.group != current_group:
            current_group = item.group
            print(f"\n{current_group}")
        if item.done:
            mark = "ok"
        elif not item.selected:
            mark = "skipped"
        else:
            mark = "missing"
            missing += 1
        print(f"  {mark:7} {item.name:<{width}}  {format_install_command(item.install)}")
    print(f"\n{len(items) - missing}/{len(items)} complete or skipped")
    return 0 if missing == 0 else 1


def install_missing(items: list[ChecklistItem], assume_yes: bool = False) -> int:
    missing = selected_missing_items(items)
    if not missing:
        print("Nothing selected is missing.")
        return 0

    print_plan(items)
    if not assume_yes:
        answer = input("\nInstall these items? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled.")
            return 1

    for item in missing:
        print(f"\nInstalling {item.name}: {format_install_command(item.install)}")
        ok, message = install_item(item)
        print(message)
        if not ok:
            print(f"Stopped. See log: {LOG_PATH}")
            return 1
    return 0


def draw_help(stdscr: Any) -> None:
    stdscr.erase()
    lines = [
        "Fedora Post-Install Checklist keys",
        "",
        "Up/Down or k/j  Move",
        "Space          Include or skip selected item",
        "m              Mark selected item done manually",
        "Enter          Install selected item",
        "a              Install all selected missing items in order",
        "r              Rescan",
        "?              Show this help",
        "q              Save and quit",
        "",
        "Press any key to return.",
    ]
    height, width = stdscr.getmaxyx()
    for row, line in enumerate(lines[:height]):
        attr = curses.A_BOLD if row == 0 else curses.A_NORMAL
        stdscr.addnstr(row, 0, line, width - 1, attr)
    stdscr.refresh()
    stdscr.getch()


def draw(stdscr: Any, state: AppState) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    title = "Fedora Post-Install Installer"
    complete = sum(1 for item in state.items if item.done)
    wanted_missing = sum(1 for item in state.items if item.wanted_missing)
    header = f"{title}  {complete}/{len(state.items)} done  {wanted_missing} selected missing"
    stdscr.addnstr(0, 0, header, width - 1, curses.A_BOLD)
    stdscr.addnstr(1, 0, "Keys: Up/Down move  Space include/skip  m manual  Enter install  a install all  ? help  q quit", width - 1)

    list_top = 3
    list_bottom = max(list_top, height - 5)
    visible_rows = list_bottom - list_top
    if state.selected_index < state.offset:
        state.offset = state.selected_index
    if state.selected_index >= state.offset + visible_rows:
        state.offset = state.selected_index - visible_rows + 1

    row = list_top
    current_group = ""
    for index, item in enumerate(state.items[state.offset : state.offset + visible_rows]):
        real_index = index + state.offset
        if item.group != current_group:
            current_group = item.group
            if row < list_bottom:
                stdscr.addnstr(row, 0, current_group, width - 1, curses.A_UNDERLINE)
                row += 1
        if row >= list_bottom:
            break
        if item.done:
            marker = "[x]"
            status = "installed" if item.installed else "manual"
        elif not item.selected:
            marker = "[-]"
            status = "skipped"
        else:
            marker = "[ ]"
            status = "missing"
        line = f"{marker} {item.name} ({status})"
        attr = curses.A_REVERSE if real_index == state.selected_index else curses.A_NORMAL
        stdscr.addnstr(row, 0, line, width - 1, attr)
        row += 1

    selected = state.items[state.selected_index]
    detail_y = height - 3
    deps = f" Depends on: {', '.join(selected.depends_on)}" if selected.depends_on else ""
    stdscr.addnstr(detail_y, 0, f"Install: {selected.install}", width - 1)
    stdscr.addnstr(detail_y + 1, 0, f"{selected.notes}{deps}", width - 1)
    stdscr.addnstr(height - 1, 0, state.message, width - 1, curses.A_DIM)
    stdscr.refresh()


def install_from_tui(stdscr: Any, state: AppState, item: ChecklistItem) -> bool:
    if item.done:
        state.message = f"{item.name} is already complete."
        return True
    if not item.selected:
        state.message = f"{item.name} is skipped. Press Space to include it first."
        return True
    state.message = f"Installing {item.name}..."
    draw(stdscr, state)
    ok, message = install_item(item)
    state.message = message if len(message) < 240 else message[:237] + "..."
    return ok


def tui(stdscr: Any, items: list[ChecklistItem], persisted: PersistedState) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    state = AppState(items=items, persisted=persisted)
    scan_items(state.items, state.persisted)

    while True:
        draw(stdscr, state)
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            save_state(state.persisted)
            return
        if key in (curses.KEY_DOWN, ord("j")):
            state.selected_index = min(len(state.items) - 1, state.selected_index + 1)
        elif key in (curses.KEY_UP, ord("k")):
            state.selected_index = max(0, state.selected_index - 1)
        elif key == ord("?"):
            draw_help(stdscr)
        elif key == ord(" "):
            item = state.items[state.selected_index]
            if item.id in state.persisted.skipped:
                state.persisted.skipped.remove(item.id)
                item.selected = True
                state.message = f"Included {item.name} in install runs."
            else:
                state.persisted.skipped.add(item.id)
                item.selected = False
                state.message = f"Skipped {item.name}."
            save_state(state.persisted)
        elif key in (ord("m"), ord("M")):
            item = state.items[state.selected_index]
            if item.id in state.persisted.manual_done:
                state.persisted.manual_done.remove(item.id)
                item.manual_done = False
                state.message = f"Cleared manual mark for {item.name}."
            else:
                state.persisted.manual_done.add(item.id)
                item.manual_done = True
                state.message = f"Marked {item.name} done manually."
            save_state(state.persisted)
        elif key in (ord("r"), ord("R")):
            scan_items(state.items, state.persisted)
            state.message = "Scan complete."
        elif key in (curses.KEY_ENTER, 10, 13):
            install_from_tui(stdscr, state, state.items[state.selected_index])
            scan_items(state.items, state.persisted)
        elif key in (ord("a"), ord("A")):
            for item in selected_missing_items(state.items):
                ok = install_from_tui(stdscr, state, item)
                scan_items(state.items, state.persisted)
                if not ok:
                    state.message = f"Stopped at {item.name}. See {LOG_PATH}."
                    break
            else:
                state.message = "Install run complete."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Fedora post-install checklist and installer")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=package_path("checklist.json"),
        help="Path to checklist JSON file.",
    )
    parser.add_argument("--check", action="store_true", help="Print checklist status without launching the TUI.")
    parser.add_argument("--plan", action="store_true", help="Print selected missing items in install order.")
    parser.add_argument("--install-missing", action="store_true", help="Install selected missing items without launching the TUI.")
    parser.add_argument("-y", "--yes", action="store_true", help="Do not prompt before --install-missing.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.version:
        from fedora_checklist import __version__

        print(__version__)
        return 0

    items = load_config(args.config)
    persisted = load_state()
    scan_items(items, persisted)

    if args.plan:
        return print_plan(items)

    if args.install_missing:
        result = install_missing(items, assume_yes=args.yes)
        scan_items(items, persisted)
        if result != 0:
            return result
        return print_summary(items)

    if args.check:
        return print_summary(items)

    if os.name == "nt":
        print("The interactive TUI needs a Unix-like terminal. Use --check or --plan on Windows, or run this on Fedora.")
        return print_summary(items)
    if curses is None:
        print("Python curses support is required for the interactive TUI.")
        return 1
    if shutil.which("sudo") is None:
        print("sudo is required for install commands.")
        return 1

    curses.wrapper(tui, items, persisted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
