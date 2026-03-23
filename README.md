# Ketut's File Explorer

A modern, Windows Explorer-style file manager that runs entirely in the terminal.
Perfect for VPS and remote server environments.

## Install

```bash
pip install textual rich
```

## Run

```bash
python cli.py              # opens home directory
python cli.py /var/www     # opens a specific directory
```

## File Structure

```
explorer/
├── cli.py        ← Main entry point — run this
├── helpers.py    ← Utilities, CSS theme, Settings, Clipboard
├── modals.py     ← All dialogs: Input, Confirm, Search, Editor, Preview, Settings, Help
├── widgets.py    ← FileListView, FileRow, DetailStrip
└── README.md
```

## Commands (prefix with colon)

| Command | Description |
|---|---|
| `:q` `:quit` | Exit |
| `:h` `:help` | Help & reference |
| `:r` `:reload` | Reload directory |
| `:i` `:info` | Show file info |
| `:settings` | Open settings panel |
| `:hidden` | Toggle hidden files |
| `:new <name>` | Create file |
| `:mkdir <name>` | Create folder |
| `:rename <name>` | Rename selected |
| `:del` | Delete selected |
| `:chmod 755` | Change permissions |
| `:copy` `:cut` `:paste` | Clipboard |
| `:edit` | Open in built-in editor |
| `:preview` | Preview file (full-screen) |
| `:search <query>` | Search files recursively |
| `:shell` | Open shell here |
| `:cd /path` | Navigate to directory |

## Keyboard Shortcuts

| Key | Action |
|---|---|
| F2 | Rename |
| F5 | Reload |
| Delete | Delete |
| Ctrl+N | New file |
| Ctrl+Shift+N | New folder |
| Ctrl+C / X / V | Copy / Cut / Paste |
| Ctrl+F | Search |
| Ctrl+E | Edit file |
| Ctrl+P | Preview file |
| Ctrl+H | Toggle hidden files |
| Ctrl+O | Open shell |
| Esc | Clear clipboard |

## Mouse Support

- **Single click** → select item
- **Double click** → enter folder / open file in editor
- **Click address bar** → type path, Enter to navigate
- **Click left tree** → navigate folder
- **Scroll** → scroll file list

## Settings (`:settings`)

| Setting | Default | Description |
|---|---|---|
| `show_hidden` | OFF | Show dotfiles (`.cache`, `.bashrc`, etc.) |
| `show_file_icons` | ON | Emoji icons in file list |
| `confirm_delete` | ON | Ask before deleting |
| `confirm_overwrite` | ON | Ask before overwriting on paste |
| `preview_max_kb` | 200 | Max file size for syntax preview |
| `start_path` | `~` | Startup directory |
| `date_format` | `%d/%m/%Y %H:%M` | Date display format |

Settings are saved to `~/.config/ketut-explorer/settings.json`.

## Image Files

The terminal cannot render actual images (pixels). When you open an image file,
the explorer shows:
- File info (name, format, MIME type, size, modified date)
- Pixel dimensions (if `identify` from ImageMagick is installed)
- Commands to view externally: `xdg-open`, `catimg`, `viu`, `chafa`

For pixel-level image rendering in terminal, install one of:
- [`viu`](https://github.com/atanunq/viu) — `cargo install viu`
- [`chafa`](https://hpjansson.org/chafa/) — `apt install chafa`
- [`catimg`](https://github.com/posva/catimg) — `brew install catimg`

## Requirements

```
textual>=0.47.0
rich>=13.0.0
```