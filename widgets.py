"""
widgets.py — Custom widgets: FileRow, FileListView, DetailStrip
"""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.widgets import ListView, ListItem, Label, Static
from textual.message import Message
from textual import events
from rich.text import Text

from helpers import (
    format_size, format_date, format_perms,
    get_owner, file_type_label,
    get_icon, get_mime, list_dir, Settings,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Internal message: user double-clicked a file (not a directory)
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

        # Build name column: [icon] name
        name_text = Text(overflow="ellipsis", no_wrap=True)
        if self.path.is_dir():
            # folder icon stays as-is (emoji preserved)
            name_text.append(f"{icon} ", style="#4fc1ff")
            name_text.append(name, style="bold #4fc1ff")
        elif self.path.is_symlink():
            name_text.append(f"{icon} ", style="#c586c0")
            name_text.append(name, style="italic #c586c0")
        elif show_icons and icon.strip():
            # text icon in muted brackets
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
        # Double-click detection: chain == 2 means second click
        if event.button == 1 and event.chain == 2:
            self.post_message(self.DoubleClicked(self.path))


# ─────────────────────────────────────────────────────────────────────────────
#  FileListView — right-panel file list (Windows Explorer style)
# ─────────────────────────────────────────────────────────────────────────────
class FileListView(ListView):
    """
    ListView wrapping FileRows.
    Emits FileSelected / DirectoryEntered / FileDoubleClicked messages.
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

    # ── Public API ────────────────────────────────────────────────────────
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
        """Highlight the row matching `path` if present."""
        try:
            idx = self._entries.index(path)
            self.index = idx
        except (ValueError, AttributeError):
            pass

    # ── Events ────────────────────────────────────────────────────────────
    def on_list_view_selected(self, event: ListView.Selected):
        event.stop()
        path = self.selected_path
        if path:
            self.post_message(self.FileSelected(path))

    def on_file_row_double_clicked(self, event: FileRow.DoubleClicked):
        event.stop()
        if event.path.is_dir():
            self.post_message(self.DirectoryEntered(event.path))
        else:
            self.post_message(FileDoubleClicked(event.path))

    def on_key(self, event: events.Key):
        if event.key == "enter":
            path = self.selected_path
            if path and path.is_dir():
                self.post_message(self.DirectoryEntered(path))
                event.stop()
        elif event.key == "backspace":
            if self._current_dir and self._current_dir.parent != self._current_dir:
                self.post_message(self.DirectoryEntered(self._current_dir.parent))
                event.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  DetailStrip — bottom info bar (2 lines)
# ─────────────────────────────────────────────────────────────────────────────
class DetailStrip(Static):
    """Shows brief metadata for the selected item at the bottom of the panel."""

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