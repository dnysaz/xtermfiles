"""
helpers.py — Utilities, CSS, Settings, Clipboard
xtermfiles — Terminal File Explorer
"""

import os
import stat
import mimetypes
import hashlib
import json
import pwd
import grp
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  Settings
# ─────────────────────────────────────────────────────────────────────────────
SETTINGS_PATH = Path.home() / ".config" / "xtermfiles" / "settings.json"

DEFAULTS: dict = {
    "show_hidden":        False,
    "preview_max_kb":     200,
    "date_format":        "%d/%m/%Y %H:%M",
    "start_path":         "~",
    "confirm_delete":     True,
    "confirm_overwrite":  True,
    "show_file_icons":    True,
    "saved_ssh":          [],
}


class Settings:
    def __init__(self):
        self._data: dict = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if SETTINGS_PATH.exists():
                saved = json.loads(SETTINGS_PATH.read_text())
                for k, v in saved.items():
                    if k in DEFAULTS:
                        self._data[k] = v
        except Exception:
            pass

    def save(self):
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(json.dumps(self._data, indent=2))
        except Exception:
            pass

    def get(self, key: str):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value):
        if key in DEFAULTS:
            self._data[key] = value
            self.save()

    def toggle(self, key: str) -> bool:
        val = not bool(self._data.get(key, DEFAULTS.get(key)))
        self.set(key, val)
        return val


