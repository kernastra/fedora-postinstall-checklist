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

## Current Personal App Set

Included by default:

- Firefox, LibreWolf, Discord, Steam, Obsidian, and 1Password.
- Claude Code CLI, Codex CLI, Ollama, Hermes Agent, Higgsfield MCP CLI, GitHub CLI, Supabase CLI, Vercel CLI, and Docker.
- Fedora setup basics, Intel Arc Pro B60 support packages, shell utilities, codecs, and fonts.

Skipped by default, but still visible so you can include them with Space:

- PAI Agent, because the requested package name is ambiguous. The current candidate is `paintress-cli`, which is built on `pai-agent-sdk`.
- Spotify, VLC, Neovim, and Visual Studio Code from the starter checklist.
- Intel Arc Pro B60 hardware verifiers. Include these after the B60 is physically installed.

Not included:

- Chromium and GIMP were removed.
- Linear does not currently publish a Linux desktop app. Use Linear in a supported browser or install it as a browser PWA.

## Intel Arc Pro B60

The checklist installs Fedora's current Intel Arc support packages by default:

- `linux-firmware`
- Mesa OpenGL/Vulkan packages
- `libva-utils` and `libva-intel-media-driver`
- `intel-gpu-tools`
- `intel-compute-runtime` and `clinfo`

The B60 verification items are skipped by default so the full install run does not fail before the physical GPU is installed. After the card is in the machine, include those verifier items with Space or run:

```bash
fedora-checklist --check
```

Also enable Resizable BAR or Smart Access Memory, Above 4G Decoding if your BIOS requires it, and UEFI boot mode.

## License

MIT
