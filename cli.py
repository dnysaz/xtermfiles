"""
cli.py — xtermfiles  (entry point)

Run:
    python cli.py              # home directory
    python cli.py /var/www     # specific path

Mouse:
    Single click  = enter folder / select file (preview in right panel)
    Double click  = open draggable floating window

Commands (Space Space to open bar, prefix with :):
    :q  :r  :h  :i  :settings  :hidden
    :new  :mkdir  :rename  :del  :chmod
    :copy  :cut  :paste  :edit  :preview  :search  :shell  :cd
"""

import os
import re
import sys
import stat
import time
import shutil
import subprocess
from pathlib import Path
from upath import UPath
from typing import Optional, Any

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, DirectoryTree, Static, Input, Label, Button,
    ListView, ListItem,
)
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.reactive import reactive
from textual.css.query import NoMatches
from textual import events
from rich.text import Text
from rich.syntax import Syntax

from helpers import (
    APP_CSS, Clipboard, Settings,
    format_size, format_date, format_perms,
    get_owner, get_group, file_type_label,
    is_text_file, get_lang, get_mime, md5_file, list_dir,
)
from modals import (
    InputModal, ConfirmModal, SearchModal,
    TextEditorModal, FilePreviewModal, SettingsModal,
    HelpModal, CommandModal, SSHLoginModal, LoadingModal,
)
from widgets import FileListView, DetailStrip, FileDoubleClicked, FloatingWindow

_PREVIEW_LANGS = {
    "python","javascript","typescript","html","css","markdown",
    "json","sql","bash","rust","go","java","c","cpp","regex",
}

EXTRA_CSS = """
.editor-box  { width: 100%; height: 100%; border: none; padding: 0; }
#preview-box { width: 100%; height: 100%; border: none; padding: 0; }
#editor-area { height: 1fr; border: none; }
"""


# ─────────────────────────────────────────────────────────────────────────────
#  FilteredDirectoryTree  — hides dotfiles via filter_paths()
#  BUG FIX: was using old ID "tree-view"; now uses "local-tree" / "remote-tree"
# ─────────────────────────────────────────────────────────────────────────────
class FilteredDirectoryTree(DirectoryTree):
    PATH = UPath
    
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


