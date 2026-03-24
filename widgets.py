"""
widgets.py — Custom widgets: FileRow, FileListView, DetailStrip, FloatingWindow
xtermfiles — Terminal File Explorer
"""

import time
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import ListView, ListItem, Label, Static, Button, Input, TextArea
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual import events
from rich.text import Text
from rich.syntax import Syntax

from helpers import (
    format_size, format_date, format_perms,
    get_owner, file_type_label,
    get_icon, get_mime, get_lang, is_text_file, list_dir, Settings,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Internal message: user double-clicked a file or folder
# ─────────────────────────────────────────────────────────────────────────────
class FileDoubleClicked(Message):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path


# ─────────────────────────────────────────────────────────────────────────────
#  FileRow — one row in the file list
# ─────────────────────────────────────────────────────────────────────────────
class FileRow(ListItem):
    """One file/folder row with icon, name, size, type, date columns."""

    class DoubleClicked(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    def __init__(self, path: Path, settings: Settings):
        super().__init__()
        self.path = path
        self._settings = settings
        self.add_class("file-row")

    def compose(self) -> ComposeResult:
        show_icons = self._settings.get("show_file_icons")
        date_fmt   = self._settings.get("date_format")
        try:
            st = self.path.stat()
            size_str = format_size(st.st_size) if self.path.is_file() else ""
            date_str = format_date(st.st_mtime, date_fmt)
        except OSError:
            size_str = ""
            date_str = "—"

        icon     = get_icon(self.path, show_icons)
        name     = self.path.name
        type_str = file_type_label(self.path)

        name_text = Text(overflow="ellipsis", no_wrap=True)
        if self.path.is_dir():
            name_text.append(f"{icon} ", style="#4fc1ff")
            name_text.append(name, style="bold #4fc1ff")
        elif self.path.is_symlink():
            name_text.append(f"{icon} ", style="#c586c0")
            name_text.append(name, style="italic #c586c0")
        elif show_icons and icon.strip():
            name_text.append("[", style="#555555")
            name_text.append(icon, style="#6a9955")
            name_text.append("] ", style="#555555")
            if self.path.name.startswith("."):
                name_text.append(name, style="#666666")
            else:
                name_text.append(name, style="#d4d4d4")
        else:
            if self.path.name.startswith("."):
                name_text.append(name, style="#666666")
            else:
                name_text.append(name, style="#d4d4d4")

        yield Label(name_text, classes="row-name")
        yield Label(size_str,  classes="row-size")
        yield Label(type_str,  classes="row-type")
        yield Label(date_str,  classes="row-date")

    def on_click(self, event: events.Click):
        if event.button == 1 and event.chain == 2:
            self.post_message(self.DoubleClicked(self.path))


# ─────────────────────────────────────────────────────────────────────────────
#  FileListView — right-panel file list
# ─────────────────────────────────────────────────────────────────────────────
class FileListView(ListView):
    """
    Single click on folder = enter it.
    Single click on file = select it.
    Double click = open floating window.
    """

    class FileSelected(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    class DirectoryEntered(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    def __init__(self, settings: Settings, **kwargs):
        super().__init__(**kwargs)
        self._settings = settings
        self._current_dir: Optional[Path] = None
        self._entries: list[Path] = []

    def load_directory(self, path: Path, show_hidden: bool = False):
        self._current_dir = path
        self._entries = list_dir(path, show_hidden)
        self.clear()
        for p in self._entries:
            self.append(FileRow(p, self._settings))

    def refresh_directory(self, show_hidden: bool = False):
        if self._current_dir:
            self.load_directory(self._current_dir, show_hidden)

    @property
    def selected_path(self) -> Optional[Path]:
        if self.index is not None and 0 <= self.index < len(self._entries):
            return self._entries[self.index]
        return None

    @property
    def current_dir(self) -> Optional[Path]:
        return self._current_dir

    def try_select_path(self, path: Path):
        try:
            idx = self._entries.index(path)
            self.index = idx
        except (ValueError, AttributeError):
            pass

    def on_list_view_selected(self, event: ListView.Selected):
        event.stop()
        path = self.selected_path
        if path:
            if path.is_dir():
                self.post_message(self.DirectoryEntered(path))
            else:
                self.post_message(self.FileSelected(path))

    def on_file_row_double_clicked(self, event: FileRow.DoubleClicked):
        event.stop()
        self.post_message(FileDoubleClicked(event.path))

    def on_key(self, event: events.Key):
        if event.key == "backspace" or event.key == "left":
            if self._current_dir and self._current_dir.parent != self._current_dir:
                self.post_message(self.DirectoryEntered(self._current_dir.parent))
                event.stop()
        elif event.key == "right":
            path = self.selected_path
            if path and path.is_dir():
                self.post_message(self.DirectoryEntered(path))
                event.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  DetailStrip — bottom info bar
# ─────────────────────────────────────────────────────────────────────────────
class DetailStrip(Static):
    def __init__(self, settings: Settings, **kwargs):
        super().__init__("", **kwargs)
        self._settings = settings

    def show_path(self, path: Optional[Path]):
        if path is None:
            self.update(""); return
        try:
            st = path.stat()
            date_fmt = self._settings.get("date_format")
            show_icons = self._settings.get("show_file_icons")
            icon = get_icon(path, show_icons)
            text = Text()
            text.append(f" {icon} " if icon else " ")
            text.append(path.name,
                "bold #4fc1ff" if path.is_dir() else "bold #d4d4d4")
            text.append(f"   {file_type_label(path)}", "#888888")
            if path.is_file():
                text.append(f"   Size: {format_size(st.st_size)}", "#9cdcfe")
            text.append(f"   Modified: {format_date(st.st_mtime, date_fmt)}", "#6a9955")
            text.append(f"   {format_perms(st.st_mode)}", "#ce9178")
            text.append(f"   {get_owner(st)}", "#c586c0")
            if path.is_file():
                text.append(f"   {get_mime(path)}", "#888888")
            self.update(text)
        except Exception as e:
            self.update(f"[red]{e}[/red]")

    def show_dir_summary(self, path: Path, show_hidden: bool = False):
        entries = list_dir(path, show_hidden)
        n_dirs  = sum(1 for e in entries if e.is_dir())
        n_files = sum(1 for e in entries if e.is_file())
        text = Text()
        text.append(f" 📁 {path.name}   ", "bold #4fc1ff")
        text.append(f"{n_dirs} folder{'s' if n_dirs != 1 else ''}, "
                    f"{n_files} file{'s' if n_files != 1 else ''}", "#888888")
        self.update(text)


# ─────────────────────────────────────────────────────────────────────────────
#  FloatingWindow — draggable, resizable, editable floating window
# ─────────────────────────────────────────────────────────────────────────────
TEXTUAL_LANGS = {
    "python", "javascript", "typescript", "html", "css", "markdown",
    "json", "sql", "bash", "rust", "go", "java", "c", "cpp", "regex",
}


class FloatingWindow(Widget):
    """
    Draggable, resizable floating window.
    - Folders: shows directory listing, click item → new window
    - Files: shows content in read mode, :e to edit, :s to save, :q to close
    - Double-space or Escape → command bar
    """

    _next_id = 0

    class OpenPath(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    def __init__(self, path: Path, settings: Settings):
        FloatingWindow._next_id += 1
        self._wid = FloatingWindow._next_id
        super().__init__(id=f"fw-{self._wid}")
        self._path = path
        self._settings = settings
        self._entries: list[Path] = []
        # Drag state
        self._dragging = False
        self._drag_start_screen = (0, 0)
        self._drag_start_pos = (0, 0)
        # Resize state
        self._resizing = False
        self._resize_start_screen = (0, 0)
        self._resize_start_size = (64, 22)
        self._cur_width = 64
        self._cur_height = 22
        # Position (staggered)
        self._pos_x = 4 + (self._wid % 6) * 3
        self._pos_y = 2 + (self._wid % 6) * 2
        # Edit state
        self._is_editing = False
        self._is_text = path.is_file() and is_text_file(path)
        # Command bar state
        self._last_space_time: float = 0.0
        self._cmd_visible = False

    def compose(self) -> ComposeResult:
        icon = "📁" if self._path.is_dir() else "📄"
        mode_text = "  READ" if self._is_text else ""
        with Vertical():
            # Title bar
            with Horizontal(classes="fw-titlebar"):
                yield Static(
                    f" {icon} {self._path.name}",
                    classes="fw-title-label",
                    id=f"fw-title-{self._wid}",
                )
                if self._is_text:
                    yield Static(mode_text, classes="fw-mode-label",
                                 id=f"fw-mode-{self._wid}")
                yield Button("✕", classes="fw-close-btn")

            # Content area
            if self._path.is_dir():
                self._entries = list_dir(
                    self._path, self._settings.get("show_hidden")
                )
                show_icons = self._settings.get("show_file_icons")
                items: list[ListItem] = []
                for entry in self._entries:
                    eicon = get_icon(entry, show_icons)
                    name_text = Text()
                    if entry.is_dir():
                        name_text.append(f"{eicon} ", "#4fc1ff")
                        name_text.append(entry.name, "bold #4fc1ff")
                    elif eicon.strip():
                        name_text.append(f"[{eicon}] ", "#6a9955")
                        name_text.append(entry.name, "#d4d4d4")
                    else:
                        name_text.append(entry.name, "#d4d4d4")
                    items.append(ListItem(Label(name_text)))
                yield ListView(*items, classes="fw-list")
            elif self._is_text:
                # Text file: use TextArea (read-only initially)
                try:
                    content = self._path.read_text(errors="replace")
                except Exception:
                    content = ""
                lang = get_lang(self._path)
                use_lang = lang if lang in TEXTUAL_LANGS else None
                yield TextArea(
                    content, language=use_lang, read_only=True,
                    id=f"fw-ta-{self._wid}", classes="fw-editor",
                )
            else:
                # Binary / non-text file: static preview
                with ScrollableContainer(classes="fw-content"):
                    yield Static(self._build_file_preview(), classes="fw-preview")

            # Command input (hidden by default, toggled with double-space/Esc)
            yield Input(
                placeholder=":e edit  :s save  :q close",
                id=f"fw-cmd-{self._wid}",
                classes="fw-cmd-input",
            )
            # Resize handle
            yield Static("◢", classes="fw-resize-handle")

    def _build_file_preview(self):
        path = self._path
        try:
            st = path.stat()
            return (
                f"[bold yellow]📄 {path.name}[/bold yellow]\n\n"
                f"Type    : {file_type_label(path)}\n"
                f"Size    : {format_size(st.st_size)}\n"
                f"MIME    : {get_mime(path)}\n"
                f"Modified: {format_date(st.st_mtime)}\n"
            )
        except Exception as e:
            return f"[red]Cannot read file info: {e}[/red]"

    def on_mount(self):
        self.styles.offset = (self._pos_x, self._pos_y)

    # ── Command bar ───────────────────────────────────────────────────────
    def _show_cmd_input(self):
        try:
            cmd = self.query_one(f"#fw-cmd-{self._wid}", Input)
            cmd.display = True
            cmd.value = ""
            cmd.focus()
            self._cmd_visible = True
        except Exception:
            pass

    def _hide_cmd_input(self):
        try:
            cmd = self.query_one(f"#fw-cmd-{self._wid}", Input)
            cmd.display = False
            self._cmd_visible = False
            # Refocus the text area or list
            if self._is_text:
                self.query_one(f"#fw-ta-{self._wid}", TextArea).focus()
            else:
                try:
                    self.query_one(".fw-list", ListView).focus()
                except Exception:
                    pass
        except Exception:
            pass

    def _handle_fw_command(self, raw: str):
        cmd = raw.strip().lstrip(":").lower()
        if cmd in ("e", "edit"):
            self._enter_edit_mode()
        elif cmd in ("s", "save"):
            self._save_file()
        elif cmd in ("q", "quit"):
            self.remove()
        else:
            self.app.notify(f"Unknown window command: {raw}", severity="warning")

    def _enter_edit_mode(self):
        if not self._is_text:
            self.app.notify("Cannot edit non-text files", severity="warning")
            return
        try:
            ta = self.query_one(f"#fw-ta-{self._wid}", TextArea)
            ta.read_only = False
            self._is_editing = True
            self._update_mode_label("  EDIT")
            ta.focus()
        except Exception:
            pass

    def _save_file(self):
        if not self._is_text or not self._is_editing:
            self.app.notify("Not in edit mode", severity="warning")
            return
        try:
            ta = self.query_one(f"#fw-ta-{self._wid}", TextArea)
            self._path.write_text(ta.text)
            self.app.notify(f"Saved: {self._path.name}")
            # Stay in edit mode after saving
        except Exception as e:
            self.app.notify(f"Save failed: {e}", severity="error")

    def _update_mode_label(self, text: str):
        try:
            label = self.query_one(f"#fw-mode-{self._wid}", Static)
            label.update(text)
        except Exception:
            pass

    # ── Key handling ──────────────────────────────────────────────────────
    def on_key(self, event: events.Key):
        # Ctrl+S = save directly
        if event.key == "ctrl+s" and self._is_editing:
            self._save_file()
            event.stop()
            return

        # Escape = toggle command bar
        if event.key == "escape":
            if self._cmd_visible:
                self._hide_cmd_input()
            else:
                self._show_cmd_input()
            event.stop()
            return

        # Double-space = toggle command bar (only if not editing / not in Input)
        if event.key == "space":
            focused = self.app.focused
            # Let space pass if typing in the command input
            try:
                cmd = self.query_one(f"#fw-cmd-{self._wid}", Input)
                if focused == cmd:
                    return
            except Exception:
                pass
            # Let space pass if TextArea is in edit mode
            if self._is_editing:
                try:
                    ta = self.query_one(f"#fw-ta-{self._wid}", TextArea)
                    if focused == ta:
                        return
                except Exception:
                    pass

            now = time.monotonic()
            if now - self._last_space_time < 0.45:
                self._show_cmd_input()
                event.stop()
                self._last_space_time = 0.0
                return
            self._last_space_time = now
            event.stop()  # Prevent reaching main app's double-space
            return

    # ── Input submitted (command bar) ─────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == f"fw-cmd-{self._wid}":
            event.stop()
            val = event.value.strip()
            self._hide_cmd_input()
            if val:
                self._handle_fw_command(val)

    # ── Dragging & Resizing ───────────────────────────────────────────────
    def on_mouse_down(self, event: events.MouseDown):
        if event.button != 1:
            return
        h = self.size.height
        w = self.size.width
        # Bottom-right corner = resize
        if event.y >= h - 1 and event.x >= w - 3:
            self._resizing = True
            self._resize_start_screen = (event.screen_x, event.screen_y)
            self._resize_start_size = (self._cur_width, self._cur_height)
            self.capture_mouse()
            event.stop()
        # Title bar = drag
        elif event.y == 0:
            self._dragging = True
            self._drag_start_screen = (event.screen_x, event.screen_y)
            self._drag_start_pos = (self._pos_x, self._pos_y)
            self.capture_mouse()
            event.stop()

    def on_mouse_move(self, event: events.MouseMove):
        if self._dragging:
            dx = event.screen_x - self._drag_start_screen[0]
            dy = event.screen_y - self._drag_start_screen[1]
            self._pos_x = self._drag_start_pos[0] + dx
            self._pos_y = self._drag_start_pos[1] + dy
            self.styles.offset = (self._pos_x, self._pos_y)
            event.stop()
        elif self._resizing:
            dx = event.screen_x - self._resize_start_screen[0]
            dy = event.screen_y - self._resize_start_screen[1]
            new_w = max(30, self._resize_start_size[0] + dx)
            new_h = max(8, self._resize_start_size[1] + dy)
            self._cur_width = new_w
            self._cur_height = new_h
            self.styles.width = new_w
            self.styles.height = new_h
            event.stop()

    def on_mouse_up(self, event: events.MouseUp):
        if self._dragging:
            self._dragging = False
            self.release_mouse()
            event.stop()
        elif self._resizing:
            self._resizing = False
            self.release_mouse()
            event.stop()

    # ── Close button ──────────────────────────────────────────────────────
    def on_button_pressed(self, event: Button.Pressed):
        if "fw-close-btn" in event.button.classes:
            self.remove()
            event.stop()

    # ── Clicking items inside directory window → new window ───────────────
    def on_list_view_selected(self, event: ListView.Selected):
        event.stop()
        lv = event.list_view
        if lv.index is not None and 0 <= lv.index < len(self._entries):
            self.post_message(self.OpenPath(self._entries[lv.index]))