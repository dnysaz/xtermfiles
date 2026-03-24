"""
widgets.py — FileRow, FileListView, DetailStrip, FloatingWindow

xtermfiles — Terminal File Explorer

SSH freeze fixes applied:
    1. FloatingWindow.compose() no longer calls list_dir() directly.
       Directory listing is deferred to on_mount() via run_worker.
    2. DetailStrip.show_dir_summary() now has a remote-safe variant
       show_remote_dir() that never calls iterdir/stat.
    3. FileRow now accepts optional pre-fetched stat_result to avoid
       per-row stat() calls in the main thread when finishing a load.
"""

import time
from pathlib import Path
from typing import Optional
from textual.app import ComposeResult
from textual.widgets import ListView, ListItem, Label, Static, Button, Input, TextArea
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.reactive import reactive
from textual import events
from textual.widget import Widget
from rich.text import Text
from rich.syntax import Syntax
from helpers import (
    format_size, format_date, format_perms,
    get_owner, file_type_label,
    get_icon, get_mime, get_lang, is_text_file, list_dir, Settings,
)

TEXTUAL_LANGS = {
    "python", "javascript", "typescript", "html", "css", "markdown",
    "json", "sql", "bash", "rust", "go", "java", "c", "cpp", "regex",
    "yaml", "toml", "scss", "kotlin", "ruby", "php", "lua", "r",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Message: double-clicked a file in the main list
# ─────────────────────────────────────────────────────────────────────────────
class FileDoubleClicked(Message):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path


# ─────────────────────────────────────────────────────────────────────────────
#  FileRow — one row in the file list
# ─────────────────────────────────────────────────────────────────────────────
class FileRow(ListItem):
    class DoubleClicked(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    def __init__(self, path: Path, settings: Settings, stat_result=None, view_mode="list"):
        """
        stat_result: optional pre-fetched os.stat_result.
        If provided, compose() uses it directly and avoids a stat() call
        on the main thread (important for remote SSH paths where stat is slow).
        """
        super().__init__()
        self.path = path
        self._settings = settings
        self._stat_result = stat_result
        self._view_mode = view_mode
        self.add_class("file-row")
        self.add_class(f"mode-{view_mode}")

    def compose(self) -> ComposeResult:
        show_icons = self._settings.get("show_file_icons")
        date_fmt   = self._settings.get("date_format")

        if self._stat_result is not None:
            # Use pre-fetched stat to avoid any I/O on the main thread
            st       = self._stat_result
            size_str = format_size(st.st_size) if self.path.is_file() else ""
            date_str = format_date(st.st_mtime, date_fmt)
        else:
            try:
                st       = self.path.stat()
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
            name_text.append(name, style="#666666" if name.startswith(".") else "#d4d4d4")
        else:
            name_text.append(name, style="#666666" if name.startswith(".") else "#d4d4d4")

        if self._view_mode == "grid":
            # Grid layout: vertical stack icon + name
            with Vertical(classes="grid-inner"):
                yield Label(f"{icon}", classes="grid-icon")
                yield Label(name, classes="grid-name")
        else:
            # List layout: horizontal row
            yield Label(name_text, classes="row-name")
            yield Label(size_str, classes="row-size")
            yield Label(type_str, classes="row-type")
            yield Label(date_str, classes="row-date")

    def on_click(self, event: events.Click):
        if event.button == 1 and event.chain == 2:
            self.post_message(self.DoubleClicked(self.path))


# ─────────────────────────────────────────────────────────────────────────────
#  FileListView
# ─────────────────────────────────────────────────────────────────────────────
class FileListView(ListView):
    class FileSelected(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    class DirectoryEntered(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    view_mode: reactive[str] = reactive("list")

    def __init__(self, settings: Settings, **kwargs):
        super().__init__(**kwargs)
        self._settings    = settings
        self._current_dir: Optional[Path] = None
        self._entries: list[Path] = []
        self.view_mode = settings.get("view_mode") or "list"

    # ── Public API ────────────────────────────────────────────────────────

    def load_directory(self, path, show_hidden: bool = False):
        self._current_dir = path
        self.clear()
        self._entries = []
        self.append(ListItem(Label(" ⌛ Loading...")))
        self.run_worker(self._async_load(path, show_hidden), thread=True)

    async def _async_load(self, path, show_hidden: bool = False):
        """
        Background worker: fetch entries AND stat each one.
        Stat is batched here so FileRow.compose() never has to call stat()
        on the main thread — critical for SSH paths where stat is slow.
        """
        try:
            entries = list_dir(path, show_hidden)
            # Pre-fetch stat for each entry while still in the worker thread
            stat_map = {}
            for p in entries:
                try:
                    stat_map[p] = p.stat()
                except Exception:
                    stat_map[p] = None
            self.app.call_from_thread(self._finish_load, entries, stat_map)
        except Exception as e:
            msg = str(e)
            if "socket" in msg.lower() or "closed" in msg.lower():
                msg = "Connection lost. Try reconnecting."
            self.app.call_from_thread(self.app.notify, f"Load Error: {msg}", severity="error")
            self.app.call_from_thread(self.clear)

    def _finish_load(self, entries: list, stat_map: dict):
        self._entries = entries
        self.clear()
        if not entries:
            self.append(ListItem(Label(" (empty)")))
        else:
            for p in entries:
                # Pass pre-fetched stat to FileRow — no stat() in main thread
                self.append(FileRow(p, self._settings, stat_result=stat_map.get(p),
                                    view_mode=self.view_mode))

    def refresh_directory(self, show_hidden: bool = False):
        if self._current_dir:
            self.load_directory(self._current_dir, show_hidden)

    def watch_view_mode(self, old_mode: str, new_mode: str):
        self.remove_class(f"mode-{old_mode}")
        self.add_class(f"mode-{new_mode}")
        # Re-render all items by reloading directory (simplest way to swap layouts)
        self.refresh_directory(self.app.show_hidden)

    @property
    def selected_path(self) -> Optional[Path]:
        if self.index is not None and 0 <= self.index < len(self._entries):
            return self._entries[self.index]
        return None

    def try_select_path(self, path):
        try:
            self.index = self._entries.index(path)
        except (ValueError, AttributeError):
            pass

    # ── Events ────────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected):
        event.stop()
        path = self.selected_path
        if path:
            # Single click/selection: just select (and preview in cli.py)
            self.post_message(self.FileSelected(path))

    def on_file_row_double_clicked(self, event: FileRow.DoubleClicked):
        event.stop()
        self.post_message(FileDoubleClicked(event.path))

    def on_key(self, event: events.Key):
        if event.key == "enter":
            path = self.selected_path
            if path:
                # Enter key acts as "Open / Activate"
                self.post_message(FileDoubleClicked(path))
        elif event.key in ("s", "shift+enter"):
            # 's' or 'shift+enter' opens context menu
            self.app.run_worker(self.app.action_open_context_menu())
        if event.key in ("backspace", "left"):
            if self._current_dir and self._current_dir.parent != self._current_dir:
                self.post_message(self.DirectoryEntered(self._current_dir.parent))
            event.stop()
        elif event.key == "right":
            path = self.selected_path
            if path and path.is_dir():
                self.post_message(self.DirectoryEntered(path))
            event.stop()

    def on_mouse_down(self, event: events.MouseDown):
        # Button 3 is right-click in some environments
        if event.button == 3:
            # Select the item under the mouse if possible, then open menu
            self.app.run_worker(self.app.action_open_context_menu())


# ─────────────────────────────────────────────────────────────────────────────
#  Breadcrumbs — clickable path trail
# ─────────────────────────────────────────────────────────────────────────────
class BreadcrumbSegment(Label):
    """A single segment in the breadcrumb trail."""
    def __init__(self, name: str, path: Path):
        super().__init__(name)
        self.path = path
        self.add_class("breadcrumb-segment")

    def on_click(self, event: events.Click):
        self.post_message(Breadcrumbs.PathClicked(self.path))

class Breadcrumbs(Horizontal):
    """
    Displays a series of clickable path segments:
    home / user / Desktop
    """
    class PathClicked(Message):
        def __init__(self, path: Path):
            super().__init__()
            self.path = path

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._path: Optional[Path] = None

    def update_path(self, path: Path):
        self._path = path
        self.remove_children()
        
        # Build path segments
        segments = []
        curr = path
        while True:
            segments.append(curr)
            parent = curr.parent
            if parent == curr: break
            curr = parent
        
        segments.reverse()
        
        # Root special case (for UPath URLs)
        for i, p in enumerate(segments):
            name = p.name or str(p)
            if name.endswith("/"): name = name[:-1]
            if not name: name = "/"
            
            # Segment
            self.mount(BreadcrumbSegment(name, p))
            
            # Separator
            if i < len(segments) - 1:
                self.mount(Label(" / ", classes="breadcrumb-separator"))
        
        self.scroll_end(animate=False)

    def on_breadcrumb_segment_click(self, event: events.Click):
        # We handle this via the segment itself
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  DetailStrip — single-line info bar at the bottom
# ─────────────────────────────────────────────────────────────────────────────
class DetailStrip(Static):
    def __init__(self, settings: Settings, **kwargs):
        super().__init__("", **kwargs)
        self._settings = settings

    def show_path(self, path: Optional[Path]):
        """Show details for a local file/folder. Safe to call from main thread."""
        if path is None:
            self.update(""); return
        try:
            st       = path.stat()
            date_fmt = self._settings.get("date_format")
            show_ic  = self._settings.get("show_file_icons")
            icon     = get_icon(path, show_ic)
            text     = Text()
            text.append(f" {icon} " if icon else " ")
            text.append(path.name, "bold #4fc1ff" if path.is_dir() else "bold #d4d4d4")
            text.append(f" {file_type_label(path)}", "#888888")
            if path.is_file():
                text.append(f" {format_size(st.st_size)}", "#9cdcfe")
                text.append(f" {format_date(st.st_mtime, date_fmt)}", "#6a9955")
                text.append(f" {format_perms(st.st_mode)}", "#ce9178")
                text.append(f" {get_owner(st)}", "#c586c0")
            self.update(text)
        except Exception as e:
            self.update(f"[red]{e}[/red]")

    def show_dir_summary(self, path: Path, show_hidden: bool = False):
        """
        Show entry count summary for a LOCAL directory.
        Never call this with a remote SSH path — iterdir() would block main thread.
        Use show_remote_dir() instead for remote paths.
        """
        try:
            entries = list_dir(path, show_hidden)
            n_d = sum(1 for e in entries if e.is_dir())
            n_f = sum(1 for e in entries if e.is_file())
            t = Text()
            t.append(f" 📁 {path.name} ", "bold #4fc1ff")
            t.append(f"{n_d} folder{'s' if n_d != 1 else ''}, {n_f} file{'s' if n_f != 1 else ''}", "#888888")
            self.update(t)
        except Exception as e:
            self.update(f"[red]{e}[/red]")

    def show_remote_dir(self, path):
        """
        FIX: Lightweight placeholder for remote (SSH) directories.
        Does NOT call iterdir() or stat() — safe from main thread.
        """
        t = Text()
        t.append(" 🔗 ", "bold #9cdcfe")
        t.append(str(path), "bold #9cdcfe")
        t.append("  [remote — loading…]", "#888888")
        self.update(t)


# ─────────────────────────────────────────────────────────────────────────────
#  FloatingWindow — draggable, resizable, with per-window command bar
#
#  FIX: compose() no longer calls list_dir() directly for directories.
#       Directory listing is deferred to on_mount() via run_worker so it
#       never blocks the main thread (critical for remote SSH paths).
# ─────────────────────────────────────────────────────────────────────────────
class FloatingWindow(Widget):
    _next_id = 0

    class OpenPath(Message):
        def __init__(self, path):
            super().__init__()
            self.path = path

    def __init__(self, path, settings: Settings):
        FloatingWindow._next_id += 1
        self._wid = FloatingWindow._next_id
        super().__init__(id=f"fw-{self._wid}")
        self._path     = path
        self._settings = settings
        self._entries: list = []

        # Drag / resize state
        self._dragging = False
        self._resizing = False
        self._drag_sx = self._drag_sy = 0
        self._drag_ox = self._drag_oy = 0
        self._res_sx = self._res_sy = 0
        self._res_ow = self._res_oh = 0
        self._cur_w = 64
        self._cur_h = 22

        offset = (self._wid - 1) % 8
        self._px = 4 + offset * 3
        self._py = 2 + offset * 2

        # Editor state
        self._is_text    = path.is_file() and is_text_file(path)
        self._is_editing = False
        self._cmd_vis    = False
        self._last_space = 0.0

    def compose(self) -> ComposeResult:
        icon = "📁" if self._path.is_dir() else "F"
        with Vertical():
            with Horizontal(classes="fw-titlebar", id=f"fw-tb-{self._wid}"):
                yield Static(f" {icon} {self._path.name}", classes="fw-title-label",
                             id=f"fw-tl-{self._wid}")
                if self._is_text:
                    yield Static(" READ", classes="fw-mode-label",
                                 id=f"fw-ml-{self._wid}")
                yield Button("x", classes="fw-close-btn")

            if self._path.is_dir():
                # FIX: yield an empty ListView; populate it in on_mount via worker
                yield ListView(classes="fw-list", id=f"fw-lv-{self._wid}")

            elif self._is_text:
                try:
                    content = self._path.read_text(errors="replace")
                except Exception:
                    content = ""
                lang     = get_lang(self._path)
                use_lang = lang if lang in TEXTUAL_LANGS else None
                yield TextArea(content, language=use_lang, theme="vscode_dark",
                               read_only=True, id=f"fw-ta-{self._wid}",
                               classes="fw-editor")

            else:
                with ScrollableContainer(classes="fw-content"):
                    yield Static(self._file_info(), classes="fw-preview")

            yield Input(
                placeholder=":e edit :s save :q close",
                id=f"fw-cmd-{self._wid}",
                classes="fw-cmd-input",
            )
            yield Static("◢", classes="fw-resize-handle")

    def on_mount(self):
        self.styles.offset = (self._px, self._py)
        self.styles.width  = self._cur_w
        self.styles.height = self._cur_h

        # Hide command bar
        try:
            self.query_one(f"#fw-cmd-{self._wid}", Input).display = False
        except Exception:
            pass

        # FIX: load directory listing in background thread
        if self._path.is_dir():
            self._load_dir_async()

    def _load_dir_async(self):
        """Kick off a background worker to load directory contents."""
        def worker():
            try:
                show_hidden = self._settings.get("show_hidden")
                entries     = list_dir(self._path, show_hidden)
                self.app.call_from_thread(self._finish_dir_load, entries)
            except Exception as e:
                self.app.call_from_thread(
                    lambda: self.app.notify(f"Floating window load error: {e}", severity="error")
                )

        self.run_worker(worker, thread=True)

    def _finish_dir_load(self, entries: list):
        """Called from main thread after background listing is done."""
        self._entries = entries
        show_ic = self._settings.get("show_file_icons")
        try:
            lv = self.query_one(f"#fw-lv-{self._wid}", ListView)
            lv.clear()
            for entry in entries:
                ic = get_icon(entry, show_ic)
                t  = Text()
                if entry.is_dir():
                    t.append(f"{ic} ", "#4fc1ff")
                    t.append(entry.name, "bold #4fc1ff")
                elif ic.strip():
                    t.append(f"[{ic}] ", "#6a9955")
                    t.append(entry.name, "#d4d4d4")
                else:
                    t.append(entry.name, "#d4d4d4")
                lv.append(ListItem(Label(t)))
        except Exception:
            pass

    def _file_info(self) -> str:
        try:
            st = self._path.stat()
            return (
                f"[bold]{self._path.name}[/bold]\n\n"
                f"Type : {file_type_label(self._path)}\n"
                f"Size : {format_size(st.st_size)}\n"
                f"MIME : {get_mime(self._path)}\n"
                f"Modified: {format_date(st.st_mtime)}\n"
            )
        except Exception as e:
            return f"[red]{e}[/red]"

    # ── Command bar ───────────────────────────────────────────────────────

    def _show_cmd(self):
        try:
            inp = self.query_one(f"#fw-cmd-{self._wid}", Input)
            inp.display = True
            inp.value   = ""
            inp.focus()
            self._cmd_vis = True
        except Exception:
            pass

    def _hide_cmd(self):
        try:
            inp = self.query_one(f"#fw-cmd-{self._wid}", Input)
            inp.display = False
            self._cmd_vis = False
        except Exception:
            pass
        try:
            self.query_one(f"#fw-ta-{self._wid}", TextArea).focus()
        except Exception:
            try:
                self.query_one(f"#fw-lv-{self._wid}", ListView).focus()
            except Exception:
                pass

    def _run_cmd(self, raw: str):
        cmd = raw.strip().lstrip(":").lower()
        if cmd in ("e", "edit"):
            self._enter_edit()
        elif cmd in ("s", "save"):
            self._save()
        elif cmd in ("q", "quit", "close"):
            self.remove()
        else:
            self.app.notify(f"Unknown: {raw}", severity="warning")

    def _enter_edit(self):
        if not self._is_text:
            self.app.notify("Cannot edit binary files", severity="warning"); return
        try:
            ta = self.query_one(f"#fw-ta-{self._wid}", TextArea)
            ta.read_only     = False
            self._is_editing = True
            self._set_mode(" EDIT")
            ta.focus()
        except Exception:
            pass

    def _save(self):
        if not self._is_editing:
            self.app.notify("Not in edit mode — press :e first", severity="warning"); return
        try:
            ta = self.query_one(f"#fw-ta-{self._wid}", TextArea)
            self._path.write_text(ta.text)
            self.app.notify(f"Saved: {self._path.name}")
        except Exception as e:
            self.app.notify(f"Save failed: {e}", severity="error")

    def _set_mode(self, text: str):
        try:
            self.query_one(f"#fw-ml-{self._wid}", Static).update(text)
        except Exception:
            pass

    # ── Keys ──────────────────────────────────────────────────────────────

    def on_key(self, event: events.Key):
        if event.key == "ctrl+s" and self._is_editing:
            self._save(); event.stop(); return

        if event.key == "escape":
            if self._cmd_vis:
                self._hide_cmd()
            else:
                self._show_cmd()
            event.stop(); return

        if event.key == "space":
            focused = self.app.focused
            try:
                if focused == self.query_one(f"#fw-cmd-{self._wid}", Input):
                    return
            except Exception:
                pass
            if self._is_editing:
                try:
                    if focused == self.query_one(f"#fw-ta-{self._wid}", TextArea):
                        return
                except Exception:
                    pass
            now = time.monotonic()
            if now - self._last_space < 0.45:
                self._show_cmd()
                self._last_space = 0.0
            else:
                self._last_space = now
            event.stop()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == f"fw-cmd-{self._wid}":
            event.stop()
            val = event.value.strip()
            self._hide_cmd()
            if val:
                self._run_cmd(val)

    # ── Drag & Resize ─────────────────────────────────────────────────────

    def on_mouse_down(self, event: events.MouseDown):
        if event.button != 1:
            return
        h = self._cur_h
        w = self._cur_w
        if event.y >= h - 1 and event.x >= w - 3:
            self._resizing = True
            self._res_sx, self._res_sy = event.screen_x, event.screen_y
            self._res_ow, self._res_oh = self._cur_w, self._cur_h
            self.capture_mouse(); event.stop()
        elif event.y == 0:
            self._dragging = True
            self._drag_sx, self._drag_sy = event.screen_x, event.screen_y
            self._drag_ox, self._drag_oy = self._px, self._py
            self.capture_mouse(); event.stop()

    def on_mouse_move(self, event: events.MouseMove):
        if self._dragging:
            self._px = self._drag_ox + (event.screen_x - self._drag_sx)
            self._py = self._drag_oy + (event.screen_y - self._drag_sy)
            self.styles.offset = (self._px, self._py)
            event.stop()
        elif self._resizing:
            self._cur_w = max(30, self._res_ow + (event.screen_x - self._res_sx))
            self._cur_h = max(8,  self._res_oh + (event.screen_y - self._res_sy))
            self.styles.width  = self._cur_w
            self.styles.height = self._cur_h
            event.stop()

    def on_mouse_up(self, event: events.MouseUp):
        if self._dragging or self._resizing:
            self._dragging = self._resizing = False
            self.release_mouse(); event.stop()

    # ── Close button ──────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed):
        if "fw-close-btn" in event.button.classes:
            self.remove(); event.stop()

    # ── Directory item click → new window ─────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected):
        event.stop()
        lv = event.list_view
        if lv.index is not None and 0 <= lv.index < len(self._entries):
            self.post_message(self.OpenPath(self._entries[lv.index]))