# ─────────────────────────────────────────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────────────────────────────────────────
class FileExplorer(App):
    TITLE = "xtermfiles"
    CSS   = APP_CSS + EXTRA_CSS

    BINDINGS = [
        Binding("f5",           "reload",        "Reload",    show=True),
        Binding("ctrl+h",       "toggle_hidden", "Hidden",    show=True),
        Binding("ctrl+f",       "open_search",   "Search",    show=True),
        Binding("ctrl+n",       "new_file",      "New File",  show=True),
        Binding("ctrl+shift+n", "new_dir",       "New Folder",show=False),
        Binding("f2",           "rename_item",   "Rename",    show=True),
        Binding("delete",       "delete_item",   "Delete",    show=True),
        Binding("ctrl+c",       "copy_item",     "Copy",      show=True),
        Binding("ctrl+x",       "cut_item",      "Cut",       show=True),
        Binding("ctrl+v",       "paste_item",    "Paste",     show=True),
        Binding("ctrl+e",       "edit_file",     "Edit",      show=True),
        Binding("ctrl+p",       "preview_file",  "Preview",   show=False),
        Binding("ctrl+o",       "open_shell",    "Shell",     show=False),
        Binding("escape",       "escape_action", "Cancel",    show=False),
        Binding("tab",          "focus_next",    "Tab",       show=False),
        Binding("ctrl+q",       "quit",          "Quit"),
        Binding("ctrl+c",       "quit",          "Quit",      show=False),
        Binding("ctrl+r",       "refresh",       "Refresh"),
    ]

    show_hidden: reactive[bool] = reactive(False)

    def __init__(self, start_path: Optional[Path] = None):
        super().__init__()
        self._settings  = Settings()
        self._clipboard = Clipboard()

        if start_path is None:
            start_path = Path(self._settings.get("start_path") or "~").expanduser()
        self._root = start_path.resolve()
        self._cwd: Path = self._root
        self._selected: Optional[Path] = None

        self.show_hidden      = bool(self._settings.get("show_hidden"))
        self._last_space_time = 0.0
        self._last_tree_click = 0.0   # for double-click on tree file nodes

    # ─────────────────────────────────────────────────────────────────────
    #  Layout
    # ─────────────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="toolbar"):
            yield Input(value=str(self._cwd), placeholder="Path or IP...",
                        id="addressbar")

        with Horizontal(id="layout"):
            # Left panel — wrapped in ScrollableContainer so it scrolls
            with ScrollableContainer(id="left-panel"):
                yield Static("  LOCAL", id="local-title", classes="tree-title")
                yield FilteredDirectoryTree(
                    str(self._root),
                    show_hidden=self.show_hidden,
                    id="local-tree",
                    classes="tree-view",
                )
                yield Static("  SSH SERVERS", id="saved-ssh-title", classes="tree-title")
                yield ListView(id="saved-ssh-list", classes="ssh-list")
                # Remote tree — hidden until SSH connected
                yield Static("  REMOTE", id="remote-title",
                             classes="tree-title hidden")
                yield FilteredDirectoryTree(
                    str(self._root),
                    show_hidden=self.show_hidden,
                    id="remote-tree",
                    classes="tree-view hidden",
                )

            # Right panel
            with Vertical(id="right-panel"):
                with Horizontal(id="col-header"):
                    yield Static("   Name",       classes="col-name")
                    yield Static("Size",           classes="col-size")
                    yield Static("Type",           classes="col-type")
                    yield Static("Date Modified",  classes="col-date")

                yield FileListView(self._settings, id="file-list")

                # Inline file preview (shown on single-click file)
                with ScrollableContainer(id="file-preview-panel"):
                    yield Static("", id="file-preview-content")

                yield DetailStrip(self._settings, id="detail-strip")

        yield Static("", id="statusbar")

        with Horizontal(id="command-bar", classes="hidden"):
            yield Label(":", id="cmd-prefix")
            yield Input(id="cmd-input")

    def on_mount(self):
        self._load_dir(self._cwd)
        self._update_saved_ssh_list()
        self.query_one("#file-list", FileListView).focus()

    # ─────────────────────────────────────────────────────────────────────
    #  SSH saved list
    # ─────────────────────────────────────────────────────────────────────
    def _update_saved_ssh_list(self):
        try:
            lst  = self.query_one("#saved-ssh-list", ListView)
            lst.clear()
            for conn in (self._settings.get("saved_ssh") or []):
                display = conn.split("@")[-1] if "@" in conn else conn
                item = ListItem(Label(f"  {display}"), classes="ssh-item")
                item._conn_str = conn          # store on item directly
                lst.append(item)
        except NoMatches:
            pass

    # ─────────────────────────────────────────────────────────────────────
    #  Directory loading helpers
    # ─────────────────────────────────────────────────────────────────────
    def _show_file_list(self):
        try:
            self.query_one("#col-header").display         = True
            self.query_one("#file-list").display          = True
            self.query_one("#file-preview-panel").display = False
        except NoMatches:
            pass

    def _show_preview_panel(self):
        try:
            self.query_one("#col-header").display         = False
            self.query_one("#file-list").display          = False
            self.query_one("#file-preview-panel").display = True
        except NoMatches:
            pass

    def _load_dir(self, path):
        try:
            # IMPORTANT: path.resolve() can block the main thread for SSH paths.
            self._cwd = path 
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
            self.notify(f"Cannot open directory: {e}", severity="error")

    def _update_addressbar(self):
        try:
            self.query_one("#addressbar", Input).value = str(self._cwd)
        except NoMatches:
            pass

    def _refresh_status(self):
        cb_txt  = f"  |  {self._clipboard.label}" if self._clipboard.has_item else ""
        hid_txt = "  |  hidden: on" if self.show_hidden else ""
        entries = list_dir(self._cwd, self.show_hidden)
        n_dir   = sum(1 for e in entries if e.is_dir())
        n_file  = sum(1 for e in entries if e.is_file())
        t = Text()
        t.append(f" {n_dir} folder{'s' if n_dir != 1 else ''}, "
                 f"{n_file} file{'s' if n_file != 1 else ''}", "#ffffff")
        t.append(cb_txt,  "#ffe08a")
        t.append(hid_txt, "#c0c0c0")
        t.append("   Space Space = command bar", "#c0e0ff")
        try:
            self.query_one("#statusbar", Static).update(t)
        except NoMatches:
            pass

    # ─────────────────────────────────────────────────────────────────────
    #  Events — left tree
    # ─────────────────────────────────────────────────────────────────────
    def on_tree_node_selected(self, event: FilteredDirectoryTree.NodeSelected):
        """Single click / focus on any node in the tree (sidebar -> main view sync)."""
        if event.node.data:
            path = event.node.data
            if hasattr(path, "is_dir") and path.is_dir():
                if self._cwd != path:
                    self._load_dir(path)
            elif hasattr(path, "is_file") and path.is_file():
                self._preview_file_inline(path)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        """Single/double click on a file node in the tree."""
        event.stop()
        now  = time.monotonic()
        path = event.path
        if (self._selected == path
                and now - self._last_tree_click < 0.5):
            # Double-click → floating window
            self._open_floating_window(path)
            self._last_tree_click = 0.0
            return
        self._last_tree_click = now
        self._selected = path
        self._preview_file_inline(path)

    # ─────────────────────────────────────────────────────────────────────
    #  Events — right file list
    # ─────────────────────────────────────────────────────────────────────
    def on_file_list_view_file_selected(self, event: FileListView.FileSelected):
        event.stop()
        self._selected = event.path
        self._preview_file_inline(event.path)

    def on_file_list_view_directory_entered(
        self, event: FileListView.DirectoryEntered
    ):
        self._load_dir(event.path)

    def on_file_double_clicked(self, event: FileDoubleClicked):
        self._open_floating_window(event.path)

    # ─────────────────────────────────────────────────────────────────────
    #  Inline preview (right panel, replaces file list temporarily)
    # ─────────────────────────────────────────────────────────────────────
    def _preview_file_inline(self, path: Path):
        self.query_one("#detail-strip", DetailStrip).show_path(path)
        self._refresh_status()
        self._show_preview_panel()
        w = self.query_one("#file-preview-content", Static)
        if is_text_file(path):
            try:
                max_b = self._settings.get("preview_max_kb") * 1024
                size  = path.stat().st_size
                if size > max_b:
                    w.update(f"[yellow]Too large to preview ({format_size(size)})[/yellow]")
                    return
                lang = get_lang(path)
                slang = lang if lang in _PREVIEW_LANGS else "text"
                w.update(Syntax(path.read_text(errors="replace"),
                                slang, theme="monokai",
                                line_numbers=True, word_wrap=False))
            except Exception as e:
                w.update(f"[red]{e}[/red]")
        else:
            try:
                st = path.stat()
                w.update(
                    f"[bold]{path.name}[/bold]\n\n"
                    f"Type : {file_type_label(path)}\n"
                    f"Size : {format_size(st.st_size)}\n"
                    f"MIME : {get_mime(path)}\n"
                    f"Date : {format_date(st.st_mtime)}\n"
                )
            except Exception as e:
                w.update(f"[red]{e}[/red]")

    # ─────────────────────────────────────────────────────────────────────
    #  Floating windows
    # ─────────────────────────────────────────────────────────────────────
    def _open_floating_window(self, path: Path):
        self.mount(FloatingWindow(path, self._settings))

    def on_floating_window_open_path(self, event: FloatingWindow.OpenPath):
        self._open_floating_window(event.path)

    # ─────────────────────────────────────────────────────────────────────
    #  Address bar — handles local paths AND SSH
    # ─────────────────────────────────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted):
        val = event.value.strip()
        
        # ── Command handling (:q, :edit, etc) ──
        if event.input.id == "cmd-input":
            self.query_one("#command-bar").add_class("hidden")
            self._handle_command(val)
            return

        if event.input.id != "addressbar":
            return
            
        self.query_one("#file-list", FileListView).focus()

        # ── SSH: bare IPv4 or ssh:// URL ──
        ip_re = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::(\d+))?$", val)
        if ip_re or val.startswith("ssh://"):
            if val.startswith("ssh://"):
                self._ssh_via_upath(val)
                return
            host = ip_re.group(1)
            port = ip_re.group(2) or "22"
            def on_login(creds):
                if creds:
                    user, pwd = creds
                    self._connect_ssh(host, port, user, pwd)
            self.push_screen(SSHLoginModal(host, port), on_login)
            return

        # ── Local path ──
        p = Path(val).expanduser().resolve()
        if p.is_dir():
            self._load_dir(p)
        else:
            self.notify(f"Path not found: {val}", severity="error")

    def on_list_view_selected(self, event: ListView.Selected):
        """Saved SSH list click."""
        if event.list_view.id != "saved-ssh-list":
            return
        conn = getattr(event.item, "_conn_str", None)
        if not conn:
            return
        try:
            # Format: user:pass@host:port or user@host:port or just host
            if "@" in conn:
                upart, hpart = conn.split("@", 1)
                if ":" in upart:
                    user, pwd = upart.split(":", 1)
                else:
                    user, pwd = upart, ""
            else:
                hpart = conn
                user, pwd = "root", ""

            if ":" in hpart:
                host, port = hpart.split(":", 1)
            else:
                host, port = hpart, "22"

            self._connect_ssh(host, str(port), user, pwd)
        except Exception as e:
            self.notify(f"Invalid saved connection: {e}", severity="error")

    # ── SSH helpers ───────────────────────────────────────────────────────
    def _ssh_via_upath(self, url: str):
        """Connect using a full ssh:// URL (no credentials)."""
        try:
            from upath import UPath
            p = UPath(url)
            self._load_dir(p)
        except Exception as e:
            self.notify(f"SSH Error: {e}", severity="error")

    def _connect_ssh(self, host: str, port: str, user: str, pwd: str):
        # Pre-flight: check dependencies before spawning thread
        try:
            import upath  # noqa
        except ImportError:
            self.notify(
                "SSH requires: pip install universal-pathlib paramiko",
                severity="error", timeout=8,
            )
            return
        self.notify(f"Connecting to {host}:{port} …")
        
        def worker():
            import paramiko
            import socket
            import threading
            
            # Absolute background thread to avoid ANY main thread block
            def run_auth():
                try:
                    # DNS lookup
                    try: _ip = socket.gethostbyname(host)
                    except: _ip = host

                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(
                        _ip, port=int(port), username=user, password=pwd,
                        timeout=5, banner_timeout=5, auth_timeout=5,
                        look_for_keys=False, allow_agent=False,
                        gss_auth=False, gss_kex=False
                    )
                    client.close()
                    
                    # Prepare UPath object in background and "ping" it
                    from upath import UPath
                    remote = UPath(f"ssh://{host}:{port}/", username=user, password=pwd, 
                                   look_for_keys=False, allow_agent=False,
                                   timeout=5, banner_timeout=5, auth_timeout=5)
                    # Verify listing works (optional, but good for error catching)
                    # list(remote.iterdir()) 

                    def finish_success(rmt=remote):
                        try:
                            rtree = self.query_one("#remote-tree", FilteredDirectoryTree)
                            rtree.path = rmt
                            self.query_one("#remote-title").remove_class("hidden")
                            rtree.remove_class("hidden")
                            # Focus remote tree and load it into main view
                            rtree.focus()
                            self._load_dir(rmt)
                            self.notify(f"Connected: {host}")
                        except Exception as e:
                            self.notify(f"Remote UI error: {e}", severity="error")

                    self.call_from_thread(finish_success)

                except Exception as e:
                    msg = str(e)
                    if "Auth" in msg or "permission" in msg.lower(): msg = "Auth failed"
                    elif "timeout" in msg.lower(): msg = "Connection timed out"
                    elif "refused" in msg.lower(): msg = "Connection refused"
                    self.call_from_thread(lambda m=msg: self.notify(f"SSH Error: {m}", severity="error"))

            threading.Thread(target=run_auth, daemon=True).start()

        self.run_worker(worker, thread=True)

    # ─────────────────────────────────────────────────────────────────────
    #  Double-space → command modal
    # ─────────────────────────────────────────────────────────────────────
    def on_key(self, event: events.Key):
        # Emergency exit
        if event.key in ("ctrl+c", "ctrl+x"):
            self.exit()
            return

        if event.key == "colon":
            self._open_cmd_bar()
            event.stop()
            return

        if event.key == "space":
            focused = self.focused
            if focused is not None and focused.__class__.__name__ == "Input":
                return
            now = time.monotonic()
            if now - self._last_space_time < 0.45:
                self._open_cmd_bar()
                event.stop()
                self._last_space_time = 0.0
                return
            self._last_space_time = now

    def _open_cmd_bar(self):
        try:
            cb = self.query_one("#command-bar")
            cb.remove_class("hidden")
            inp = self.query_one("#cmd-input", Input)
            inp.value = ":"
            inp.focus()
        except NoMatches:
            pass

    # ─────────────────────────────────────────────────────────────────────
    #  Command parser
    # ─────────────────────────────────────────────────────────────────────
    def _handle_command(self, raw: str):
        if not raw: return
        if not raw.startswith(":"):
            self.notify("Commands must start with :   Type :help for a list.",
                        severity="warning"); return

        parts = raw[1:].split(maxsplit=1)
        cmd   = parts[0].lower() if parts else ""
        arg   = parts[1] if len(parts) > 1 else ""

        simple = {
            "q":       self.action_quit,        "quit":    self.action_quit,
            "h":       self._cmd_help,           "help":    self._cmd_help,
            "r":       self.action_reload,       "reload":  self.action_reload,
            "i":       self._cmd_info,           "info":    self._cmd_info,
            "settings":self._cmd_settings,
            "hidden":  self.action_toggle_hidden,
            "copy":    self.action_copy_item,    "cut":     self.action_cut_item,
            "paste":   self.action_paste_item,
            "del":     self.action_delete_item,  "delete":  self.action_delete_item,
            "edit":    self.action_edit_file,    "preview": self.action_preview_file,
            "shell":   self.action_open_shell,
        }
        if cmd == "new"    and arg: self._create_file(arg);   return
        if cmd == "mkdir"  and arg: self._create_dir(arg);    return
        if cmd == "rename" and arg: self._do_rename(arg);     return
        if cmd == "chmod"  and arg: self._do_chmod(arg);      return
        if cmd == "search":         self.action_open_search(); return
        if cmd == "cd":
            p = Path(arg or "~").expanduser().resolve()
            if p.is_dir(): self._load_dir(p)
            else: self.notify(f"Not a directory: {arg}", severity="error")
            return
        fn = simple.get(cmd)
        if fn: fn()
        else:  self.notify(f"Unknown: :{cmd}  — type :help", severity="warning")

    def _cmd_help(self):     self.push_screen(HelpModal())
    def _cmd_info(self):     self._show_info_notify(self._selected or self._cwd)
    def _cmd_settings(self):
        def cb(changed: bool):
            if changed:
                self.show_hidden = bool(self._settings.get("show_hidden"))
                self._apply_hidden()
                self._load_dir(self._cwd)
                self._update_saved_ssh_list()
                self.notify("Settings saved")
        self.push_screen(SettingsModal(self._settings), cb)

    # ─────────────────────────────────────────────────────────────────────
    #  Hidden files — BUG FIX: targets both local-tree and remote-tree
    # ─────────────────────────────────────────────────────────────────────
    def action_toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self._settings.set("show_hidden", self.show_hidden)
        self._apply_hidden()
        self._load_dir(self._cwd)
        self.notify("Hidden files: " + ("on" if self.show_hidden else "off"))

    def _apply_hidden(self):
        for tid in ("local-tree", "remote-tree"):
            try:
                self.query_one(f"#{tid}", FilteredDirectoryTree) \
                    .set_show_hidden(self.show_hidden)
            except NoMatches:
                pass

    # ─────────────────────────────────────────────────────────────────────
    #  Reload
    # ─────────────────────────────────────────────────────────────────────
    def action_reload(self):
        try:
            self.query_one("#file-list", FileListView).refresh_directory(self.show_hidden)
        except NoMatches:
            pass
        for tid in ("local-tree", "remote-tree"):
            try:
                self.query_one(f"#{tid}", FilteredDirectoryTree).reload()
            except NoMatches:
                pass
        self._refresh_status()
        self.notify("Refreshed")

    # ─────────────────────────────────────────────────────────────────────
    #  Search
    # ─────────────────────────────────────────────────────────────────────
    def action_open_search(self):
        self.push_screen(SearchModal(self._cwd), self._search_cb)

    def _search_cb(self, path: Optional[Path]):
        if path:
            self._selected = path
            self._load_dir(path.parent if path.is_file() else path)
            if path.is_file():
                try:
                    self.query_one("#file-list", FileListView).try_select_path(path)
                except NoMatches:
                    pass
            self.notify(f"Found: {path.name}")

    # ─────────────────────────────────────────────────────────────────────
    #  File creation
    # ─────────────────────────────────────────────────────────────────────
    def action_new_file(self):
        self.push_screen(InputModal("New File", "filename.txt"),
                         lambda n: n and self._create_file(n))

    def action_new_dir(self):
        self.push_screen(InputModal("New Folder", "folder_name"),
                         lambda n: n and self._create_dir(n))

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

    # ─────────────────────────────────────────────────────────────────────
    #  Rename
    # ─────────────────────────────────────────────────────────────────────
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
            np = p.parent / new_name
            p.rename(np)
            self._selected = np
            self.notify(f"Renamed to: {new_name}")
            self._reload_and_select(np)
        except Exception as e:
            self.notify(str(e), severity="error")

    # ─────────────────────────────────────────────────────────────────────
    #  Delete
    # ─────────────────────────────────────────────────────────────────────
    def action_delete_item(self):
        if not self._selected:
            self.notify("Select an item first", severity="warning"); return
        p = self._selected
        if self._settings.get("confirm_delete"):
            def cb(ok: bool):
                if ok: self._do_delete(p)
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

    # ─────────────────────────────────────────────────────────────────────
    #  Clipboard
    # ─────────────────────────────────────────────────────────────────────
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
            self.push_screen(ConfirmModal("Overwrite?",
                             f"'{dest.name}' already exists. Overwrite?",
                             confirm_label="Overwrite", danger=True), cb)
        else:
            self._do_paste(src, dest)

    def _do_paste(self, src: Path, dest: Path):
        try:
            if self._clipboard.op == "copy":
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dest)
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

    # ─────────────────────────────────────────────────────────────────────
    #  chmod
    # ─────────────────────────────────────────────────────────────────────
    def _do_chmod(self, octal_str: str):
        p = self._selected or self._cwd
        try:
            p.chmod(int(octal_str, 8))
            self.notify(f"chmod {octal_str}: {p.name}")
        except Exception as e:
            self.notify(str(e), severity="error")

    # ─────────────────────────────────────────────────────────────────────
    #  Editor
    # ─────────────────────────────────────────────────────────────────────
    def action_edit_file(self):
        p = self._selected
        if not p:
            def cb(name):
                if name:
                    t = self._cwd / name; t.touch(); self._open_editor(t)
            self.push_screen(InputModal("Create & Edit File", "notes.txt"), cb)
            return
        if not p.is_file():
            self.notify("Select a file first", severity="warning"); return
        if not is_text_file(p):
            self.notify("Not a text file — use :preview", severity="warning"); return
        self._open_editor(p)

    def _open_editor(self, path: Path):
        def cb(saved: bool):
            if saved:
                self.notify(f"Saved: {path.name}")
                self.action_reload()
        self.push_screen(TextEditorModal(path), cb)

    # ─────────────────────────────────────────────────────────────────────
    #  Preview (full-screen modal)
    # ─────────────────────────────────────────────────────────────────────
    def action_preview_file(self):
        p = self._selected
        if not p or not p.is_file():
            self.notify("Select a file first", severity="warning"); return
        self.push_screen(FilePreviewModal(p, self._settings))

    # ─────────────────────────────────────────────────────────────────────
    #  Shell
    # ─────────────────────────────────────────────────────────────────────
    def action_open_shell(self):
        shell = os.environ.get("SHELL", "/bin/bash")
        with self.suspend():
            subprocess.run([shell], cwd=str(self._cwd))

    # ─────────────────────────────────────────────────────────────────────
    #  Info notify
    # ─────────────────────────────────────────────────────────────────────
    def _show_info_notify(self, p: Path):
        try:
            st    = p.stat()
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

    # ─────────────────────────────────────────────────────────────────────
    #  Reload + select helper
    # ─────────────────────────────────────────────────────────────────────
    def _reload_and_select(self, path: Path):
        fl = self.query_one("#file-list", FileListView)
        fl.load_directory(self._cwd, self.show_hidden)
        fl.try_select_path(path)
        self._selected = path
        self._refresh_status()
        self.query_one("#detail-strip", DetailStrip).show_path(path)


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    start = (Path(sys.argv[1]).expanduser().resolve()
             if len(sys.argv) > 1 else None)
    FileExplorer(start_path=start).run()