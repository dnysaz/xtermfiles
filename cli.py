"""
cli.py — Ketut's File Explorer  (entry point)

Run:
    python cli.py              # opens home directory
    python cli.py /var/www     # opens a specific path

Commands (prefix with colon):
    :q  :quit      Exit          :h  :help      Help
    :r  :reload    Reload        :i  :info      File info
    :settings      Settings      :hidden        Toggle dotfiles
    :new <n>    New file         :mkdir <n>  New folder
    :rename <n> Rename           :del           Delete
    :chmod <o>  Permissions      :search <q>    Search
    :copy  :cut  :paste          Clipboard ops
    :edit          Editor        :preview       Preview
    :shell         Shell         :cd <path>     Navigate

Keyboard:
    F2 Rename  F5 Reload  Del Delete  Ctrl+N New file
    Ctrl+Shift+N New folder  Ctrl+C/X/V Copy/Cut/Paste
    Ctrl+F Search  Ctrl+E Edit  Ctrl+P Preview
    Ctrl+H Toggle hidden  Ctrl+O Shell  Esc Clear cb
"""

import os
import sys
import time
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, DirectoryTree, Static, Input, Label, Button
)
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.reactive import reactive
from textual.css.query import NoMatches
from textual import events
from rich.text import Text

from helpers import (
    APP_CSS, Clipboard, Settings,
    format_size, format_date, format_perms,
    get_owner, get_group, file_type_label,
    is_text_file, md5_file, list_dir,
)
from modals import (
    InputModal, ConfirmModal, SearchModal,
    TextEditorModal, FilePreviewModal, SettingsModal, HelpModal,
    CommandModal,
)
from widgets import FileListView, DetailStrip, FileDoubleClicked


EXTRA_CSS = """
.editor-box  { width: 100%; height: 100%; border: none; padding: 0; }
#preview-box { width: 100%; height: 100%; border: none; padding: 0; }
#editor-area { height: 1fr; border: none; }
"""


# ---------------------------------------------------------------------------
#  FilteredDirectoryTree
#  Overrides filter_paths() — the ONLY reliable way to hide dotfiles in
#  Textual's DirectoryTree (setting .show_hidden after mount does not work).
# ---------------------------------------------------------------------------
class FilteredDirectoryTree(DirectoryTree):
    """DirectoryTree that hides dotfiles via filter_paths unless _show_hidden."""

    def __init__(self, path: str, show_hidden: bool = False, **kwargs):
        super().__init__(path, **kwargs)
        self._show_hidden = show_hidden

    def filter_paths(self, paths):
        if self._show_hidden:
            return paths
        return [p for p in paths if not p.name.startswith(".")]

    def set_show_hidden(self, value: bool):
        self._show_hidden = value
        self.reload()


