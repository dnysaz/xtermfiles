"""
cli.py — xtermfiles  (entry point)

Terminal File Explorer — Windows Explorer style file manager for the terminal.

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

Mouse:
    Single click   = Enter folder / select file
    Double click   = Open floating window (draggable, multi-instance)
"""

import os
import sys
import time
import shutil
import stat
import subprocess
import asyncio
import re
from pathlib import Path
from typing import Optional, Any

from upath import UPath
from textual.app import App, ComposeResult
from textual.widgets import (
    Header, DirectoryTree, Static, Input, Label, Button,
    ListView, ListItem
)
from textual.widgets._tree import TreeNode
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
    is_text_file, md5_file, list_dir, get_lang, get_mime,
)
from modals import (
    InputModal, ConfirmModal, SearchModal,
    TextEditorModal, FilePreviewModal, SettingsModal,
    HelpModal, CommandModal, SSHLoginModal, LoadingModal,
)
from widgets import FileListView, DetailStrip, FileDoubleClicked, FloatingWindow


EXTRA_CSS = """
.editor-box  { width: 100%; height: 100%; border: none; padding: 0; }
#preview-box { width: 100%; height: 100%; border: none; padding: 0; }
#editor-area { height: 1fr; border: none; }
"""


# ---------------------------------------------------------------------------
#  FilteredDirectoryTree
# ---------------------------------------------------------------------------
class FilteredDirectoryTree(DirectoryTree):
    """DirectoryTree that hides dotfiles via filter_paths unless _show_hidden."""
    from upath import UPath
    PATH = UPath

    def __init__(self, path: str, show_hidden: bool = False, **kwargs):
        super().__init__(path, **kwargs)
        self._show_hidden = show_hidden

    def set_show_hidden(self, value: bool):
        self._show_hidden = value
        self.reload()

    def reset_node(self, node: TreeNode, label: str, data: Any) -> None:
        """Override root label if it's a UPath root."""
        super().reset_node(node, label, data)
        from upath import UPath
        if isinstance(node.data.path, UPath):
            # If path.name is empty (root), show host
            if not node.data.path.name:
                host = getattr(node.data.path.fs, "host", "remote")
                node.set_label(f"root ({host})")

    def filter_paths(self, paths):
        if self._show_hidden:
            return paths
        return [p for p in paths if not p.name.startswith(".")]


