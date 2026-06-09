# Fedora Post-Install Checklist

An interactive terminal checklist and installer for a fresh Fedora Linux install. It scans for apps and system setup steps, lets you include or skip each item, then installs the selected missing items in dependency order.

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
| Space | Include or skip the selected item |
| `m` | Mark or unmark an item manually |
| Enter | Install the selected item |
| `r` | Rescan installed programs |
| `a` | Install every selected missing item until one fails |
| `?` | Show help |
| `q` | Save and quit |

Manual marks are stored in:

```text
~/.local/state/fedora-postinstall-checklist/state.json
```

The installer writes a log to:

```text
~/.local/state/fedora-postinstall-checklist/install.log
```

## Non-Interactive Modes

Print the status without launching the TUI:

```bash
fedora-checklist --check
```

Preview the install plan without launching the TUI:

```bash
fedora-checklist --plan
```

Install selected missing items without launching the TUI:

```bash
fedora-checklist --install-missing
```

Skip the confirmation prompt:

```bash
fedora-checklist --install-missing --yes
```

## Customize The Checklist

Edit `checklist.json` or pass another JSON file:

```bash
fedora-checklist --config ~/my-fedora-checklist.json
```

Each item has:

- `id`: Stable identifier used for saved state and dependencies.
- `name`: Label shown in the TUI.
- `check`: Shell command that exits `0` when the item is complete.
- `install`: Shell command used when you press Enter.
- `selected`: Optional. Defaults to `true`; set to `false` for apps you want listed but not installed by default.
- `depends_on`: Optional list of item IDs that should be installed first.
- `notes`: Optional detail shown at the bottom of the TUI.

Example:

```json
{
  "id": "example-app",
  "name": "Example App",
  "check": "command -v example",
  "install": "sudo dnf install -y example",
  "selected": true,
  "depends_on": ["flathub"],
  "notes": "Optional context for future-you."
}
```

To remove an app from your setup permanently, delete its object from `checklist.json`. To keep it visible but avoid installing it automatically, set `"selected": false` or press Space in the TUI.

## Fedora Notes

The default checklist includes RPM Fusion, Flathub, common developer tools, media apps, codecs, and fonts. Install runs are dependency-aware: Flatpak apps wait for Flathub, and multimedia codecs wait for RPM Fusion.

## License

MIT
