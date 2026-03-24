"""
modals.py — All modal dialogs: Input, Confirm, Search, Chmod, Editor, Settings, Help, Preview
xtermfiles — Terminal File Explorer
"""

import subprocess
from pathlib import Path
from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Static, TextArea
from textual.containers import Horizontal, Vertical, ScrollableContainer
from rich.text import Text
from rich.syntax import Syntax

from helpers import (
    Settings,
    is_image, is_text_file, is_video, is_audio, is_archive,
    get_lang, get_mime, format_size, format_date, format_perms,
)


# ─────────────────────────────────────────────────────────────────────────────
#  InputModal
# ─────────────────────────────────────────────────────────────────────────────
class InputModal(ModalScreen[Optional[str]]):
    def __init__(self, title: str, placeholder: str = "", default: str = "",
                 confirm_label: str = "OK", danger: bool = False):
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._default = default
        self._confirm_label = confirm_label
        self._danger = danger

    def compose(self) -> ComposeResult:
        btn_cls = "btn-danger" if self._danger else "btn-ok"
        with Vertical(id="modal-box"):
            yield Label(self._title, id="modal-title")
            yield Input(placeholder=self._placeholder, value=self._default,
                        id="modal-input", classes="modal-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button(self._confirm_label, id="btn-ok", classes=btn_cls)

    def on_mount(self):
        inp = self.query_one("#modal-input", Input)
        inp.focus(); inp.action_select_all()

    def on_button_pressed(self, e: Button.Pressed):
        self.dismiss(self.query_one("#modal-input", Input).value.strip()
                     if e.button.id == "btn-ok" else None)

    def on_input_submitted(self, e: Input.Submitted):
        self.dismiss(e.value.strip())

    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
#  ConfirmModal
# ─────────────────────────────────────────────────────────────────────────────
class ConfirmModal(ModalScreen[bool]):
    def __init__(self, title: str, message: str,
                 confirm_label: str = "OK", danger: bool = False):
        super().__init__()
        self._title = title; self._message = message
        self._confirm_label = confirm_label; self._danger = danger

    def compose(self) -> ComposeResult:
        btn_cls = "btn-danger" if self._danger else "btn-ok"
        with Vertical(id="modal-box"):
            yield Label(self._title, id="modal-title")
            yield Label(self._message, id="modal-body")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button(self._confirm_label, id="btn-ok", classes=btn_cls)

    def on_mount(self): self.query_one("#btn-ok", Button).focus()

    def on_button_pressed(self, e: Button.Pressed):
        self.dismiss(e.button.id == "btn-ok")

    def on_key(self, e):
        if e.key == "escape": self.dismiss(False)
        elif e.key == "enter": self.dismiss(True)


# ─────────────────────────────────────────────────────────────────────────────
#  SearchModal
# ─────────────────────────────────────────────────────────────────────────────
class SearchModal(ModalScreen[Optional[Path]]):
    def __init__(self, root: Path):
        super().__init__()
        self._root = root
        self._results: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label("  Search Files  (min. 2 chars)", id="modal-title")
            yield Input(placeholder="filename / pattern...", id="modal-input",
                        classes="modal-input")
            yield ListView(id="search-list")
            with Horizontal(classes="modal-buttons"):
                yield Button("Close", id="btn-cancel", classes="btn-cancel")
                yield Button("Open",  id="btn-ok",     classes="btn-ok")

    def on_mount(self): self.query_one("#modal-input", Input).focus()

    def on_input_changed(self, e: Input.Changed):
        q = e.value.strip().lower()
        lv = self.query_one("#search-list", ListView)
        lv.clear(); self._results = []
        if len(q) < 2: return
        try:
            for p in self._root.rglob("*"):
                if q in p.name.lower():
                    self._results.append(p)
                    if len(self._results) >= 150: break
        except PermissionError: pass
        for r in self._results:
            rel = r.relative_to(self._root) if r.is_relative_to(self._root) else r
            lv.append(ListItem(Label(str(rel))))

    def on_list_view_selected(self, _e: ListView.Selected):
        lv = self.query_one("#search-list", ListView)
        if lv.index is not None and lv.index < len(self._results):
            self.dismiss(self._results[lv.index])

    def on_button_pressed(self, e: Button.Pressed):
        if e.button.id == "btn-ok":
            lv = self.query_one("#search-list", ListView)
            if lv.index is not None and lv.index < len(self._results):
                self.dismiss(self._results[lv.index]); return
        self.dismiss(None)

    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
#  ChmodModal
# ─────────────────────────────────────────────────────────────────────────────
class ChmodModal(ModalScreen[Optional[str]]):
    def __init__(self, path: Path):
        super().__init__()
        self._path = path
        import stat as _s
        self._current = oct(_s.S_IMODE(path.stat().st_mode))[-3:]

    def compose(self) -> ComposeResult:
        st = self._path.stat()
        sym = format_perms(st.st_mode)
        with Vertical(id="modal-box"):
            yield Label(f"  Change Permissions — {self._path.name}", id="modal-title")
            yield Label(f"Current: {sym}  ({self._current})", id="modal-body")
            yield Input(placeholder="e.g. 755 or 644", value=self._current,
                        id="modal-input", classes="modal-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button("Apply",  id="btn-ok",     classes="btn-ok")

    def on_mount(self):
        inp = self.query_one("#modal-input", Input)
        inp.focus(); inp.action_select_all()

    def on_button_pressed(self, e: Button.Pressed):
        self.dismiss(self.query_one("#modal-input", Input).value.strip()
                     if e.button.id == "btn-ok" else None)

    def on_input_submitted(self, e: Input.Submitted):
        self.dismiss(e.value.strip())

    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
#  TextEditorModal — full-screen built-in editor with syntax highlighting
# ─────────────────────────────────────────────────────────────────────────────
class TextEditorModal(ModalScreen[bool]):
    """
    Full-screen editor (100% width × 100% height).
    Ctrl+S = save, Esc = cancel.
    Save / Cancel buttons are fixed in the bottom-right footer.
    """

    def __init__(self, path: Path):
        super().__init__()
        self._path = path

    def compose(self) -> ComposeResult:
        try:
            content = self._path.read_text(errors="replace") if self._path.exists() else ""
        except Exception:
            content = ""

        lang = get_lang(self._path)
        textual_langs = {
            "python","javascript","typescript","html","css","markdown",
            "json","sql","bash","rust","go","java","c","cpp","regex",
        }
        use_lang = lang if lang in textual_langs else None

        with Vertical(classes="editor-box"):
            yield Label(
                f"️  {self._path}    │   Ctrl+S = Save   │   Esc = Cancel",
                id="editor-titlebar"
            )
            yield TextArea(
                content,
                language=use_lang,
                id="editor-area",
            )
            with Horizontal(id="editor-footer"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button("  Save", id="btn-ok", classes="btn-ok")

    def on_mount(self):
        self.query_one("#editor-area", TextArea).focus()

    def _save(self):
        content = self.query_one("#editor-area", TextArea).text
        try:
            self._path.write_text(content)
            self.dismiss(True)
        except Exception as e:
            self.notify(f" Save failed: {e}", severity="error")

    def on_button_pressed(self, e: Button.Pressed):
        if e.button.id == "btn-ok": self._save()
        else: self.dismiss(False)

    def on_key(self, e):
        if e.key == "ctrl+s": self._save()
        elif e.key == "escape": self.dismiss(False)


# ─────────────────────────────────────────────────────────────────────────────
#  FilePreviewModal — full-screen preview for any file type
# ─────────────────────────────────────────────────────────────────────────────
class FilePreviewModal(ModalScreen[None]):
    """
    Full-screen preview modal.
    - Text / code → Syntax highlighted TextArea (read-only view via Static+Syntax)
    - Image       → ASCII art info + pixel dimensions via `file` command
    - Binary      → Hex dump of first 512 bytes
    - Archive     → File listing via `unzip -l` / `tar -tvf`
    """

    def __init__(self, path: Path, settings: Settings):
        super().__init__()
        self._path = path
        self._settings = settings

    def compose(self) -> ComposeResult:
        name = self._path.name
        mime = get_mime(self._path)
        with Vertical(id="preview-box"):
            yield Label(
                f"  Preview — {self._path}    │   Esc or Close to go back",
                id="preview-titlebar"
            )
            with ScrollableContainer(id="preview-content"):
                yield Static(self._build_content(), id="preview-static")
            with Horizontal(id="preview-footer"):
                yield Button("Close", id="btn-cancel", classes="btn-cancel")

    def _build_content(self) -> str | object:
        path = self._path
        max_bytes = self._settings.get("preview_max_kb") * 1024

        # ── Image ──
        if is_image(path):
            return self._image_info(path)

        # ── Text / code ──
        if is_text_file(path):
            try:
                size = path.stat().st_size
                if size > max_bytes:
                    return (f"[yellow]File too large to preview ({format_size(size)}).\n"
                            f"Limit: {self._settings.get('preview_max_kb')} KB[/yellow]")
                content = path.read_text(errors="replace")
                lang = get_lang(path)
                return Syntax(content, lang, theme="monokai",
                              line_numbers=True, word_wrap=False)
            except Exception as e:
                return f"[red]Error reading file: {e}[/red]"

        # ── Archive ──
        if is_archive(path):
            return self._archive_listing(path)

        # ── Audio / Video ──
        if is_audio(path) or is_video(path):
            st = path.stat()
            mime = get_mime(path)
            return (
                f"[bold yellow]{'' if is_audio(path) else ''}  Media File[/bold yellow]\n\n"
                f"Name    : {path.name}\n"
                f"MIME    : {mime}\n"
                f"Size    : {format_size(st.st_size)}\n"
                f"Modified: {format_date(st.st_mtime)}\n\n"
                f"[dim]Terminal cannot play media files.\n"
                f"Use a media player application.[/dim]"
            )

        # ── Generic binary ──
        return self._hex_preview(path)

    def _image_info(self, path: Path) -> str:
        import subprocess, shutil
        st = path.stat()
        lines = [
            f"[bold yellow]️  Image File[/bold yellow]\n",
            f"Name    : {path.name}",
            f"Format  : {path.suffix.upper().lstrip('.')}",
            f"MIME    : {get_mime(path)}",
            f"Size    : {format_size(st.st_size)}",
            f"Modified: {format_date(st.st_mtime)}",
        ]

        # Try to get dimensions using `file` command
        if shutil.which("file"):
            try:
                result = subprocess.run(
                    ["file", str(path)], capture_output=True, text=True, timeout=3
                )
                if result.stdout:
                    lines.append(f"Info    : {result.stdout.split(':',1)[-1].strip()}")
            except Exception:
                pass

        # Try `identify` (ImageMagick) for pixel dimensions
        if shutil.which("identify"):
            try:
                result = subprocess.run(
                    ["identify", "-format", "%wx%h", str(path)],
                    capture_output=True, text=True, timeout=3
                )
                if result.stdout.strip():
                    lines.append(f"Pixels  : {result.stdout.strip()}")
            except Exception:
                pass

        lines += [
            "",
            "[dim]─── Terminal Image Rendering ───────────────────────────────[/dim]",
            "",
            "[dim]True image rendering is not possible in a standard terminal.[/dim]",
            "[dim]Install a kitty/iTerm2/sixel-capable terminal for pixel art.[/dim]",
            "",
            "[cyan]To view this image:[/cyan]",
            f"  xdg-open \"{path}\"      (Linux GUI)",
            f"  open \"{path}\"          (macOS)",
            f"  catimg \"{path}\"        (catimg tool)",
            f"  viu \"{path}\"           (viu tool — pip install viu)",
            f"  chafa \"{path}\"         (chafa tool)",
        ]
        return "\n".join(lines)

    def _hex_preview(self, path: Path) -> str:
        try:
            with open(path, "rb") as f:
                data = f.read(512)
            lines = [
                f"[bold yellow]⬡  Binary File[/bold yellow]\n",
                f"Name : {path.name}",
                f"MIME : {get_mime(path)}",
                f"Size : {format_size(path.stat().st_size)}",
                "",
                "[dim]─── Hex Preview (first 512 bytes) ──────────────────────────[/dim]",
                "",
            ]
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                hex_part  = " ".join(f"{b:02x}" for b in chunk).ljust(48)
                ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"[dim]{i:04x}[/dim]  [cyan]{hex_part}[/cyan]  [green]{ascii_part}[/green]")
            return "\n".join(lines)
        except Exception as e:
            return f"[red]Cannot read file: {e}[/red]"

    def _archive_listing(self, path: Path) -> str:
        import subprocess, shutil
        ext = path.suffix.lower()
        lines = [
            f"[bold yellow]  Archive File[/bold yellow]\n",
            f"Name : {path.name}",
            f"Size : {format_size(path.stat().st_size)}",
            "",
            "[dim]─── Contents ──────────────────────────────────────────────────[/dim]",
            "",
        ]
        try:
            if ext == ".zip" and shutil.which("unzip"):
                r = subprocess.run(["unzip","-l",str(path)], capture_output=True, text=True, timeout=5)
                lines.append(r.stdout or r.stderr)
            elif ext in {".tar",".gz",".bz2",".xz"} and shutil.which("tar"):
                r = subprocess.run(["tar","-tvf",str(path)], capture_output=True, text=True, timeout=5)
                lines.append(r.stdout or r.stderr)
            elif ext == ".7z" and shutil.which("7z"):
                r = subprocess.run(["7z","l",str(path)], capture_output=True, text=True, timeout=5)
                lines.append(r.stdout or r.stderr)
            else:
                lines.append("[dim]Install unzip / tar / 7z to list archive contents.[/dim]")
        except Exception as e:
            lines.append(f"[red]{e}[/red]")
        return "\n".join(lines)

    def on_button_pressed(self, _e: Button.Pressed):
        self.dismiss(None)

    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)



# ─────────────────────────────────────────────────────────────────────────────
#  SettingsModal  —  :settings
#  Lightweight: no nested classes, no dynamic widget factories.
#  Bool settings = simple Button that shows ON/OFF state via label.
# ─────────────────────────────────────────────────────────────────────────────
class SettingsModal(ModalScreen[bool]):

    # Map key → (label, description)
    BOOL_SETTINGS = [
        ("show_hidden",       "Show hidden files",          "Show dotfiles (.cache, .ssh …)"),
        ("show_file_icons",   "Show file icons",            "Emoji icons next to filenames"),
        ("confirm_delete",    "Confirm before delete",      "Ask before permanently deleting"),
        ("confirm_overwrite", "Confirm before overwrite",   "Ask before overwriting on paste"),
    ]
    TEXT_SETTINGS = [
        ("preview_max_kb", "Preview max size (KB)", "200"),
        ("start_path",     "Startup directory",     "~"),
        ("date_format",    "Date format",            "%d/%m/%Y %H:%M"),
    ]

    def __init__(self, settings: Settings):
        super().__init__()
        self._s = settings

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Label("  Settings — xtermfiles", id="settings-titlebar")

            with ScrollableContainer(id="settings-scroll"):

                # ── Bool toggles ──────────────────────────────────────
                yield Static("[bold #4fc1ff]Display & Behaviour[/bold #4fc1ff]",
                             classes="stg-section")
                for key, label, desc in self.BOOL_SETTINGS:
                    val = bool(self._s.get(key))
                    yield Static(
                        f"[bold #d4d4d4]{label}[/bold #d4d4d4]  "
                        f"[dim]{desc}[/dim]",
                        classes="stg-label",
                    )
                    yield Button(
                        "  ON " if val else "  OFF",
                        id=f"tog-{key}",
                        classes="stg-btn-on" if val else "stg-btn-off",
                    )

                # ── Text inputs ───────────────────────────────────────
                yield Static("[bold #4fc1ff]Other[/bold #4fc1ff]",
                             classes="stg-section")
                for key, label, placeholder in self.TEXT_SETTINGS:
                    yield Static(
                        f"[bold #d4d4d4]{label}[/bold #d4d4d4]",
                        classes="stg-label",
                    )
                    yield Input(
                        value=str(self._s.get(key)),
                        placeholder=placeholder,
                        id=f"inp-{key}",
                        classes="stg-input",
                    )

                # ── SSH profiles ──────────────────────────────────────
                yield Static("[bold #4fc1ff]Saved SSH Connections[/bold #4fc1ff]",
                             classes="stg-section")
                yield Static("[dim]Format: user:pass@host:port (one per line)[/dim]",
                             classes="stg-label")
                saved_str = "\n".join(self._s.get("saved_ssh") or [])
                ta_ssh = TextArea(
                    saved_str,
                    id="inp-saved_ssh",
                    classes="stg-input",
                )
                ta_ssh.styles.height = 10
                yield ta_ssh

            # ── Footer ────────────────────────────────────────────────
            with Horizontal(id="settings-footer"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button("Save",   id="btn-save",   classes="btn-ok")

    def on_button_pressed(self, e: Button.Pressed):
        bid = e.button.id or ""

        if bid.startswith("tog-"):
            key = bid[4:]
            new_val = self._s.toggle(key)
            e.button.label = "  ON " if new_val else "  OFF"
            e.button.remove_class("stg-btn-on", "stg-btn-off")
            e.button.add_class("stg-btn-on" if new_val else "stg-btn-off")
            return

        if bid == "btn-save":
            for key, _, _ in self.TEXT_SETTINGS:
                try:
                    raw = self.query_one(f"#inp-{key}", Input).value.strip()
                    self._s.set(key, int(raw) if key == "preview_max_kb" else raw)
                except Exception:
                    pass
            
            # Save SSH profiles
            try:
                raw_ssh = self.query_one("#inp-saved_ssh", TextArea).text.strip()
                ssh_list = [line.strip() for line in raw_ssh.split("\n") if line.strip()]
                self._s.set("saved_ssh", ssh_list)
            except Exception:
                pass

            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, e):
        if e.key == "escape":
            self.dismiss(False)

# ─────────────────────────────────────────────────────────────────────────────
#  CommandModal — double-space popup for quick commands
# ─────────────────────────────────────────────────────────────────────────────
class CommandModal(ModalScreen[Optional[str]]):
    """
    Compact command palette that appears in the centre on double-space.
    Returns the raw command string (with leading colon) or None.
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="cmd-modal-box"):
            yield Label(
                "  Command Bar   [dim]Space·Space to close · Enter to run · Esc to cancel[/dim]",
                id="cmd-modal-title",
            )
            yield Input(
                placeholder=":help  :settings  :new file.txt  :cd /path  :q",
                id="cmd-modal-input",
                classes="modal-input",
            )
            # Quick-pick hint row
            yield Static(
                "[dim] :help   :settings   :hidden   :search   :shell   :edit   :preview[/dim]",
                id="cmd-modal-hints",
            )

    def on_mount(self):
        self.query_one("#cmd-modal-input", Input).focus()

    def on_input_submitted(self, e: Input.Submitted):
        val = e.value.strip()
        self.dismiss(val if val else None)

    def on_key(self, e):
        if e.key == "escape":
            self.dismiss(None)
        elif e.key == "space" and not self.query_one("#cmd-modal-input", Input).value:
            # second space on empty input = close
            self.dismiss(None)


COMMANDS = [
    (":q / :quit",        "Exit the application"),
    (":h / :help",        "Show this help"),
    (":r / :reload",      "Reload current directory"),
    (":i / :info",        "Show file / folder details"),
    (":settings",         "Open settings panel"),
    (":hidden",           "Toggle dotfiles visibility"),
    (":new <name>",       "Create a new file"),
    (":mkdir <name>",     "Create a new folder"),
    (":rename <name>",    "Rename selected item"),
    (":del",              "Delete selected item"),
    (":chmod <octal>",    "Change permissions  e.g. :chmod 755"),
    (":search <query>",   "Recursive filename search"),
    (":copy",             "Copy selected to clipboard"),
    (":cut",              "Cut selected to clipboard"),
    (":paste",            "Paste clipboard here"),
    (":edit",             "Open file in built-in editor"),
    (":preview",          "Full-screen file preview"),
    (":shell",            "Open shell in current directory"),
    (":cd <path>",        "Navigate to a directory"),
]

SHORTCUTS = [
    ("Space Space",   "Open / close command bar"),
    ("F2",            "Rename selected"),
    ("F5",            "Reload directory"),
    ("Delete",        "Delete selected"),
    ("Ctrl+N",        "New file"),
    ("Ctrl+Shift+N",  "New folder"),
    ("Ctrl+C/X/V",   "Copy / Cut / Paste"),
    ("Ctrl+F",        "Search"),
    ("Ctrl+E",        "Edit file"),
    ("Ctrl+P",        "Preview file"),
    ("Ctrl+H",        "Toggle hidden files"),
    ("Ctrl+O",        "Open shell"),
    ("Esc",           "Close overlay / clear clipboard"),
    ("Dbl-click",     "Enter folder or edit file"),
    ("Backspace",     "Go up one directory"),
]


class HelpModal(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Label("  xtermfiles — Command Reference", id="help-titlebar")
            with ScrollableContainer(id="help-scroll"):
                yield Static(self._build(), id="help-content")
            with Horizontal(id="help-footer"):
                yield Button("Close", id="btn-close", classes="btn-cancel")

    @staticmethod
    def _build() -> str:
        col = max(len(c) for c, _ in COMMANDS) + 2
        out = []
        out.append("[bold #4fc1ff]COMMANDS[/bold #4fc1ff]  [dim]prefix with colon[/dim]")
        out.append("")
        for cmd, desc in COMMANDS:
            out.append("  [bold #9cdcfe]{:<{}}[/bold #9cdcfe]  [#d4d4d4]{}[/#d4d4d4]".format(cmd, col, desc))
        out.append("")
        col2 = max(len(k) for k, _ in SHORTCUTS) + 2
        out.append("[bold #4fc1ff]SHORTCUTS[/bold #4fc1ff]")
        out.append("")
        for key, desc in SHORTCUTS:
            out.append("  [bold #ce9178]{:<{}}[/bold #ce9178]  [#d4d4d4]{}[/#d4d4d4]".format(key, col2, desc))
        out.append("")
        out.append("[bold #4fc1ff]MOUSE[/bold #4fc1ff]")
        out.append("")
        for label, desc in [
            ("Single click",  "Select item"),
            ("Double click",  "Enter folder / open file in editor"),
            ("Address bar",   "Type path + Enter to navigate"),
            ("Left tree",     "Click to navigate folders"),
        ]:
            out.append("  [bold #6a9955]{:<14}[/bold #6a9955]  [#d4d4d4]{}[/#d4d4d4]".format(label, desc))
        out.append("")
        out.append("[dim]Settings saved to  ~/.config/xtermfiles/settings.json[/dim]")
        return "\n".join(out)
    def on_button_pressed(self, _e: Button.Pressed):
        self.dismiss(None)

    def on_key(self, e):
        if e.key == "escape":
            self.dismiss(None)

class SSHLoginModal(ModalScreen[tuple[str, str]]):
    def __init__(self, host: str, port: str):
        super().__init__()
        self.host = host
        self.port = port

    def compose(self) -> ComposeResult:
        with Vertical(id="ssh-box", classes="dialog-box"):
            yield Label(f"SSH Login: {self.host}:{self.port}", id="ssh-title", classes="dialog-title")
            with Horizontal(classes="dialog-input-row"):
                yield Label("User:", classes="dialog-label")
                yield Input("root", id="ssh-user", classes="dialog-input")
            with Horizontal(classes="dialog-input-row"):
                yield Label("Pass:", classes="dialog-label")
                yield Input(password=True, id="ssh-pass", classes="dialog-input")
            with Horizontal(classes="dialog-btn-row"):
                yield Button("Connect", id="ssh-connect-btn", variant="primary")
                yield Button("Cancel", id="ssh-cancel-btn")

    def on_mount(self):
        self.query_one("#ssh-pass", Input).focus()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "ssh-connect-btn":
            user = self.query_one("#ssh-user", Input).value
            pwd = self.query_one("#ssh-pass", Input).value
            self.dismiss((user, pwd))
        elif event.button.id == "ssh-cancel-btn":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted):
        user = self.query_one("#ssh-user", Input).value
        pwd = self.query_one("#ssh-pass", Input).value
        self.dismiss((user, pwd))

    def on_key(self, event: events.Key):
        if event.key == "escape":
            self.dismiss(None)

class LoadingModal(ModalScreen[None]):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="loading-box", classes="dialog-box"):
            yield Label(self.message, id="loading-msg", classes="dialog-title")
            with Horizontal(classes="dialog-btn-row"):
                yield Button("Cancel", id="loading-cancel-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "loading-cancel-btn":
            self.dismiss(None)