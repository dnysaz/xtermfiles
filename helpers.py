"""
helpers.py — Utility functions, CSS theming, Settings, Clipboard
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
#  Settings — persisted to ~/.config/ketut-explorer/settings.json
# ─────────────────────────────────────────────────────────────────────────────
SETTINGS_PATH = Path.home() / ".config" / "ketut-explorer" / "settings.json"

DEFAULTS: dict = {
    "show_hidden":        False,   # show dotfiles in file list & tree
    "preview_max_kb":     200,     # max file size for syntax preview (KB)
    "date_format":        "%d/%m/%Y %H:%M",
    "start_path":         "~",     # startup directory
    "confirm_delete":     True,    # ask before deleting
    "confirm_overwrite":  True,    # ask before paste-overwrite
    "show_file_icons":    True,    # emoji icons in file list
}

SETTING_LABELS = {
    "show_hidden":       ("Show hidden files (dotfiles)",  "bool"),
    "preview_max_kb":    ("Max preview size (KB)",         "int"),
    "date_format":       ("Date format",                   "str"),
    "start_path":        ("Startup directory",             "str"),
    "confirm_delete":    ("Confirm before delete",         "bool"),
    "confirm_overwrite": ("Confirm before overwrite",      "bool"),
    "show_file_icons":   ("Show file icons",               "bool"),
}


class Settings:
    def __init__(self):
        self._data: dict = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if SETTINGS_PATH.exists():
                with open(SETTINGS_PATH) as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    if k in DEFAULTS:
                        self._data[k] = v
        except Exception:
            pass

    def save(self):
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_PATH, "w") as f:
                json.dump(self._data, f, indent=2)
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

    def all(self) -> dict:
        return dict(self._data)


# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
APP_CSS = """
Screen { background: #1e1e1e; color: #d4d4d4; }

Header { background: #2d2d2d; color: #ffffff; text-style: bold; height: 1; }
Footer { background: #007acc; color: #ffffff; height: 1; }

/* ── Toolbar ── */
#toolbar { height: 1; background: #2d2d2d; layout: horizontal; }
#addressbar {
    height: 1; background: #3c3c3c; color: #cccccc;
    padding: 0 1; border: none; width: 1fr;
}
#addressbar:focus { background: #1e3a5f; color: #ffffff; border: none; }

/* ── Layout ── */
#layout { layout: horizontal; height: 1fr; }

/* ── Left tree ── */
#left-panel {
    width: 26%; min-width: 20; max-width: 48;
    background: #252526; border-right: solid #3e3e3e;
}
#left-title { height: 1; background: #37373d; color: #cccccc; padding: 0 1; text-style: bold; }
#tree-view  { height: 1fr; background: #252526; scrollbar-color: #424242 #252526; scrollbar-size: 1 1; }
DirectoryTree .tree--cursor    { background: #094771; color: #ffffff; }
DirectoryTree .tree--highlight { background: #2a2d2e; }
DirectoryTree .tree--guides    { color: #404040; }

/* ── Right file list ── */
#right-panel { width: 1fr; background: #1e1e1e; }

#col-header { height: 1; background: #2d2d2d; color: #888888; layout: horizontal; border-bottom: solid #3e3e3e; }
.col-name { width: 1fr; padding: 0 1; }
.col-size { width: 12;  padding: 0 1; }
.col-type { width: 16;  padding: 0 1; }
.col-date { width: 18;  padding: 0 1; }

#file-list { height: 1fr; background: #1e1e1e; scrollbar-color: #424242 #1e1e1e; scrollbar-size: 1 1; }

.file-row             { layout: horizontal; height: 1; }
.file-row:hover       { background: #2a2d2e; }
.file-row.--highlight { background: #094771; color: #ffffff; }

.row-name { width: 1fr; padding: 0 1; overflow: hidden; }
.row-size { width: 12;  padding: 0 1; color: #9cdcfe; text-align: right; }
.row-type { width: 16;  padding: 0 1; color: #ce9178; }
.row-date { width: 18;  padding: 0 1; color: #6a9955; }

/* ── Detail strip ── */
#detail-strip { height: 2; background: #252526; border-top: solid #3e3e3e; padding: 0 1; }

/* ── Status bar ── */
#statusbar { height: 1; background: #007acc; color: #ffffff; padding: 0 1; }

/* ── Command bar ── */
#cmd-bar   { height: 1; background: #1e1e1e; border-top: solid #3e3e3e; }
#cmd-input { background: #1e1e1e; color: #d4d4d4; border: none; height: 1; padding: 0 1; }
#cmd-input:focus { background: #1e3a5f; border: none; }

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

.btn-ok     { background: #0e639c; color: #ffffff; border: none;          width: 12; margin-left: 1; }
.btn-ok:hover     { background: #1177bb; }
.btn-cancel { background: #3c3c3c; color: #d4d4d4; border: solid #555555; width: 12; }
.btn-cancel:hover { background: #505050; }
.btn-danger { background: #c72e2e; color: #ffffff; border: none;           width: 12; margin-left: 1; }
.btn-danger:hover { background: #e33232; }

/* ── Full-screen editor ── */
.editor-box { width: 100%; height: 100%; border: none; padding: 0; }
#editor-titlebar { height: 1; background: #37373d; color: #cccccc; padding: 0 2; }
#editor-area { height: 1fr; border: none; }
#editor-footer {
    height: 3; background: #2d2d2d; layout: horizontal;
    align: right middle; padding: 0 2; border-top: solid #3e3e3e;
}

/* ── Settings modal ── */
#settings-box {
    background: #1e1e1e;
    border: solid #007acc;
    width: 62;
    height: auto;
    max-height: 38;
    padding: 0;
}
#settings-titlebar {
    height: 1;
    background: #007acc;
    color: #ffffff;
    text-style: bold;
    padding: 0 1;
}
#settings-scroll {
    height: 1fr;
    max-height: 30;
    padding: 1 2;
}
.stg-section {
    color: #4fc1ff;
    text-style: bold;
    margin-top: 1;
    height: 1;
}
.stg-label {
    height: 1;
    color: #d4d4d4;
    margin-top: 1;
}
.stg-btn-on {
    background: #16825d;
    color: #ffffff;
    border: none;
    width: 8;
    height: 1;
    margin-bottom: 1;
}
.stg-btn-on:hover { background: #1bab7b; }
.stg-btn-off {
    background: #5a1a1a;
    color: #ff8080;
    border: solid #8b2222;
    width: 8;
    height: 1;
    margin-bottom: 1;
}
.stg-btn-off:hover { background: #6e2020; }
.stg-input {
    background: #2d2d2d;
    color: #9cdcfe;
    border: solid #3e3e3e;
    height: 3;
    margin-bottom: 1;
}
.stg-input:focus { border: solid #007acc; }
#settings-footer {
    height: 3;
    background: #252526;
    layout: horizontal;
    align: right middle;
    padding: 0 2;
    border-top: solid #3e3e3e;
}

/* ── Help modal ── */
#help-box { background: #252526; border: solid #007acc; width: 72; height: 40; padding: 0; }
#help-titlebar { height: 1; background: #37373d; color: #4fc1ff; text-style: bold; padding: 0 2; }
#help-scroll { height: 1fr; padding: 1 2; }
#help-footer {
    height: 3; background: #2d2d2d; layout: horizontal;
    align: right middle; padding: 0 2; border-top: solid #3e3e3e;
}

/* ── Search modal ── */
#search-list { height: 14; border: solid #3e3e3e; background: #1e1e1e; margin-bottom: 1; scrollbar-color: #424242 #1e1e1e; }
#search-list > ListItem             { padding: 0 1; height: 1; color: #d4d4d4; }
#search-list > ListItem:hover       { background: #2a2d2e; }
#search-list > ListItem.--highlight { background: #094771; }

/* ── Image/binary preview modal ── */
#preview-box { background: #1e1e1e; border: solid #3e3e3e; width: 100%; height: 100%; padding: 0; }
#preview-titlebar { height: 1; background: #37373d; color: #cccccc; padding: 0 2; }
#preview-content { height: 1fr; padding: 1 2; align: center middle; }
#preview-footer {
    height: 3; background: #2d2d2d; layout: horizontal;
    align: right middle; padding: 0 2; border-top: solid #3e3e3e;
}

/* ── CommandModal (double-space palette) ── */
#cmd-modal-box {
    background: #1e1e1e;
    border: solid #007acc;
    width: 70;
    height: auto;
    padding: 0;
}
#cmd-modal-title {
    height: 1;
    background: #007acc;
    color: #ffffff;
    text-style: bold;
    padding: 0 1;
}
#cmd-modal-input {
    background: #2d2d2d;
    color: #ffffff;
    border: none;
    height: 3;
    padding: 0 1;
    margin: 0;
}
#cmd-modal-input:focus {
    background: #1e3a5f;
    border: none;
}
#cmd-modal-hints {
    height: 1;
    background: #252526;
    padding: 0 1;
}

/* ── Help modal clean ── */
#help-box {
    background: #1e1e1e;
    border: solid #007acc;
    width: 72;
    height: 38;
    padding: 0;
}
#help-titlebar {
    height: 1;
    background: #007acc;
    color: #ffffff;
    text-style: bold;
    padding: 0 1;
}
#help-scroll { height: 1fr; padding: 1 2; }
#help-content { color: #d4d4d4; }
#help-footer {
    height: 3;
    background: #252526;
    layout: horizontal;
    align: right middle;
    padding: 0 2;
    border-top: solid #3e3e3e;
}
"""


# ─────────────────────────────────────────────────────────────────────────────
#  File type helpers
# ─────────────────────────────────────────────────────────────────────────────
IMAGE_EXTS   = {".png",".jpg",".jpeg",".gif",".webp",".bmp",".ico",".tiff",".tif",".svg"}
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
TEXT_NAMES = {
    "makefile","dockerfile","readme","license","changelog",
    ".bashrc",".zshrc",".profile",".bash_profile",".bash_history",
    ".gitconfig",".gitignore",
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
    ".csv":"text",".env":"bash",".dockerfile":"docker",
}

def is_image(path: Path) -> bool:   return path.suffix.lower() in IMAGE_EXTS
def is_video(path: Path) -> bool:   return path.suffix.lower() in VIDEO_EXTS
def is_audio(path: Path) -> bool:   return path.suffix.lower() in AUDIO_EXTS
def is_archive(path: Path) -> bool: return path.suffix.lower() in ARCHIVE_EXTS
def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTS: return True
    if path.name.lower() in TEXT_NAMES:  return True
    mime, _ = mimetypes.guess_type(str(path))
    return bool(mime and mime.startswith("text"))

def get_lang(path: Path) -> str:
    return LANG_MAP.get(path.suffix.lower(), "text")

def get_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "unknown"


def format_size(size: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if size < 1024.0: return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def format_perms(mode: int) -> str: return stat.filemode(mode)

def format_date(ts: float, fmt: str = "%d/%m/%Y %H:%M") -> str:
    return datetime.fromtimestamp(ts).strftime(fmt)

def get_owner(st: os.stat_result) -> str:
    try:    return pwd.getpwuid(st.st_uid).pw_name
    except: return str(st.st_uid)

def get_group(st: os.stat_result) -> str:
    try:    return grp.getgrgid(st.st_gid).gr_name
    except: return str(st.st_gid)

def md5_file(path: Path) -> str:
    h = hashlib.md5()
    try:
        with open(path,"rb") as f:
            for chunk in iter(lambda: f.read(8192), b""): h.update(chunk)
        return h.hexdigest()
    except: return "—"


def file_type_label(path: Path) -> str:
    if path.is_dir():    return "Folder"
    if path.is_symlink(): return "Shortcut"
    ext = path.suffix.lower()
    labels = {
        ".py":"Python File",".js":"JS File",".ts":"TS File",
        ".html":"HTML File",".css":"CSS File",".json":"JSON File",
        ".yaml":"YAML File",".yml":"YAML File",".toml":"TOML File",
        ".sh":"Shell Script",".bash":"Shell Script",".zsh":"Shell Script",
        ".md":"Markdown",".txt":"Text File",".log":"Log File",
        ".xml":"XML File",".csv":"CSV File",".sql":"SQL File",
        ".go":"Go File",".rs":"Rust File",".c":"C Source",
        ".cpp":"C++ Source",".h":"Header File",".java":"Java File",
        ".rb":"Ruby File",".php":"PHP File",".lua":"Lua File",
        ".png":"PNG Image",".jpg":"JPEG Image",".jpeg":"JPEG Image",
        ".gif":"GIF Image",".svg":"SVG File",".webp":"WebP Image",
        ".bmp":"Bitmap",".ico":"Icon",
        ".zip":"ZIP Archive",".tar":"TAR Archive",".gz":"GZ Archive",
        ".pdf":"PDF File",".env":"ENV File",".ini":"Config File",
        ".cfg":"Config File",".conf":"Config File",
        ".mp3":"Audio File",".wav":"Audio File",".mp4":"Video File",
        ".mkv":"Video File",".avi":"Video File",
    }
    name_lower = path.name.lower()
    if name_lower in {"makefile","dockerfile","readme","license","changelog"}:
        return path.name.capitalize()
    return labels.get(ext, (ext.lstrip(".").upper()+" File") if ext else "File")


def get_icon(path: Path, show: bool = True) -> str:
    """Return a short text tag used as file icon in the list."""
    if not show: return ""
    if path.is_dir():     return "📁"
    if path.is_symlink(): return "🔗"
    ext = path.suffix.lower()
    # Text-only icons — consistent 2-char width
    return {
        # Code
        ".py": "py", ".js": "js", ".ts": "ts", ".jsx": "js", ".tsx": "ts",
        ".html": "ht", ".css": "cs", ".scss": "cs", ".sass": "cs",
        ".go": "go", ".rs": "rs", ".c": " c", ".cpp": "c+",
        ".java": "jv", ".rb": "rb", ".php": "ph", ".lua": "lu",
        ".sh": "sh", ".bash": "sh", ".zsh": "sh", ".fish": "sh",
        ".r": " r", ".pl": "pl", ".swift": "sw", ".kt": "kt",
        # Data / config
        ".json": "{}", ".yaml": "ym", ".yml": "ym", ".toml": "tm",
        ".xml": "xm", ".csv": "cv", ".sql": "sq",
        ".ini": "in", ".cfg": "cf", ".conf": "cf", ".env": "ev",
        # Docs
        ".md": "md", ".rst": "rs", ".txt": "tx", ".log": "lg", ".pdf": "pd",
        # Images
        ".png": "im", ".jpg": "im", ".jpeg": "im", ".gif": "im",
        ".svg": "im", ".webp": "im", ".bmp": "im", ".ico": "im",
        # Archives
        ".zip": "ar", ".tar": "ar", ".gz": "ar", ".bz2": "ar",
        ".xz": "ar", ".rar": "ar", ".7z": "ar",
        # Media
        ".mp3": "au", ".wav": "au", ".ogg": "au", ".flac": "au",
        ".mp4": "vi", ".mkv": "vi", ".avi": "vi", ".mov": "vi",
        # Misc
        ".gitignore": "gi", ".dockerfile": "dk",
    }.get(ext, "  ")


def list_dir(path: Path, show_hidden: bool = False) -> list[Path]:
    try:    entries = list(path.iterdir())
    except: return []
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

    def copy(self, path: Path): self.path = path; self.op = "copy"
    def cut(self, path: Path):  self.path = path; self.op = "cut"
    def clear(self):            self.path = None;  self.op = ""

    @property
    def has_item(self) -> bool: return self.path is not None

    @property
    def label(self) -> str:
        if not self.has_item: return ""
        return (" " if self.op == "copy" else "️ ") + self.path.name