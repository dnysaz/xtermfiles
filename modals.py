"""
modals.py — All modal dialogs
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
from rich.syntax import Syntax

from helpers import (
    Settings,
    is_image, is_text_file, is_video, is_audio, is_archive,
    get_lang, get_mime, format_size, format_date, format_perms,
)

_TEXTUAL_LANGS = {
    "python", "javascript", "typescript", "html", "css", "markdown",
    "json", "sql", "bash", "rust", "go", "java", "c", "cpp", "regex",
    "yaml", "toml", "scss", "kotlin", "ruby", "php", "lua", "r",
}


# ─────────────────────────────────────────────────────────────────────────────
#  InputModal
# ─────────────────────────────────────────────────────────────────────────────
class InputModal(ModalScreen[Optional[str]]):
    def __init__(self, title: str, placeholder: str = "", default: str = "",
                 confirm_label: str = "OK", danger: bool = False):
        super().__init__()
        self._title = title; self._placeholder = placeholder
        self._default = default; self._confirm_label = confirm_label
        self._danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label(self._title, id="modal-title")
            yield Input(placeholder=self._placeholder, value=self._default,
                        id="modal-input", classes="modal-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button(self._confirm_label, id="btn-ok",
                             classes="btn-danger" if self._danger else "btn-ok")

    def on_mount(self):
        inp = self.query_one("#modal-input", Input)
        inp.focus(); inp.action_select_all()

    def on_button_pressed(self, e: Button.Pressed):
        self.dismiss(
            self.query_one("#modal-input", Input).value.strip()
            if e.button.id == "btn-ok" else None
        )

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
        with Vertical(id="modal-box"):
            yield Label(self._title, id="modal-title")
            yield Label(self._message, id="modal-body")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button(self._confirm_label, id="btn-ok",
                             classes="btn-danger" if self._danger else "btn-ok")

    def on_mount(self): self.query_one("#btn-ok", Button).focus()

    def on_button_pressed(self, e: Button.Pressed):
        self.dismiss(e.button.id == "btn-ok")

    def on_key(self, e):
        if e.key == "escape":   self.dismiss(False)
        elif e.key == "enter":  self.dismiss(True)


# ─────────────────────────────────────────────────────────────────────────────
#  SearchModal  (async rglob to avoid blocking UI)
# ─────────────────────────────────────────────────────────────────────────────
class SearchModal(ModalScreen[Optional[Path]]):
    def __init__(self, root: Path):
        super().__init__()
        self._root    = root
        self._results: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label("  Search Files  (min 2 chars)", id="modal-title")
            yield Input(placeholder="filename / pattern...",
                        id="modal-input", classes="modal-input")
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
        except PermissionError:
            pass
        for r in self._results:
            try:    rel = r.relative_to(self._root)
            except: rel = r
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
#  TextEditorModal — full-screen editor
# ─────────────────────────────────────────────────────────────────────────────
class TextEditorModal(ModalScreen[bool]):
    """
    Full-screen editor.
    - Read mode : shows Rich Syntax (colour-highlighted, read-only)
    - Edit mode : TextArea with same language — Ctrl+S or Save button to save
    Toggle with Ctrl+E or the Edit/Read button in the footer.
    """

    def __init__(self, path: Path):
        super().__init__()
        self._path    = path
        self._editing = False
        try:
            self._content = path.read_text(errors="replace") if path.exists() else ""
        except Exception:
            self._content = ""
        self._lang     = get_lang(path)
        self._use_lang = self._lang if self._lang in _TEXTUAL_LANGS else None

    def compose(self) -> ComposeResult:
        with Vertical(classes="editor-box"):
            yield Label(
                f" {self._path.name}  |  READ  |  Ctrl+E = edit  |  Esc = close",
                id="editor-titlebar",
            )
            # Syntax view (read mode — always rendered with colour)
            from rich.syntax import Syntax as _Syn
            yield Static(
                _Syn(self._content, self._lang, theme="monokai",
                     line_numbers=True, word_wrap=False),
                id="editor-view",
            )
            # TextArea (edit mode — hidden until Ctrl+E)
            yield TextArea(
                self._content,
                language=self._use_lang,
                theme="vscode_dark",
                id="editor-area",
            )
            with Horizontal(id="editor-footer"):
                yield Button("Close",    id="btn-cancel", classes="btn-cancel")
                yield Button("Edit",     id="btn-edit",   classes="btn-ok")
                yield Button("Save",     id="btn-ok",     classes="btn-ok")

    def on_mount(self):
        # Start in read mode: show view, hide textarea
        self.query_one("#editor-area", TextArea).display = False
        self.query_one("#btn-ok",      Button).display   = False
        self.query_one("#editor-area", TextArea)  # warm up

    def _enter_edit(self):
        self._editing = True
        content = self.query_one("#editor-view", Static)
        ta      = self.query_one("#editor-area", TextArea)
        content.display = False
        ta.display      = True
        ta.focus()
        self.query_one("#btn-edit", Button).display = False
        self.query_one("#btn-ok",   Button).display = True
        self._set_title(f" {self._path.name}  |  EDIT  |  Ctrl+S = save  |  Esc = close")

    def _enter_read(self):
        self._editing = False
        # Refresh syntax view with current textarea content
        from rich.syntax import Syntax as _Syn
        ta = self.query_one("#editor-area", TextArea)
        self.query_one("#editor-view", Static).update(
            _Syn(ta.text, self._lang, theme="monokai",
                 line_numbers=True, word_wrap=False)
        )
        self.query_one("#editor-view", Static).display = True
        ta.display = False
        self.query_one("#btn-edit", Button).display = True
        self.query_one("#btn-ok",   Button).display = False
        self._set_title(f" {self._path.name}  |  READ  |  Ctrl+E = edit  |  Esc = close")

    def _set_title(self, text: str):
        self.query_one("#editor-titlebar", Label).update(text)

    def _save(self):
        ta = self.query_one("#editor-area", TextArea)
        try:
            self._path.write_text(ta.text)
            self._content = ta.text
            self._enter_read()          # back to read mode after save
            self.app.notify(f"Saved: {self._path.name}")
        except Exception as e:
            self.app.notify(f"Save failed: {e}", severity="error")

    def on_button_pressed(self, e: Button.Pressed):
        if   e.button.id == "btn-ok":     self._save()
        elif e.button.id == "btn-edit":   self._enter_edit()
        elif e.button.id == "btn-cancel":
            if self._editing:
                self._enter_read()      # cancel edit, go back to read
            else:
                self.dismiss(False)

    def on_key(self, e):
        if   e.key == "ctrl+s": self._save()
        elif e.key == "ctrl+e":
            if self._editing: self._enter_read()
            else:             self._enter_edit()
        elif e.key == "escape":
            if self._editing: self._enter_read()
            else:             self.dismiss(False)


# ─────────────────────────────────────────────────────────────────────────────
#  FilePreviewModal — full-screen preview
# ─────────────────────────────────────────────────────────────────────────────
class FilePreviewModal(ModalScreen[None]):
    def __init__(self, path: Path, settings: Settings):
        super().__init__()
        self._path = path; self._settings = settings

    def compose(self) -> ComposeResult:
        with Vertical(id="preview-box"):
            yield Label(f" Preview — {self._path.name}  |  Esc to close",
                        id="preview-titlebar")
            with ScrollableContainer(id="preview-content"):
                yield Static(self._build(), id="preview-static")
            with Horizontal(id="preview-footer"):
                yield Button("Close", id="btn-cancel", classes="btn-cancel")

    def _build(self):
        path      = self._path
        max_bytes = self._settings.get("preview_max_kb") * 1024
        if is_image(path):   return self._image_info(path)
        if is_text_file(path):
            try:
                if path.stat().st_size > max_bytes:
                    return f"[yellow]File too large ({format_size(path.stat().st_size)})[/yellow]"
                lang = get_lang(path)
                return Syntax(path.read_text(errors="replace"), lang,
                              theme="monokai", line_numbers=True, word_wrap=False)
            except Exception as e:
                return f"[red]{e}[/red]"
        if is_archive(path): return self._archive_info(path)
        if is_audio(path) or is_video(path):
            st = path.stat()
            return (f"[bold yellow]Media File[/bold yellow]\n\n"
                    f"Name : {path.name}\nMIME : {get_mime(path)}\n"
                    f"Size : {format_size(st.st_size)}\n"
                    f"Modified: {format_date(st.st_mtime)}")
        return self._hex_dump(path)

    def _image_info(self, path: Path) -> str:
        import shutil
        st    = path.stat()
        lines = [
            f"[bold yellow]Image File[/bold yellow]\n",
            f"Name    : {path.name}",
            f"Format  : {path.suffix.upper().lstrip('.')}",
            f"MIME    : {get_mime(path)}",
            f"Size    : {format_size(st.st_size)}",
            f"Modified: {format_date(st.st_mtime)}",
        ]
        if shutil.which("file"):
            try:
                r = subprocess.run(["file", str(path)], capture_output=True,
                                   text=True, timeout=3)
                if r.stdout:
                    lines.append(f"Info    : {r.stdout.split(':',1)[-1].strip()}")
            except Exception: pass
        if shutil.which("identify"):
            try:
                r = subprocess.run(["identify", "-format", "%wx%h", str(path)],
                                   capture_output=True, text=True, timeout=3)
                if r.stdout.strip():
                    lines.append(f"Pixels  : {r.stdout.strip()}")
            except Exception: pass
        lines += ["", "[dim]To view: xdg-open / open / viu / chafa / catimg[/dim]"]
        return "\n".join(lines)

    def _hex_dump(self, path: Path) -> str:
        try:
            data  = path.read_bytes()[:512]
            lines = [f"[bold yellow]Binary File[/bold yellow]\n",
                     f"Name : {path.name}",
                     f"MIME : {get_mime(path)}",
                     f"Size : {format_size(path.stat().st_size)}", ""]
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                hex_  = " ".join(f"{b:02x}" for b in chunk).ljust(48)
                asc   = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"[dim]{i:04x}[/dim]  [cyan]{hex_}[/cyan]  [green]{asc}[/green]")
            return "\n".join(lines)
        except Exception as e:
            return f"[red]{e}[/red]"

    def _archive_info(self, path: Path) -> str:
        import shutil
        ext   = path.suffix.lower()
        lines = [f"[bold yellow]Archive File[/bold yellow]\n",
                 f"Name : {path.name}",
                 f"Size : {format_size(path.stat().st_size)}", ""]
        try:
            if ext == ".zip" and shutil.which("unzip"):
                r = subprocess.run(["unzip","-l",str(path)], capture_output=True,
                                   text=True, timeout=5)
                lines.append(r.stdout or r.stderr)
            elif ext in {".tar",".gz",".bz2",".xz"} and shutil.which("tar"):
                r = subprocess.run(["tar","-tvf",str(path)], capture_output=True,
                                   text=True, timeout=5)
                lines.append(r.stdout or r.stderr)
            elif ext == ".7z" and shutil.which("7z"):
                r = subprocess.run(["7z","l",str(path)], capture_output=True,
                                   text=True, timeout=5)
                lines.append(r.stdout or r.stderr)
            else:
                lines.append("[dim]Install unzip / tar / 7z to list contents[/dim]")
        except Exception as e:
            lines.append(f"[red]{e}[/red]")
        return "\n".join(lines)

    def on_button_pressed(self, _e: Button.Pressed): self.dismiss(None)
    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
#  SettingsModal  (lightweight — no nested classes)
# ─────────────────────────────────────────────────────────────────────────────
class SettingsModal(ModalScreen[bool]):
    BOOL_SETTINGS = [
        ("show_hidden",       "Show hidden files",         "Show dotfiles (.cache, .ssh …)"),
        ("show_file_icons",   "Show file icons",           "Text icons next to filenames"),
        ("confirm_delete",    "Confirm before delete",     "Ask before permanently deleting"),
        ("confirm_overwrite", "Confirm before overwrite",  "Ask before overwriting on paste"),
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
                yield Static("[bold #4fc1ff]Display & Behaviour[/bold #4fc1ff]",
                             classes="stg-section")
                for key, label, desc in self.BOOL_SETTINGS:
                    val = bool(self._s.get(key))
                    yield Static(f"[bold #d4d4d4]{label}[/bold #d4d4d4]  [dim]{desc}[/dim]",
                                 classes="stg-label")
                    yield Button("  ON " if val else "  OFF",
                                 id=f"tog-{key}",
                                 classes="stg-btn-on" if val else "stg-btn-off")
                yield Static("[bold #4fc1ff]Other[/bold #4fc1ff]", classes="stg-section")
                for key, label, placeholder in self.TEXT_SETTINGS:
                    yield Static(f"[bold #d4d4d4]{label}[/bold #d4d4d4]", classes="stg-label")
                    yield Input(value=str(self._s.get(key)), placeholder=placeholder,
                                id=f"inp-{key}", classes="stg-input")
                yield Static("[bold #4fc1ff]Saved SSH Connections[/bold #4fc1ff]",
                             classes="stg-section")
                yield Static("[dim]Format: user:pass@host:port  (one per line)[/dim]",
                             classes="stg-label")
                ssh_ta = TextArea(
                    "\n".join(self._s.get("saved_ssh") or []),
                    id="inp-saved_ssh", classes="stg-input",
                )
                ssh_ta.styles.height = 6
                yield ssh_ta
            with Horizontal(id="settings-footer"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button("Save",   id="btn-save",   classes="btn-ok")

    def on_button_pressed(self, e: Button.Pressed):
        bid = e.button.id or ""
        if bid.startswith("tog-"):
            key = bid[4:]
            val = self._s.toggle(key)
            e.button.label = "  ON " if val else "  OFF"
            e.button.remove_class("stg-btn-on", "stg-btn-off")
            e.button.add_class("stg-btn-on" if val else "stg-btn-off")
            return
        if bid == "btn-save":
            for key, _, _ in self.TEXT_SETTINGS:
                try:
                    raw = self.query_one(f"#inp-{key}", Input).value.strip()
                    self._s.set(key, int(raw) if key == "preview_max_kb" else raw)
                except Exception:
                    pass
            try:
                raw_ssh = self.query_one("#inp-saved_ssh", TextArea).text.strip()
                self._s.set("saved_ssh", [l.strip() for l in raw_ssh.splitlines() if l.strip()])
            except Exception:
                pass
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, e):
        if e.key == "escape": self.dismiss(False)


# ─────────────────────────────────────────────────────────────────────────────
#  CommandModal
# ─────────────────────────────────────────────────────────────────────────────
class CommandModal(ModalScreen[Optional[str]]):
    def compose(self) -> ComposeResult:
        with Vertical(id="cmd-modal-box"):
            yield Label("  Command Bar  [dim]Enter = run  |  Esc = cancel[/dim]",
                        id="cmd-modal-title")
            yield Input(placeholder=":help  :settings  :new file.txt  :cd /path  :q",
                        id="cmd-modal-input", classes="modal-input")
            yield Static("[dim] :help  :settings  :hidden  :search  :shell  :edit  :preview[/dim]",
                         id="cmd-modal-hints")

    def on_mount(self): self.query_one("#cmd-modal-input", Input).focus()

    def on_input_submitted(self, e: Input.Submitted):
        self.dismiss(e.value.strip() or None)

    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
#  HelpModal
# ─────────────────────────────────────────────────────────────────────────────
_COMMANDS = [
    (":q / :quit",      "Exit the application"),
    (":h / :help",      "Show this help"),
    (":r / :reload",    "Reload current directory"),
    (":i / :info",      "Show file / folder details"),
    (":settings",       "Open settings panel"),
    (":hidden",         "Toggle dotfiles visibility"),
    (":new <n>",        "Create a new file"),
    (":mkdir <n>",      "Create a new folder"),
    (":rename <n>",     "Rename selected item"),
    (":del",            "Delete selected item"),
    (":chmod <octal>",  "Change permissions  e.g. :chmod 755"),
    (":search <q>",     "Recursive filename search"),
    (":copy",           "Copy selected to clipboard"),
    (":cut",            "Cut selected to clipboard"),
    (":paste",          "Paste clipboard here"),
    (":edit",           "Open file in built-in editor"),
    (":preview",        "Full-screen file preview"),
    (":shell",          "Open shell in current directory"),
    (":cd <path>",      "Navigate to a directory"),
]
_SHORTCUTS = [
    ("Space Space",  "Open command bar"),
    ("F2",           "Rename selected"),
    ("F5",           "Reload directory"),
    ("Delete",       "Delete selected"),
    ("Ctrl+N",       "New file"),
    ("Ctrl+Shift+N", "New folder"),
    ("Ctrl+C/X/V",  "Copy / Cut / Paste"),
    ("Ctrl+F",       "Search"),
    ("Ctrl+E",       "Edit file"),
    ("Ctrl+P",       "Preview file"),
    ("Ctrl+H",       "Toggle hidden files"),
    ("Ctrl+O",       "Open shell"),
    ("Esc",          "Close modal / clear clipboard"),
    ("Dbl-click",    "Open floating window"),
    ("Backspace",    "Go up one directory"),
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
        col  = max(len(c) for c, _ in _COMMANDS) + 2
        col2 = max(len(k) for k, _ in _SHORTCUTS) + 2
        out  = []
        out.append("[bold #4fc1ff]COMMANDS[/bold #4fc1ff]  [dim]prefix with colon[/dim]")
        out.append("")
        for cmd, desc in _COMMANDS:
            out.append("  [bold #9cdcfe]{:<{}}[/bold #9cdcfe]  [#d4d4d4]{}[/#d4d4d4]"
                       .format(cmd, col, desc))
        out.append("")
        out.append("[bold #4fc1ff]SHORTCUTS[/bold #4fc1ff]")
        out.append("")
        for key, desc in _SHORTCUTS:
            out.append("  [bold #ce9178]{:<{}}[/bold #ce9178]  [#d4d4d4]{}[/#d4d4d4]"
                       .format(key, col2, desc))
        out.append("")
        out.append("[bold #4fc1ff]FLOATING WINDOWS[/bold #4fc1ff]")
        out.append("")
        out.append("  Double-click any file or folder to open a draggable floating window.")
        out.append("  Inside a floating window:")
        out.append("    Esc / Space Space   Toggle window command bar")
        out.append("    :e                  Enter edit mode (text files)")
        out.append("    :s                  Save file")
        out.append("    :q                  Close window")
        out.append("    Ctrl+S              Save directly")
        out.append("    Drag title bar      Move window")
        out.append("    Drag bottom-right   Resize window")
        out.append("")
        out.append("[dim]Settings saved to  ~/.config/xtermfiles/settings.json[/dim]")
        return "\n".join(out)

    def on_button_pressed(self, _e: Button.Pressed): self.dismiss(None)
    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
#  SSHLoginModal
# ─────────────────────────────────────────────────────────────────────────────
class SSHLoginModal(ModalScreen[Optional[tuple[str, str]]]):
    def __init__(self, host: str, port: str):
        super().__init__()
        self.host = host; self.port = port

    def compose(self) -> ComposeResult:
        with Vertical(id="ssh-box", classes="dialog-box"):
            yield Label(f"SSH Login — {self.host}:{self.port}", classes="dialog-title")
            with Horizontal(classes="dialog-input-row"):
                yield Label("User:", classes="dialog-label")
                yield Input("root", id="ssh-user", classes="dialog-input")
            with Horizontal(classes="dialog-input-row"):
                yield Label("Pass:", classes="dialog-label")
                yield Input(password=True, id="ssh-pass", classes="dialog-input")
            with Horizontal(classes="dialog-btn-row"):
                yield Button("Cancel",  id="btn-cancel",  classes="btn-cancel")
                yield Button("Connect", id="btn-connect",  classes="btn-ok")

    def on_mount(self): self.query_one("#ssh-pass", Input).focus()

    def _submit(self):
        user = self.query_one("#ssh-user", Input).value
        pwd  = self.query_one("#ssh-pass", Input).value
        self.dismiss((user, pwd))

    def on_button_pressed(self, e: Button.Pressed):
        if e.button.id == "btn-connect": self._submit()
        else: self.dismiss(None)

    def on_input_submitted(self, _e: Input.Submitted): self._submit()

    def on_key(self, e):
        if e.key == "escape": self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
#  LoadingModal
# ─────────────────────────────────────────────────────────────────────────────
class LoadingModal(ModalScreen[None]):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="loading-box", classes="dialog-box"):
            yield Label(self.message, classes="dialog-title")
            with Horizontal(classes="dialog-btn-row"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")

    def on_button_pressed(self, _e: Button.Pressed): self.dismiss(None)