# ─────────────────────────────────────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────────────────────────────────────
APP_CSS = """
Screen { background: #1e1e1e; color: #d4d4d4; }
Header { background: #2d2d2d; color: #ffffff; text-style: bold; height: 1; }

/* ── Toolbar ── */
#toolbar { height: 1; background: #2d2d2d; layout: horizontal; }
#addressbar {
    height: 1; background: #3c3c3c; color: #cccccc;
    padding: 0 1; border: none; width: 1fr;
}
#addressbar:focus { background: #1e3a5f; color: #ffffff; border: none; }

/* ── Main layout ── */
#layout { layout: horizontal; height: 1fr; }

/* ── Left panel — scrollable ── */
#left-panel {
    width: 26%; min-width: 20; max-width: 50;
    background: #252526;
    border-right: solid #3e3e3e;
    overflow-y: auto;
}

.tree-title {
    height: 1; background: #37373d; color: #888888;
    padding: 0 1; text-style: bold;
}

.tree-view {
    background: #252526;
    scrollbar-color: #424242 #252526;
    scrollbar-size: 1 1;
}

.hidden { display: none; }

.ssh-list { background: #252526; height: auto; }
.ssh-item { padding: 0 1; color: #9cdcfe; height: 1; }
.ssh-item:hover { background: #2a2d2e; }
.ssh-item.--highlight { background: #094771; }

/* ── Right panel ── */
#right-panel { width: 1fr; background: #1e1e1e; layout: vertical; }

#col-header {
    height: 1; background: #2d2d2d; color: #888888;
    layout: horizontal; border-bottom: solid #3e3e3e;
}
.col-name { width: 1fr; padding: 0 1; }
.col-size { width: 12;  padding: 0 1; }
.col-type { width: 16;  padding: 0 1; }
.col-date { width: 18;  padding: 0 1; }

#file-list {
    height: 1fr; background: #1e1e1e;
    scrollbar-color: #424242 #1e1e1e; scrollbar-size: 1 1;
}

.file-row             { layout: horizontal; height: 1; }
.file-row:hover       { background: #2a2d2e; }
.file-row.--highlight { background: #094771; color: #ffffff; }

.row-name { width: 1fr; padding: 0 1; overflow: hidden; }
.row-size { width: 12;  padding: 0 1; color: #9cdcfe; text-align: right; }
.row-type { width: 16;  padding: 0 1; color: #ce9178; }
.row-date { width: 18;  padding: 0 1; color: #6a9955; }

/* ── File preview strip — fills full height when visible ── */
#file-preview-panel {
    height: 1fr; background: #1a1a1a;
    border-top: solid #3e3e3e;
    padding: 0 1;
    display: none;
    scrollbar-color: #424242 #1a1a1a;
    scrollbar-size: 1 1;
}

/* ── Detail strip ── */
#detail-strip {
    height: 1; background: #252526;
    border-top: solid #3e3e3e; padding: 0 1;
}

/* ── Status bar ── */
#statusbar { height: 1; background: #007acc; color: #ffffff; padding: 0 1; }

/* ── Modal base ── */
ModalScreen { background: rgba(0,0,0,0.6); align: center middle; }

#modal-box {
    background: #252526; border: solid #007acc;
    width: 58; padding: 1 2; height: auto; max-height: 36;
}
#modal-title { color: #4fc1ff; text-style: bold; margin-bottom: 1; }
#modal-body  { color: #d4d4d4; margin-bottom: 1; height: auto; }

.modal-input { background: #3c3c3c; color: #d4d4d4; border: solid #555555; margin-bottom: 1; }
.modal-input:focus { border: solid #007acc; }

.modal-buttons { layout: horizontal; height: 3; align: right middle; margin-top: 1; }

.btn-ok     { background: #0e639c; color: #ffffff; border: none;
               width: 14; height: 3; margin-left: 1; content-align: center middle; }
.btn-ok:hover     { background: #1177bb; }
.btn-cancel { background: #2d2d2d; color: #cccccc; border: solid #555555;
               width: 14; height: 3; content-align: center middle; }
.btn-cancel:hover { background: #3e3e3e; }
.btn-danger { background: #8b1a1a; color: #ffaaaa; border: solid #c72e2e;
               width: 14; height: 3; margin-left: 1; content-align: center middle; }
.btn-danger:hover { background: #c72e2e; color: #ffffff; }

/* ── Full-screen editor / preview ── */
.editor-box  { width: 100%; height: 100%; border: none; padding: 0; }
#preview-box { width: 100%; height: 100%; border: none; padding: 0; }

/* editor: view (read) and area (edit) both fill 1fr, one is hidden at a time */
#editor-view { height: 1fr; padding: 0 1; overflow-y: auto;
               scrollbar-color: #424242 #1e1e1e; scrollbar-size: 1 1; }
#editor-area { height: 1fr; border: none; }

#editor-titlebar {
    height: 1; background: #252526;
    color: #888888; padding: 0 1;
    border-bottom: solid #3e3e3e;
}
#editor-footer {
    height: 3; background: #252526; layout: horizontal;
    align: right middle; padding: 0 1; border-top: solid #3e3e3e;
}
#preview-titlebar {
    height: 1; background: #252526;
    color: #888888; padding: 0 1;
    border-bottom: solid #3e3e3e;
}
#preview-content  { height: 1fr; padding: 0 1; overflow-y: auto;
                    scrollbar-color: #424242 #1e1e1e; scrollbar-size: 1 1; }
#preview-footer {
    height: 3; background: #252526; layout: horizontal;
    align: right middle; padding: 0 1; border-top: solid #3e3e3e;
}

/* ── Settings ── */
#settings-box { background: #1e1e1e; border: solid #007acc; width: 62; height: auto; max-height: 38; padding: 0; }
#settings-titlebar { height: 1; background: #007acc; color: #ffffff; text-style: bold; padding: 0 1; }
#settings-scroll { height: 1fr; max-height: 30; padding: 1 2; }
.stg-section { color: #4fc1ff; text-style: bold; margin-top: 1; height: 1; }
.stg-label   { height: 1; color: #d4d4d4; margin-top: 1; }
.stg-btn-on  { background: #16825d; color: #ffffff; border: none;
               width: 10; height: 3; margin-bottom: 1; content-align: center middle; }
.stg-btn-on:hover  { background: #1bab7b; }
.stg-btn-off { background: #4a1a1a; color: #ff9090; border: solid #8b2222;
               width: 10; height: 3; margin-bottom: 1; content-align: center middle; }
.stg-btn-off:hover { background: #6e2020; color: #ffffff; }
.stg-input   { background: #2d2d2d; color: #9cdcfe; border: solid #3e3e3e; height: 3; margin-bottom: 1; }
.stg-input:focus { border: solid #007acc; }
#settings-footer {
    height: 3; background: #252526; layout: horizontal;
    align: right middle; padding: 0 1; border-top: solid #3e3e3e;
}

/* ── Help ── */
#help-box { background: #1e1e1e; border: solid #007acc; width: 72; height: 38; padding: 0; }
#help-titlebar { height: 1; background: #007acc; color: #ffffff; text-style: bold; padding: 0 1; }
#help-scroll { height: 1fr; padding: 1 2; }
#help-footer {
    height: 3; background: #252526; layout: horizontal;
    align: right middle; padding: 0 1; border-top: solid #3e3e3e;
}

/* ── Command modal ── */
#cmd-modal-box { background: #1e1e1e; border: solid #007acc; width: 70; height: auto; padding: 0; }
#cmd-modal-title { height: 1; background: #007acc; color: #ffffff; text-style: bold; padding: 0 1; }
#cmd-modal-input { background: #2d2d2d; color: #ffffff; border: none; height: 3; padding: 0 1; }
#cmd-modal-input:focus { background: #1e3a5f; border: none; }
#cmd-modal-hints { height: 1; background: #252526; padding: 0 1; }

/* ── SSH modals ── */
.dialog-box   { background: #252526; border: solid #007acc; width: 52; padding: 1 2; height: auto; }
.dialog-title { color: #4fc1ff; text-style: bold; margin-bottom: 1; }
.dialog-input-row { layout: horizontal; height: 3; margin-bottom: 1; align: left middle; }
.dialog-label { width: 8; color: #888888; }
.dialog-input { width: 1fr; background: #3c3c3c; color: #d4d4d4; border: solid #555555; }
.dialog-input:focus { border: solid #007acc; }
.dialog-btn-row { layout: horizontal; height: 3; align: right middle; margin-top: 1; }

/* ── Search list ── */
#search-list { height: 14; border: solid #3e3e3e; background: #1e1e1e; margin-bottom: 1; }
#search-list > ListItem             { padding: 0 1; height: 1; color: #d4d4d4; }
#search-list > ListItem:hover       { background: #2a2d2e; }
#search-list > ListItem.--highlight { background: #094771; }

/* ── Floating window ── */
FloatingWindow {
    background: #252526;
    border: solid #007acc;
    width: 64; height: 22;
    offset: 4 2;
    layer: floating;
}
.fw-titlebar {
    height: 1; background: #007acc; layout: horizontal;
    padding: 0 1;
}
.fw-title-label { width: 1fr; color: #ffffff; text-style: bold; }
.fw-mode-label  { width: 6;   color: #ffe08a; text-align: right; }
.fw-close-btn   { width: 3;   background: #c72e2e; color: #fff; border: none; min-width: 3; }
.fw-close-btn:hover { background: #e33232; }
.fw-list    { height: 1fr; background: #1e1e1e; scrollbar-size: 1 1; }
.fw-editor  { height: 1fr; border: none; }
.fw-content { height: 1fr; padding: 0 1; }
.fw-preview { color: #d4d4d4; }
.fw-cmd-input {
    height: 1; background: #1e3a5f; color: #ffffff;
    border-top: solid #007acc; border-left: none;
    border-right: none; border-bottom: none;
    padding: 0 1; display: none;
}
.fw-resize-handle {
    height: 1; width: 3; color: #555555;
    text-align: right; padding: 0 1;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
#  File type helpers  (all pure, no I/O — safe to call from compose)
# ─────────────────────────────────────────────────────────────────────────────
IMAGE_EXTS   = {".png",".jpg",".jpeg",".gif",".webp",".bmp",".ico",".tiff",".svg"}
VIDEO_EXTS   = {".mp4",".mkv",".avi",".mov",".webm",".flv"}
AUDIO_EXTS   = {".mp3",".wav",".ogg",".flac",".aac",".m4a"}
ARCHIVE_EXTS = {".zip",".tar",".gz",".bz2",".xz",".rar",".7z"}
TEXT_EXTS    = {
    ".py",".js",".ts",".jsx",".tsx",".html",".css",".scss",
    ".json",".yaml",".yml",".toml",".ini",".cfg",".conf",
    ".sh",".bash",".zsh",".fish",".md",".rst",".txt",
    ".xml",".sql",".r",".rb",".go",".rs",".c",".cpp",".h",
    ".java",".kt",".swift",".lua",".pl",".php",
    ".env",".gitignore",".log",".csv",".dockerfile",
}
TEXT_NAMES   = {
    "makefile","dockerfile","readme","license","changelog",
    ".bashrc",".zshrc",".profile",".bash_profile",".gitconfig",
}
LANG_MAP = {
    ".py":"python",".js":"javascript",".ts":"typescript",
    ".jsx":"jsx",".tsx":"tsx",".html":"html",".css":"css",
    ".scss":"scss",".json":"json",".yaml":"yaml",".yml":"yaml",
    ".toml":"toml",".sh":"bash",".bash":"bash",".zsh":"bash",
    ".md":"markdown",".xml":"xml",".sql":"sql",".go":"go",
    ".rs":"rust",".c":"c",".cpp":"cpp",".h":"c",
    ".java":"java",".kt":"kotlin",".rb":"ruby",".php":"php",
    ".lua":"lua",".r":"r",".ini":"ini",".conf":"ini",
    ".csv":"text",".env":"bash",
}
ICON_MAP = {
    ".py":"py",".js":"js",".ts":"ts",".jsx":"js",".tsx":"ts",
    ".html":"ht",".css":"cs",".scss":"cs",
    ".json":"{}",".yaml":"ym",".yml":"ym",".toml":"tm",
    ".sh":"sh",".bash":"sh",".zsh":"sh",
    ".md":"md",".txt":"tx",".log":"lg",".pdf":"pd",
    ".png":"im",".jpg":"im",".jpeg":"im",".gif":"im",
    ".svg":"im",".webp":"im",".bmp":"im",
    ".zip":"ar",".tar":"ar",".gz":"ar",".rar":"ar",".7z":"ar",
    ".mp3":"au",".wav":"au",".ogg":"au",
    ".mp4":"vi",".mkv":"vi",".avi":"vi",
    ".go":"go",".rs":"rs",".c":" c",".cpp":"c+",
    ".java":"jv",".rb":"rb",".php":"ph",".lua":"lu",
    ".sql":"sq",".env":"ev",".gitignore":"gi",
}
TYPE_LABELS = {
    ".py":"Python",".js":"JS",".ts":"TS",".html":"HTML",".css":"CSS",
    ".json":"JSON",".yaml":"YAML",".yml":"YAML",".toml":"TOML",
    ".sh":"Shell",".bash":"Shell",".md":"Markdown",".txt":"Text",
    ".log":"Log",".pdf":"PDF",".sql":"SQL",".go":"Go",".rs":"Rust",
    ".c":"C Source",".cpp":"C++",".h":"Header",".java":"Java",
    ".rb":"Ruby",".php":"PHP",".lua":"Lua",
    ".png":"PNG",".jpg":"JPEG",".jpeg":"JPEG",".gif":"GIF",
    ".svg":"SVG",".webp":"WebP",".bmp":"Bitmap",
    ".zip":"ZIP",".tar":"TAR",".gz":"GZip",".rar":"RAR",".7z":"7Zip",
    ".mp3":"Audio",".wav":"Audio",".mp4":"Video",".mkv":"Video",
    ".env":"ENV",".ini":"Config",".cfg":"Config",".conf":"Config",
}


def is_text_file(p: Path) -> bool:
    return p.suffix.lower() in TEXT_EXTS or p.name.lower() in TEXT_NAMES

def is_image(p: Path) -> bool:   return p.suffix.lower() in IMAGE_EXTS
def is_video(p: Path) -> bool:   return p.suffix.lower() in VIDEO_EXTS
def is_audio(p: Path) -> bool:   return p.suffix.lower() in AUDIO_EXTS
def is_archive(p: Path) -> bool: return p.suffix.lower() in ARCHIVE_EXTS

def get_lang(p: Path) -> str:
    return LANG_MAP.get(p.suffix.lower(), "text")

def get_mime(p: Path) -> str:
    mime, _ = mimetypes.guess_type(str(p))
    return mime or "application/octet-stream"

def file_type_label(p: Path) -> str:
    if p.is_dir():    return "Folder"
    if p.is_symlink(): return "Symlink"
    return TYPE_LABELS.get(p.suffix.lower(),
           (p.suffix.lstrip(".").upper() + " File") if p.suffix else "File")

def get_icon(p: Path, show: bool = True) -> str:
    if not show: return ""
    if p.is_dir():    return "📁"
    if p.is_symlink(): return "🔗"
    return ICON_MAP.get(p.suffix.lower(), "  ")

def format_size(n: int) -> str:
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def format_date(ts: float, fmt: str = "%d/%m/%Y %H:%M") -> str:
    return datetime.fromtimestamp(ts).strftime(fmt)

def format_perms(mode: int) -> str:
    return stat.filemode(mode)

def get_owner(st: os.stat_result) -> str:
    try:    return pwd.getpwuid(st.st_uid).pw_name
    except: return str(st.st_uid)

def get_group(st: os.stat_result) -> str:
    try:    return grp.getgrgid(st.st_gid).gr_name
    except: return str(st.st_gid)

def md5_file(p: Path) -> str:
    h = hashlib.md5()
    try:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
        return h.hexdigest()
    except: return "—"

def list_dir(path: Path, show_hidden: bool = False) -> list[Path]:
    entries = list(path.iterdir())
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith(".")]
    dirs  = sorted([e for e in entries if e.is_dir()],     key=lambda p: p.name.lower())
    files = sorted([e for e in entries if not e.is_dir()], key=lambda p: p.name.lower())
    return dirs + files


# ─────────────────────────────────────────────────────────────────────────────
#  Clipboard
# ─────────────────────────────────────────────────────────────────────────────
class Clipboard:
    def __init__(self):
        self.path: Path | None = None
        self.op: str = ""

    def copy(self, p: Path): self.path = p; self.op = "copy"
    def cut(self, p: Path):  self.path = p; self.op = "cut"
    def clear(self):          self.path = None; self.op = ""

    @property
    def has_item(self) -> bool: return self.path is not None

    @property
    def label(self) -> str:
        if not self.has_item: return ""
        return ("Clipboard[copy]: " if self.op == "copy" else "Clipboard[cut]: ") + self.path.name