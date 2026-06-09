from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import curses
except ImportError:  # pragma: no cover - Fedora provides curses; Windows usually does not.
    curses = None  # type: ignore[assignment]


APP_NAME = "fedora-postinstall-checklist"
STATE_PATH = Path.home() / ".local" / "state" / APP_NAME / "state.json"


@dataclass
class ChecklistItem:
    name: str
    check: str
    install: str
    group: str
    notes: str = ""
    installed: bool = False
    manual_done: bool = False
    last_error: str = ""

    @property
    def done(self) -> bool:
        return self.installed or self.manual_done


@dataclass
class AppState:
    items: list[ChecklistItem]
    selected: int = 0
    offset: int = 0
    message: str = "Press r to scan, Enter to install, Space to mark done, q to quit."
    installing: bool = False
    manual_done: set[str] = field(default_factory=set)


def package_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


def load_config(path: Path) -> list[ChecklistItem]:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    items: list[ChecklistItem] = []
    for group in raw.get("groups", []):
        group_name = group["name"]
        for item in group.get("items", []):
            items.append(
                ChecklistItem(
                    name=item["name"],
                    check=item["check"],
                    install=item["install"],
                    notes=item.get("notes", ""),
                    group=group_name,
                )
            )
    if not items:
        raise ValueError(f"No checklist items found in {path}")
    return items


def load_state() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        with STATE_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return set(data.get("manual_done", []))
    except (OSError, json.JSONDecodeError):
        return set()


def save_state(manual_done: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("w", encoding="utf-8") as file:
        json.dump({"manual_done": sorted(manual_done)}, file, indent=2)


def run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def scan_items(items: list[ChecklistItem], manual_done: set[str]) -> None:
    for item in items:
        result = run_shell(item.check)
        item.installed = result.returncode == 0
        item.manual_done = item.name in manual_done
        item.last_error = "" if item.installed else (result.stderr or result.stdout).strip()


def install_item(item: ChecklistItem) -> tuple[bool, str]:
    result = run_shell(item.install)
    if result.returncode == 0:
        check_result = run_shell(item.check)
        item.installed = check_result.returncode == 0
        if item.installed:
            return True, f"Installed {item.name}."
        return False, f"Install finished, but {item.name} was not detected."
    output = (result.stderr or result.stdout).strip()
    return False, output or f"Install command failed for {item.name}."


def format_install_command(command: str) -> str:
    return command.replace("sudo ", "")


def print_summary(items: list[ChecklistItem]) -> int:
    width = max(len(item.name) for item in items)
    missing = 0
    current_group = ""
    for item in items:
        if item.group != current_group:
            current_group = item.group
            print(f"\n{current_group}")
        mark = "ok" if item.done else "missing"
        if not item.done:
            missing += 1
        print(f"  {mark:7} {item.name:<{width}}  {format_install_command(item.install)}")
    print(f"\n{len(items) - missing}/{len(items)} complete")
    return 0 if missing == 0 else 1


def draw(stdscr: Any, state: AppState) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    title = "Fedora Post-Install Checklist"
    progress = sum(1 for item in state.items if item.done)
    header = f"{title}  {progress}/{len(state.items)} complete"
    stdscr.addnstr(0, 0, header, width - 1, curses.A_BOLD)
    stdscr.addnstr(1, 0, "Keys: ↑/↓ move  Enter install  Space mark done  r rescan  a install missing  q quit", width - 1)

    list_top = 3
    list_bottom = max(list_top, height - 5)
    visible_rows = list_bottom - list_top
    if state.selected < state.offset:
        state.offset = state.selected
    if state.selected >= state.offset + visible_rows:
        state.offset = state.selected - visible_rows + 1

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
        marker = "[x]" if item.done else "[ ]"
        detected = "installed" if item.installed else "missing"
        if item.manual_done and not item.installed:
            detected = "manual"
        line = f"{marker} {item.name} ({detected})"
        attr = curses.A_REVERSE if real_index == state.selected else curses.A_NORMAL
        stdscr.addnstr(row, 0, line, width - 1, attr)
        row += 1

    selected = state.items[state.selected]
    detail_y = height - 3
    stdscr.addnstr(detail_y, 0, f"Install: {selected.install}", width - 1)
    if selected.notes:
        stdscr.addnstr(detail_y + 1, 0, selected.notes, width - 1)
    stdscr.addnstr(height - 1, 0, state.message, width - 1, curses.A_DIM)
    stdscr.refresh()


def tui(stdscr: Any, items: list[ChecklistItem], manual_done: set[str]) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    state = AppState(items=items, manual_done=manual_done)
    scan_items(state.items, state.manual_done)

    while True:
        draw(stdscr, state)
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            save_state(state.manual_done)
            return
        if key in (curses.KEY_DOWN, ord("j")):
            state.selected = min(len(state.items) - 1, state.selected + 1)
        elif key in (curses.KEY_UP, ord("k")):
            state.selected = max(0, state.selected - 1)
        elif key == ord(" "):
            item = state.items[state.selected]
            if item.name in state.manual_done:
                state.manual_done.remove(item.name)
                item.manual_done = False
                state.message = f"Cleared manual mark for {item.name}."
            else:
                state.manual_done.add(item.name)
                item.manual_done = True
                state.message = f"Marked {item.name} done manually."
            save_state(state.manual_done)
        elif key in (ord("r"), ord("R")):
            scan_items(state.items, state.manual_done)
            state.message = "Scan complete."
        elif key in (curses.KEY_ENTER, 10, 13):
            item = state.items[state.selected]
            state.message = f"Installing {item.name}..."
            draw(stdscr, state)
            ok, message = install_item(item)
            item.manual_done = item.name in state.manual_done
            state.message = message if len(message) < 240 else message[:237] + "..."
            if ok and item.name in state.manual_done:
                state.manual_done.remove(item.name)
                save_state(state.manual_done)
        elif key in (ord("a"), ord("A")):
            for item in state.items:
                if not item.done:
                    state.message = f"Installing {item.name}..."
                    draw(stdscr, state)
                    ok, message = install_item(item)
                    if not ok:
                        state.message = message if len(message) < 240 else message[:237] + "..."
                        break
            scan_items(state.items, state.manual_done)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Fedora post-install checklist")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=package_path("checklist.json"),
        help="Path to checklist JSON file.",
    )
    parser.add_argument("--check", action="store_true", help="Print checklist status without launching the TUI.")
    parser.add_argument("--install-missing", action="store_true", help="Install all missing items without launching the TUI.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.version:
        from fedora_checklist import __version__

        print(__version__)
        return 0

    items = load_config(args.config)
    manual_done = load_state()
    scan_items(items, manual_done)

    if args.install_missing:
        for item in items:
            if not item.done:
                print(f"Installing {item.name}: {format_install_command(item.install)}")
                ok, message = install_item(item)
                print(message)
                if not ok:
                    return 1
        scan_items(items, manual_done)
        return print_summary(items)

    if args.check:
        return print_summary(items)

    if os.name == "nt":
        print("The interactive TUI needs a Unix-like terminal. Use --check on Windows, or run this on Fedora.")
        return print_summary(items)
    if curses is None:
        print("Python curses support is required for the interactive TUI.")
        return 1
    if shutil.which("sudo") is None:
        print("sudo is required for install commands.")
        return 1

    curses.wrapper(tui, items, manual_done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