# ---------------------------------------------------------------------------
#  FileExplorer — main app
# ---------------------------------------------------------------------------
class FileExplorer(App):
    TITLE = "Ketut's File Explorer"
    CSS = APP_CSS + EXTRA_CSS

    BINDINGS = [
        Binding("f5",           "reload",        "Reload",     show=True),
        Binding("ctrl+h",       "toggle_hidden", "Hidden",     show=True),
        Binding("ctrl+f",       "open_search",   "Search",     show=True),
        Binding("ctrl+n",       "new_file",      "New File",   show=True),
        Binding("ctrl+shift+n", "new_dir",       "New Folder", show=False),
        Binding("f2",           "rename_item",   "Rename",     show=True),
        Binding("delete",       "delete_item",   "Delete",     show=True),
        Binding("ctrl+c",       "copy_item",     "Copy",       show=True),
        Binding("ctrl+x",       "cut_item",      "Cut",        show=True),
        Binding("ctrl+v",       "paste_item",    "Paste",      show=True),
        Binding("ctrl+e",       "edit_file",     "Edit",       show=True),
        Binding("ctrl+p",       "preview_file",  "Preview",    show=False),
        Binding("ctrl+o",       "open_shell",    "Shell",      show=False),
        Binding("escape",       "escape_action", "Cancel",     show=False),
        Binding("tab",          "focus_next",    "Tab",        show=False),
    ]

    show_hidden: reactive[bool] = reactive(False)

    def __init__(self, start_path: Optional[Path] = None):
        super().__init__()
        self._settings  = Settings()
        self._clipboard = Clipboard()

        # Resolve start directory
        if start_path is None:
            sp = self._settings.get("start_path") or "~"
            start_path = Path(sp).expanduser()
        self._root = start_path.resolve()
        self._cwd: Path = self._root
        self._selected: Optional[Path] = None

        # Read show_hidden from saved settings (default False)
        self.show_hidden = bool(self._settings.get("show_hidden"))
        self._last_space_time: float = 0.0   # for double-space detection

    # ------------------------------------------------------------------
    #  Layout
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="toolbar"):
            yield Input(value=str(self._cwd), placeholder="Path...",
                        id="addressbar")

        with Horizontal(id="layout"):
            # Left panel — uses FilteredDirectoryTree so dots are gone from
            # the very first render, before on_mount fires.
            with Vertical(id="left-panel"):
                yield Static("   FOLDERS", id="left-title")
                yield FilteredDirectoryTree(
                    str(self._root),
                    show_hidden=self.show_hidden,
                    id="tree-view",
                )

            # Right panel
            with Vertical(id="right-panel"):
                with Horizontal(id="col-header"):
                    yield Static("   Name",      classes="col-name")
                    yield Static("Size",          classes="col-size")
                    yield Static("Type",          classes="col-type")
                    yield Static("Date Modified", classes="col-date")

                yield FileListView(self._settings, id="file-list")
                yield DetailStrip(self._settings, id="detail-strip")

        # Status bar only — clean, no shortcut clutter
        yield Static("", id="statusbar")

    def on_mount(self):
        self._load_dir(self._cwd)
        self.query_one("#file-list", FileListView).focus()

    # ------------------------------------------------------------------
    #  Directory loading
    # ------------------------------------------------------------------
    def _load_dir(self, path: Path):
        self._cwd = path.resolve()
        fl = self.query_one("#file-list", FileListView)
        fl.load_directory(self._cwd, self.show_hidden)
        self._selected = None
        self._update_addressbar()
        self._refresh_status()
        self.query_one("#detail-strip", DetailStrip).show_dir_summary(
            self._cwd, self.show_hidden
        )

    def _update_addressbar(self):
        try:
            self.query_one("#addressbar", Input).value = str(self._cwd)
        except NoMatches:
            pass

    def _refresh_status(self):
        cb_txt   = f"  |  {self._clipboard.label}" if self._clipboard.has_item else ""
        hid_txt  = "  |  hidden on" if self.show_hidden else ""
        entries  = list_dir(self._cwd, self.show_hidden)
        n_dir    = sum(1 for e in entries if e.is_dir())
        n_file   = sum(1 for e in entries if e.is_file())
        text = Text()
        text.append(
            f" {n_dir} folder{'s' if n_dir != 1 else ''}, "
            f"{n_file} file{'s' if n_file != 1 else ''}", "#ffffff"
        )
        text.append(cb_txt,  "#ffe08a")
        text.append(hid_txt, "#c0c0c0")
        text.append("   Press Space twice to open command bar", "#c0e0ff")
        try:
            self.query_one("#statusbar", Static).update(text)
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    #  Events — left tree
    # ------------------------------------------------------------------
    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ):
        event.stop()
        self._load_dir(Path(event.path))
        self.query_one("#file-list", FileListView).focus()

    # ------------------------------------------------------------------
    #  Events — right file list
    # ------------------------------------------------------------------
    def on_file_list_view_file_selected(self, event: FileListView.FileSelected):
        self._selected = event.path
        self.query_one("#detail-strip", DetailStrip).show_path(event.path)
        self._refresh_status()

    def on_file_list_view_directory_entered(
        self, event: FileListView.DirectoryEntered
    ):
        self._load_dir(event.path)

    def on_file_double_clicked(self, event: FileDoubleClicked):
        if is_text_file(event.path):
            self._open_editor(event.path)
        else:
            self._open_preview(event.path)

    # ------------------------------------------------------------------
    #  Address bar + command bar
    # ------------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "addressbar":
            p = Path(event.value).expanduser().resolve()
            if p.is_dir():
                self._load_dir(p)
            else:
                self.notify(f"Path not found: {event.value}", severity="error")
            self.query_one("#file-list", FileListView).focus()

    def on_key(self, event: events.Key):
        """Double-space opens the command modal from anywhere."""
        if event.key == "space":
            # Don't intercept if an Input widget has focus
            focused = self.focused
            if focused is not None and focused.__class__.__name__ == "Input":
                return
            now = time.monotonic()
            if now - self._last_space_time < 0.45:
                self._open_cmd_modal()
                event.stop()
                self._last_space_time = 0.0
                return
            self._last_space_time = now

    def _open_cmd_modal(self):
        def cb(raw: Optional[str]):
            if raw:
                self._handle_command(raw)
            self.query_one("#file-list", FileListView).focus()
        self.push_screen(CommandModal(), cb)

    # ------------------------------------------------------------------
    #  Command parser
    # ------------------------------------------------------------------
    def _handle_command(self, raw: str):
        if not raw:
            return
        if not raw.startswith(":"):
            self.notify(
                "Commands must start with :   Type  :help  for a list.",
                severity="warning",
            )
            return

        parts = raw[1:].split(maxsplit=1)
        cmd   = parts[0].lower() if parts else ""
        arg   = parts[1] if len(parts) > 1 else ""

        simple = {
            "q": self.action_quit,        "quit": self.action_quit,
            "h": self._cmd_help,          "help": self._cmd_help,
            "r": self.action_reload,      "reload": self.action_reload,
            "i": self._cmd_info,          "info": self._cmd_info,
            "settings": self._cmd_settings,
            "hidden":  self.action_toggle_hidden,
            "copy":    self.action_copy_item,
            "cut":     self.action_cut_item,
            "paste":   self.action_paste_item,
            "del":     self.action_delete_item,
            "delete":  self.action_delete_item,
            "edit":    self.action_edit_file,
            "preview": self.action_preview_file,
            "shell":   self.action_open_shell,
        }

        if cmd == "new"    and arg: self._create_file(arg);      return
        if cmd == "mkdir"  and arg: self._create_dir(arg);       return
        if cmd == "rename" and arg: self._do_rename(arg);        return
        if cmd == "chmod"  and arg: self._do_chmod(arg);         return
        if cmd == "search":         self.action_open_search();   return
        if cmd == "cd":
            target = Path(arg or "~").expanduser().resolve()
            if target.is_dir():
                self._load_dir(target)
            else:
                self.notify(f"Not a directory: {arg}", severity="error")
            return

        fn = simple.get(cmd)
        if fn:
            fn()
        else:
            self.notify(
                f"Unknown command: :{cmd}  —  type  :help  for reference",
                severity="warning",
            )

    def _cmd_help(self):
        self.push_screen(HelpModal())

    def _cmd_settings(self):
        def cb(changed: bool):
            if changed:
                # Re-read show_hidden from settings and apply everywhere
                self.show_hidden = bool(self._settings.get("show_hidden"))
                self._apply_hidden_everywhere()
                self._load_dir(self._cwd)
                self.notify("Settings saved")
        self.push_screen(SettingsModal(self._settings), cb)

    def _cmd_info(self):
        self._show_info_notify(self._selected or self._cwd)

    # ------------------------------------------------------------------
    #  Hidden files toggle — THE key fix
    # ------------------------------------------------------------------
    def action_toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self._settings.set("show_hidden", self.show_hidden)
        self._apply_hidden_everywhere()
        self._load_dir(self._cwd)
        self.notify("Hidden files: " + ("visible" if self.show_hidden else "hidden"))

    def _apply_hidden_everywhere(self):
        """Push show_hidden into the tree AND re-render the file list."""
        try:
            tree = self.query_one("#tree-view", FilteredDirectoryTree)
            tree.set_show_hidden(self.show_hidden)
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    #  Reload
    # ------------------------------------------------------------------
    def action_reload(self):
        fl = self.query_one("#file-list", FileListView)
        fl.refresh_directory(self.show_hidden)
        try:
            self.query_one("#tree-view", FilteredDirectoryTree).reload()
        except NoMatches:
            pass
        self._refresh_status()
        self.notify("Refreshed")

    # ------------------------------------------------------------------
    #  Search
    # ------------------------------------------------------------------
    def action_open_search(self):
        self.push_screen(SearchModal(self._cwd), self._search_cb)

    def _search_cb(self, path: Optional[Path]):
        if path:
            self._selected = path
            self._load_dir(path.parent if path.is_file() else path)
            if path.is_file():
                self.query_one("#file-list", FileListView).try_select_path(path)
            self.notify(f"Found: {path.name}")

    # ------------------------------------------------------------------
    #  Create
    # ------------------------------------------------------------------
    def action_new_file(self):
        def cb(name):
            if name: self._create_file(name)
        self.push_screen(InputModal("New File", "filename.txt"), cb)

    def action_new_dir(self):
        def cb(name):
            if name: self._create_dir(name)
        self.push_screen(InputModal("New Folder", "folder_name"), cb)

    def _create_file(self, name: str):
        target = self._cwd / name
        try:
            target.touch()
            self.notify(f"Created: {name}")
            self._reload_and_select(target)
        except Exception as e:
            self.notify(str(e), severity="error")

    def _create_dir(self, name: str):
        target = self._cwd / name
        try:
            target.mkdir(parents=True, exist_ok=True)
            self.notify(f"Folder created: {name}")
            self._reload_and_select(target)
        except Exception as e:
            self.notify(str(e), severity="error")

    # ------------------------------------------------------------------
    #  Rename
    # ------------------------------------------------------------------
    def action_rename_item(self):
        if not self._selected:
            self.notify("Select an item first", severity="warning"); return
        p = self._selected
        def cb(new_name):
            if new_name and new_name != p.name:
                self._do_rename(new_name)
        self.push_screen(InputModal("Rename", "new name", p.name, "Rename"), cb)

    def _do_rename(self, new_name: str):
        if not self._selected:
            self.notify("Select an item first", severity="warning"); return
        p = self._selected
        try:
            new_path = p.parent / new_name
            p.rename(new_path)
            self._selected = new_path
            self.notify(f"Renamed to: {new_name}")
            self._reload_and_select(new_path)
        except Exception as e:
            self.notify(str(e), severity="error")

    # ------------------------------------------------------------------
    #  Delete
    # ------------------------------------------------------------------
    def action_delete_item(self):
        if not self._selected:
            self.notify("Select an item first", severity="warning"); return
        p = self._selected
        if self._settings.get("confirm_delete"):
            def cb(confirmed: bool):
                if confirmed: self._do_delete(p)
            self.push_screen(ConfirmModal(
                "Confirm Delete",
                f"Delete '{p.name}'?\nThis cannot be undone.",
                confirm_label="Delete", danger=True,
            ), cb)
        else:
            self._do_delete(p)

    def _do_delete(self, p: Path):
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            self._selected = None
            self.notify(f"Deleted: {p.name}")
            self.action_reload()
        except Exception as e:
            self.notify(str(e), severity="error")

    # ------------------------------------------------------------------
    #  Clipboard
    # ------------------------------------------------------------------
    def action_copy_item(self):
        if not self._selected:
            self.notify("Select an item first", severity="warning"); return
        self._clipboard.copy(self._selected)
        self.notify(f"Copied: {self._selected.name}")
        self._refresh_status()

    def action_cut_item(self):
        if not self._selected:
            self.notify("Select an item first", severity="warning"); return
        self._clipboard.cut(self._selected)
        self.notify(f"Cut: {self._selected.name}")
        self._refresh_status()

    def action_paste_item(self):
        if not self._clipboard.has_item:
            self.notify("Clipboard is empty", severity="warning"); return
        src  = self._clipboard.path
        dest = self._cwd / src.name
        if dest.exists() and self._settings.get("confirm_overwrite"):
            def cb(ok: bool):
                if ok: self._do_paste(src, dest)
            self.push_screen(ConfirmModal(
                "Overwrite?",
                f"'{dest.name}' already exists. Overwrite?",
                confirm_label="Overwrite", danger=True,
            ), cb)
        else:
            self._do_paste(src, dest)

    def _do_paste(self, src: Path, dest: Path):
        try:
            if self._clipboard.op == "copy":
                shutil.copytree(src, dest) if src.is_dir() else shutil.copy2(src, dest)
                self.notify(f"Pasted: {src.name}")
            else:
                shutil.move(str(src), str(dest))
                self.notify(f"Moved: {src.name}")
                self._clipboard.clear()
            self.action_reload()
        except Exception as e:
            self.notify(str(e), severity="error")
        self._refresh_status()

    def action_escape_action(self):
        if self._clipboard.has_item:
            self._clipboard.clear()
            self.notify("Clipboard cleared")
            self._refresh_status()

    # ------------------------------------------------------------------
    #  chmod
    # ------------------------------------------------------------------
    def _do_chmod(self, octal_str: str):
        p = self._selected or self._cwd
        try:
            p.chmod(int(octal_str, 8))
            self.notify(f"chmod {octal_str} → {p.name}")
        except Exception as e:
            self.notify(str(e), severity="error")

    # ------------------------------------------------------------------
    #  Editor
    # ------------------------------------------------------------------
    def action_edit_file(self):
        p = self._selected
        if not p:
            def cb(name):
                if name:
                    t = self._cwd / name
                    t.touch()
                    self._open_editor(t)
            self.push_screen(InputModal("Create & Edit New File", "notes.txt"), cb)
            return
        if not p.is_file():
            self.notify("Select a file first", severity="warning"); return
        if not is_text_file(p):
            self.notify(f"Not a text file — use :preview instead", severity="warning")
            return
        self._open_editor(p)

    def _open_editor(self, path: Path):
        def cb(saved: bool):
            if saved:
                self.notify(f"Saved: {path.name}")
                self.action_reload()
        self.push_screen(TextEditorModal(path), cb)

    # ------------------------------------------------------------------
    #  Preview
    # ------------------------------------------------------------------
    def action_preview_file(self):
        p = self._selected
        if not p or not p.is_file():
            self.notify("Select a file first", severity="warning"); return
        self._open_preview(p)

    def _open_preview(self, path: Path):
        self.push_screen(FilePreviewModal(path, self._settings))

    # ------------------------------------------------------------------
    #  Shell
    # ------------------------------------------------------------------
    def action_open_shell(self):
        shell = os.environ.get("SHELL", "/bin/bash")
        with self.suspend():
            subprocess.run([shell], cwd=str(self._cwd))

    # ------------------------------------------------------------------
    #  Info notify
    # ------------------------------------------------------------------
    def _show_info_notify(self, p: Path):
        try:
            st = p.stat()
            lines = [
                f"  {p.name}",
                f"Type    : {file_type_label(p)}",
                f"Size    : {format_size(st.st_size) if p.is_file() else '—'}",
                f"Modified: {format_date(st.st_mtime)}",
                f"Perms   : {format_perms(st.st_mode)} ({oct(stat.S_IMODE(st.st_mode))})",
                f"Owner   : {get_owner(st)} / {get_group(st)}",
            ]
            if p.is_file() and is_text_file(p) and st.st_size < 5_000_000:
                lines.append(f"MD5     : {md5_file(p)}")
            self.notify("\n".join(lines), timeout=8)
        except Exception as e:
            self.notify(str(e), severity="error")

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------
    def _reload_and_select(self, path: Path):
        fl = self.query_one("#file-list", FileListView)
        fl.load_directory(self._cwd, self.show_hidden)
        fl.try_select_path(path)
        self._selected = path
        self._refresh_status()
        self.query_one("#detail-strip", DetailStrip).show_path(path)


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    start = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) > 1
        else None
    )
    FileExplorer(start_path=start).run()