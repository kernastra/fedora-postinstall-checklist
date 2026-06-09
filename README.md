# Fedora Post-Install Checklist

An interactive terminal checklist for a fresh Fedora Linux install. It scans for apps and system setup steps, lets you install missing items one at a time, and keeps manual checkoffs in local state.

## Quick Start

```bash
python3 -m pip install --user .
fedora-checklist
```

You can also run it without installing:

```bash
python3 -m fedora_checklist.app
```

## Controls

| Key | Action |
| --- | --- |
| Up/Down or `k`/`j` | Move through the checklist |
| Enter | Install the selected missing item |
| Space | Mark or unmark an item manually |
| `r` | Rescan installed programs |
| `a` | Install every missing item until one fails |
| `q` | Save and quit |

Manual marks are stored in:

```text
~/.local/state/fedora-postinstall-checklist/state.json
```

## Non-Interactive Checks

Print the status without launching the TUI:

```bash
fedora-checklist --check
```

Install all missing items without launching the TUI:

```bash
fedora-checklist --install-missing
```

## Customize The Checklist

Edit `checklist.json` or pass another JSON file:

```bash
fedora-checklist --config ~/my-fedora-checklist.json
```

Each item has:

- `name`: Label shown in the TUI.
- `check`: Shell command that exits `0` when the item is complete.
- `install`: Shell command used when you press Enter.
- `notes`: Optional detail shown at the bottom of the TUI.

Example:

```json
{
  "name": "Example App",
  "check": "command -v example",
  "install": "sudo dnf install -y example",
  "notes": "Optional context for future-you."
}
```

## Fedora Notes

The default checklist includes RPM Fusion, Flathub, common developer tools, media apps, codecs, and fonts. Some items depend on earlier setup items. For example, Flatpak apps need the Flathub remote, and multimedia codecs need RPM Fusion.

## License

MIT