# ---------------------------------------------------------------------------
#  FileExplorer — main app
# ---------------------------------------------------------------------------
class FileExplorer(App):
    TITLE = "xtermfiles"
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

        if start_path is None:
            sp = self._settings.get("start_path") or "~"
            start_path = Path(sp).expanduser()
        self._root = start_path.resolve()
        self._cwd: Path = self._root
        self._selected: Optional[Path] = None

        self.show_hidden = bool(self._settings.get("show_hidden"))
        self._last_space_time: float = 0.0
        self._last_tree_click_time: float = 0.0

    # ------------------------------------------------------------------
    #  Layout
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="toolbar"):
            yield Input(value=str(self._cwd), placeholder="Path...",
                        id="addressbar")

        with Horizontal(id="layout"):
            with Vertical(id="left-panel"):
                yield Static("   LOCAL SERVER", id="local-title", classes="tree-title")
                yield FilteredDirectoryTree(
                    str(self._root),
                    show_hidden=self.show_hidden,
                    id="local-tree",
                    classes="tree-view",
                )
                
                # --- SAVED SSH SERVERS ---
                yield Static("   SAVED SSH SERVERS", id="saved-ssh-title", classes="tree-title")
                yield ListView(id="saved-ssh-list", classes="ssh-list")
                
                yield Static("   REMOTE SERVER", id="remote-title", classes="tree-title hidden")
                yield FilteredDirectoryTree(
                    str(self._root),  # placeholder
                    show_hidden=self.show_hidden,
                    id="remote-tree",
                    classes="tree-view hidden",
                )

            with Vertical(id="right-panel"):
                with Horizontal(id="col-header"):
                    yield Static("   Name",      classes="col-name")
                    yield Static("Size",          classes="col-size")
                    yield Static("Type",          classes="col-type")
                    yield Static("Date Modified", classes="col-date")

                yield FileListView(self._settings, id="file-list")
                with ScrollableContainer(id="file-preview-panel"):
                    yield Static("", id="file-preview-content")
                yield DetailStrip(self._settings, id="detail-strip")

        yield Static("", id="statusbar")

    def on_mount(self):
        self._load_dir(self._cwd)
        self._update_saved_ssh_list()
        self.query_one("#file-list", FileListView).focus()

    def _update_saved_ssh_list(self):
        try:
            lst = self.query_one("#saved-ssh-list", ListView)
            lst.clear()
            saved = self._settings.get("saved_ssh") or []
            for s in saved:
                # show simple host part for display
                display = s.split("@")[-1] if "@" in s else s
                item = ListItem(Label(f" 🌐 {display}"), classes="ssh-item")
                item.conn_str = s # Store directly
                lst.append(item)
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    #  Directory loading
    # ------------------------------------------------------------------
    def _show_file_list(self):
        try:
            self.query_one("#col-header").display = True
            self.query_one("#file-list").display = True
            self.query_one("#file-preview-panel").display = False
        except NoMatches:
            pass

    def _show_file_preview(self):
        try:
            self.query_one("#col-header").display = False
            self.query_one("#file-list").display = False
            self.query_one("#file-preview-panel").display = True
        except NoMatches:
            pass

    def _load_dir(self, path: Path):
        try:
            self._cwd = path.resolve() if hasattr(path, "resolve") and not str(path).startswith("ssh://") else path
            fl = self.query_one("#file-list", FileListView)
            fl.load_directory(self._cwd, self.show_hidden)
            self._selected = None
            self._show_file_list()
            self._update_addressbar()
            self._refresh_status()
            self.query_one("#detail-strip", DetailStrip).show_dir_summary(
                self._cwd, self.show_hidden
            )
        except Exception as e:
            self.notify(f"Failed to load directory: {e}", severity="error")

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
        self._load_dir(event.path)
        self.query_one("#file-list", FileListView).focus()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        event.stop()
        now = time.monotonic()
        path = event.path
        
        # Double click opens floating window
        if self._selected == path and now - getattr(self, "_last_tree_click_time", 0) < 0.5:
            self._open_floating_window(path)
            self._last_tree_click_time = 0.0
            return
            
        self._last_tree_click_time = now
        self._selected = path
        self._preview_file_right(path)

    # ------------------------------------------------------------------
    #  Events — right file list
    # ------------------------------------------------------------------
    def on_file_list_view_file_selected(self, event: FileListView.FileSelected):
        event.stop()
        self._selected = event.path
        self._preview_file_right(event.path)

    def _preview_file_right(self, path: Path):
        self.query_one("#detail-strip", DetailStrip).show_path(path)
        self._refresh_status()
        self._show_file_preview()
        
        content_widget = self.query_one("#file-preview-content", Static)
        if is_text_file(path):
            try:
                size = path.stat().st_size
                max_bytes = self._settings.get("preview_max_kb") * 1024
                if size > max_bytes:
                    content_widget.update(f"[yellow]File too large to preview ({format_size(size)}). Limit: {self._settings.get('preview_max_kb')} KB[/yellow]")
                else:
                    content = path.read_text(errors="replace")
                    lang = get_lang(path)
                    from rich.syntax import Syntax
                    # Use a textual-compatible subset. Rich syntax highlights
                    syntax_lang = lang if lang in ["python", "javascript", "typescript", "html", "css", "markdown", "json", "sql", "bash", "rust", "go", "java", "c", "cpp", "regex"] else "text"
                    content_widget.update(Syntax(content, syntax_lang, theme="monokai", line_numbers=True, word_wrap=False))
            except Exception as e:
                content_widget.update(f"[red]Error reading file: {e}[/red]")
        else:
            try:
                st = path.stat()
                content_widget.update(
                    f"[bold yellow]📄 {path.name}[/bold yellow]\n\n"
                    f"Type    : {file_type_label(path)}\n"
                    f"Size    : {format_size(st.st_size)}\n"
                    f"MIME    : {get_mime(path)}\n"
                    f"Modified: {format_date(st.st_mtime)}\n"
                )
            except Exception as e:
                content_widget.update(f"[red]Cannot read file info: {e}[/red]")

    def on_file_list_view_directory_entered(
        self, event: FileListView.DirectoryEntered
    ):
        self._load_dir(event.path)

    # ------------------------------------------------------------------
    #  Double-click → open floating window
    # ------------------------------------------------------------------
    def on_file_double_clicked(self, event: FileDoubleClicked):
        self._open_floating_window(event.path)

    def on_floating_window_open_path(self, event: FloatingWindow.OpenPath):
        """Handle request from inside a floating window to open a new one."""
        self._open_floating_window(event.path)

    def _open_floating_window(self, path: Path):
        """Create and mount a new draggable floating window."""
        fw = FloatingWindow(path, self._settings)
        self.mount(fw)

    # ------------------------------------------------------------------
    #  Address bar + command bar
    # ------------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "addressbar":
            val = event.value.strip()
            
            # Detect IP IPv4 format or ssh://
            ip_pattern = r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::(\d+))?$"
            match = re.match(ip_pattern, val)
            
            if match or val.startswith("ssh://"):
                if val.startswith("ssh://"):
                    try:
                        self.notify("Connecting to SSH server...")
                        p = UPath(val)
                        self._load_dir(p)
                    except Exception as e:
                        self.notify(f"SSH Error: {e}", severity="error")
                    return
                
                host = match.group(1)
                port = match.group(2) or "22"
                
                def on_ssh_login(creds):
                    if creds:
                        user, pwd = creds
                        ssh_url = f"ssh://{host}:{port}/"
                        
                        self._connect_ssh(host, port, user, pwd)
                
                self.push_screen(SSHLoginModal(host, port), on_ssh_login)
                self.query_one("#file-list", FileListView).focus()

    def _connect_ssh(self, host: str, port: int, user: str, pwd: str):
        from upath import UPath
        ssh_url = f"ssh://{host}:{port}/"
        
        self.push_screen(LoadingModal(f"Connecting to {host}..."))
        
        def do_connect():
            try:
                # Securely pass auth via kwargs instead of URL-encoding to handle symbols
                remote_path = UPath(ssh_url, username=user, password=pwd)
                # Force network check
                list(remote_path.iterdir())
                
                def update_ui():
                    try: self.pop_screen()
                    except: pass
                    rtree = self.query_one("#remote-tree", DirectoryTree)
                    # Set the reactive path natively to preserve UPath kwargs (like password) in memory!
                    rtree.path = remote_path
                    
                    # We intercept the root node safely since we just changed its path
                    self.query_one("#remote-title").remove_class("hidden")
                    rtree.remove_class("hidden")
                    self._load_dir(remote_path)
                    
                    # Also hide saved list once connected? Or just leave it?
                    # self.query_one("#saved-ssh-list").add_class("hidden")
                
                self.call_from_thread(update_ui)
            except Exception as e:
                def fail_ui():
                    try: self.pop_screen()
                    except: pass
                    self.notify(f"SSH Connection Failed: {e}", severity="error")
                self.call_from_thread(fail_ui)
                
        self.run_worker(do_connect, thread=True)

    def on_list_view_selected(self, event: ListView.Selected):
        if event.list_view.id == "saved-ssh-list":
            conn_str = getattr(event.item, "conn_str", None)
            if conn_str:
                # Format: user:pass@host:port
                try:
                    # Very basic parse
                    upart, hpart = conn_str.split("@")
                    user, pwd = upart.split(":", 1)
                    if ":" in hpart:
                        host, port = hpart.split(":", 1)
                        port = int(port)
                    else:
                        host = hpart
                        port = 22
                    self._connect_ssh(host, port, user, pwd)
                except Exception as e:
                    self.notify(f"Invalid saved connection format: {e}", severity="error")
            return

            # Normal local path
            p = Path(val).expanduser().resolve()
            if p.is_dir():
                self._load_dir(p)
            else:
                self.notify(f"Path not found: {event.value}", severity="error")
            self.query_one("#file-list", FileListView).focus()

    def on_key(self, event: events.Key):
        """Double-space opens the command modal from anywhere."""
        if event.key == "space":
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
            "q": self.exit,               "quit": self.exit,
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
                self.show_hidden = bool(self._settings.get("show_hidden"))
                self._apply_hidden_everywhere()
                self._load_dir(self._cwd)
                self._update_saved_ssh_list()
                self.notify("Settings saved")
        self.push_screen(SettingsModal(self._settings), cb)

    def _cmd_info(self):
        self._show_info_notify(self._selected or self._cwd)

    # ------------------------------------------------------------------
    #  Hidden files toggle
    # ------------------------------------------------------------------
    def action_toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self._settings.set("show_hidden", self.show_hidden)
        self._apply_hidden_everywhere()
        self._load_dir(self._cwd)
        self.notify("Hidden files: " + ("visible" if self.show_hidden else "hidden"))

    def _apply_hidden_everywhere(self):
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