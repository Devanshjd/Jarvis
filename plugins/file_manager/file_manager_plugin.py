"""
J.A.R.V.I.S -- File Manager Plugin v1.0
File search, organization, disk analysis, and cleanup utilities.

Commands:
    /find <pattern>        -- Find files by name pattern (e.g., "*.pdf", "report*")
    /findtext <text>       -- Search for text content inside files
    /tree [path]           -- Show directory tree
    /diskusage [path]      -- Show disk usage summary
    /organize <folder>     -- Auto-organize files by type into subfolders
    /recent [count]        -- Show recently modified files
    /trash <file>          -- Move file to recycle bin (safe delete)
    /dups <folder>         -- Find duplicate files by hash
"""

import os
import re
import shutil
import hashlib
import threading
from pathlib import Path
from datetime import datetime

from core.plugin_manager import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RESULTS = 50

CATEGORY_MAP = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico"},
    "Documents": {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".csv", ".odt",
    },
    "Videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"},
    "Music": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"},
    "Code": {
        ".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c",
        ".h", ".cs", ".go", ".rs", ".rb", ".php",
    },
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
}

# Reverse lookup: extension -> category
_EXT_TO_CAT: dict[str, str] = {}
for _cat, _exts in CATEGORY_MAP.items():
    for _ext in _exts:
        _EXT_TO_CAT[_ext] = _cat


def _default_search_roots() -> list[str]:
    """Return common user folders that exist."""
    home = Path.home()
    candidates = [home / d for d in ("Desktop", "Documents", "Downloads")]
    return [str(p) for p in candidates if p.is_dir()]


# ---------------------------------------------------------------------------
# Background helper (same pattern as cyber plugin)
# ---------------------------------------------------------------------------

def _bg(func, jarvis, *args):
    """Run *func* in a daemon thread; post its return value to chat."""
    def _run():
        try:
            result = func(jarvis, *args)
            jarvis.root.after(
                0, lambda: jarvis.chat.add_message("assistant", result))
        except Exception as e:
            jarvis.root.after(
                0, lambda: jarvis.chat.add_message(
                    "system", f"File Manager error: {e}"))
    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Core operations (each returns a string to display)
# ---------------------------------------------------------------------------

def _find_files(_jarvis, pattern: str, roots: list[str] | None = None):
    """Find files matching a glob-like name pattern."""
    import fnmatch

    roots = roots or _default_search_roots()
    matches: list[str] = []
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                if fnmatch.fnmatch(fname.lower(), pattern.lower()):
                    matches.append(os.path.join(dirpath, fname))
                    if len(matches) >= MAX_RESULTS:
                        break
            if len(matches) >= MAX_RESULTS:
                break
        if len(matches) >= MAX_RESULTS:
            break

    if not matches:
        return f"No files matching '{pattern}' found."
    header = f"Found {len(matches)} file(s) matching '{pattern}':\n"
    listing = "\n".join(f"  {m}" for m in matches)
    suffix = "\n(results capped at 50)" if len(matches) >= MAX_RESULTS else ""
    return header + listing + suffix


def _find_text(_jarvis, text: str, roots: list[str] | None = None):
    """Search for *text* inside files (text files only)."""
    roots = roots or _default_search_roots()
    TEXT_EXTS = {
        ".txt", ".py", ".js", ".ts", ".html", ".css", ".json", ".md",
        ".csv", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".log",
        ".java", ".cpp", ".c", ".h", ".cs", ".go", ".rs", ".rb", ".php",
    }
    results: list[str] = []
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                if Path(fname).suffix.lower() not in TEXT_EXTS:
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if text.lower() in line.lower():
                                results.append(f"  {fpath}  (line {i})")
                                break  # one match per file
                except (PermissionError, OSError):
                    continue
                if len(results) >= MAX_RESULTS:
                    break
            if len(results) >= MAX_RESULTS:
                break
        if len(results) >= MAX_RESULTS:
            break

    if not results:
        return f"No files containing '{text}' found."
    header = f"Found '{text}' in {len(results)} file(s):\n"
    listing = "\n".join(results)
    suffix = "\n(results capped at 50)" if len(results) >= MAX_RESULTS else ""
    return header + listing + suffix


def _tree(_jarvis, root: str, max_depth: int = 3):
    """Show a directory tree up to *max_depth* levels."""
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return f"Directory not found: {root}"

    lines: list[str] = [root]
    count = 0

    def _walk(path: str, prefix: str, depth: int):
        nonlocal count
        if depth > max_depth or count > 200:
            return
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return
        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        files = [e for e in entries if not os.path.isdir(os.path.join(path, e))]
        all_items = dirs + files
        for i, name in enumerate(all_items):
            count += 1
            if count > 200:
                lines.append(prefix + "... (truncated)")
                return
            connector = "|-- " if i < len(all_items) - 1 else "`-- "
            lines.append(prefix + connector + name)
            full = os.path.join(path, name)
            if os.path.isdir(full):
                extension = "|   " if i < len(all_items) - 1 else "    "
                _walk(full, prefix + extension, depth + 1)

    _walk(root, "", 1)
    return "\n".join(lines)


def _disk_usage(_jarvis, path: str | None = None):
    """Show disk usage summary."""
    lines: list[str] = ["Disk Usage Summary\n"]
    if path:
        path = os.path.expanduser(path)
        if os.path.isdir(path):
            total_size = 0
            file_count = 0
            for dirpath, _dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(dirpath, f)
                    try:
                        total_size += os.path.getsize(fp)
                        file_count += 1
                    except OSError:
                        pass
            lines.append(f"  Folder : {path}")
            lines.append(f"  Files  : {file_count}")
            lines.append(f"  Size   : {_fmt_size(total_size)}")
            return "\n".join(lines)

    # Show all drives / mount points
    if os.name == "nt":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter_idx in range(26):
            if bitmask & (1 << letter_idx):
                drive = f"{chr(65 + letter_idx)}:\\"
                try:
                    usage = shutil.disk_usage(drive)
                    lines.append(
                        f"  {drive}  "
                        f"Total: {_fmt_size(usage.total)}  "
                        f"Used: {_fmt_size(usage.used)}  "
                        f"Free: {_fmt_size(usage.free)}  "
                        f"({usage.used * 100 // usage.total}% used)"
                    )
                except (PermissionError, OSError):
                    pass
    else:
        usage = shutil.disk_usage("/")
        lines.append(
            f"  /  Total: {_fmt_size(usage.total)}  "
            f"Used: {_fmt_size(usage.used)}  "
            f"Free: {_fmt_size(usage.free)}  "
            f"({usage.used * 100 // usage.total}% used)"
        )
    return "\n".join(lines)


def _organize(_jarvis, folder: str):
    """Auto-organize files in *folder* into category subfolders."""
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return f"Directory not found: {folder}"

    moved: dict[str, int] = {}
    errors: list[str] = []

    for fname in os.listdir(folder):
        fpath = os.path.join(folder, fname)
        if not os.path.isfile(fpath):
            continue
        ext = Path(fname).suffix.lower()
        category = _EXT_TO_CAT.get(ext, "Other")
        dest_dir = os.path.join(folder, category)
        os.makedirs(dest_dir, exist_ok=True)
        try:
            shutil.move(fpath, os.path.join(dest_dir, fname))
            moved[category] = moved.get(category, 0) + 1
        except Exception as e:
            errors.append(f"  Could not move {fname}: {e}")

    if not moved and not errors:
        return "No files to organize in that folder."

    lines = [f"Organized {sum(moved.values())} file(s) in {folder}:\n"]
    for cat, cnt in sorted(moved.items()):
        lines.append(f"  {cat}: {cnt} file(s)")
    if errors:
        lines.append("\nErrors:")
        lines.extend(errors[:10])
    return "\n".join(lines)


def _recent(_jarvis, count: int = 20, roots: list[str] | None = None):
    """Show the most recently modified files."""
    roots = roots or _default_search_roots()
    files: list[tuple[float, str]] = []
    for root in roots:
        for dirpath, _dirs, filenames in os.walk(root):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                    files.append((mtime, fpath))
                except OSError:
                    continue
    files.sort(reverse=True)
    files = files[:count]
    if not files:
        return "No recent files found."
    lines = [f"Last {len(files)} modified file(s):\n"]
    for mtime, fpath in files:
        dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {dt}  {fpath}")
    return "\n".join(lines)


def _trash(_jarvis, filepath: str):
    """Move a file to the recycle bin (Windows) or warn."""
    filepath = os.path.expanduser(filepath)
    if not os.path.exists(filepath):
        return f"File not found: {filepath}"
    try:
        from send2trash import send2trash
        send2trash(filepath)
        return f"Moved to recycle bin: {filepath}"
    except ImportError:
        return (
            "The 'send2trash' package is not installed.\n"
            "Install it with:  pip install send2trash\n"
            "File was NOT deleted to keep it safe."
        )
    except Exception as e:
        return f"Failed to trash file: {e}"


def _find_dups(_jarvis, folder: str):
    """Find duplicate files in *folder* by comparing MD5 of the first 8 KB."""
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return f"Directory not found: {folder}"

    hashes: dict[str, list[str]] = {}
    for dirpath, _dirs, files in os.walk(folder):
        for fname in files:
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "rb") as f:
                    chunk = f.read(8192)
                h = hashlib.md5(chunk).hexdigest()
                hashes.setdefault(h, []).append(fpath)
            except (PermissionError, OSError):
                continue

    dupes = {h: paths for h, paths in hashes.items() if len(paths) > 1}
    if not dupes:
        return "No duplicate files found."

    lines = [f"Found {len(dupes)} set(s) of duplicates:\n"]
    shown = 0
    for _h, paths in dupes.items():
        if shown >= MAX_RESULTS:
            lines.append("... (results capped)")
            break
        lines.append(f"  Duplicate set ({len(paths)} files):")
        for p in paths:
            lines.append(f"    {p}")
            shown += 1
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_size(nbytes: int) -> str:
    """Format byte count to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------

class FileManagerPlugin(PluginBase):
    name = "file_manager"
    description = "File Manager -- search, organize, disk analysis, cleanup"
    version = "1.0"

    # -- slash commands ----------------------------------------------------

    def on_command(self, command: str, args: str) -> bool:
        args = args.strip()

        if command == "find":
            if not args:
                self.jarvis.chat.add_message(
                    "system", "Usage: /find <pattern>  (e.g., /find *.pdf)")
                return True
            self.jarvis.chat.add_message(
                "system", f"Searching for '{args}'...")
            _bg(_find_files, self.jarvis, args)
            return True

        if command == "findtext":
            if not args:
                self.jarvis.chat.add_message(
                    "system", "Usage: /findtext <text>")
                return True
            self.jarvis.chat.add_message(
                "system", f"Searching file contents for '{args}'...")
            _bg(_find_text, self.jarvis, args)
            return True

        if command == "tree":
            path = args or "."
            _bg(_tree, self.jarvis, path)
            return True

        if command == "diskusage":
            self.jarvis.chat.add_message("system", "Calculating disk usage...")
            _bg(_disk_usage, self.jarvis, args or None)
            return True

        if command == "organize":
            if not args:
                self.jarvis.chat.add_message(
                    "system", "Usage: /organize <folder>")
                return True
            self.jarvis.chat.add_message(
                "system", f"Organizing {args}...")
            _bg(_organize, self.jarvis, args)
            return True

        if command == "recent":
            try:
                count = int(args) if args else 20
            except ValueError:
                count = 20
            _bg(_recent, self.jarvis, count)
            return True

        if command == "trash":
            if not args:
                self.jarvis.chat.add_message(
                    "system", "Usage: /trash <file_path>")
                return True
            _bg(_trash, self.jarvis, args)
            return True

        if command == "dups":
            if not args:
                self.jarvis.chat.add_message(
                    "system", "Usage: /dups <folder>")
                return True
            self.jarvis.chat.add_message(
                "system", f"Scanning for duplicates in {args}...")
            _bg(_find_dups, self.jarvis, args)
            return True

        return False

    # -- natural language --------------------------------------------------

    def on_message(self, message: str) -> str | None:
        msg = message.lower().strip()

        # "find all PDFs on my desktop"
        m = re.search(
            r"find\s+(?:all\s+)?(\.\w+|[\w*?]+\.\w+)\s+(?:files?\s+)?(?:on|in)\s+(?:my\s+)?(\w+)",
            msg,
        )
        if m:
            pattern = m.group(1)
            if not pattern.startswith("*"):
                pattern = "*" + pattern
            location = m.group(2)
            root = self._resolve_location(location)
            self.jarvis.chat.add_message(
                "system", f"Searching for '{pattern}' in {root}...")
            _bg(_find_files, self.jarvis, pattern, [root] if root else None)
            return ""

        # "organize my downloads folder"
        m = re.search(r"organize\s+(?:my\s+)?(\w+)\s*(?:folder)?", msg)
        if m:
            location = m.group(1)
            root = self._resolve_location(location)
            if root:
                self.jarvis.chat.add_message(
                    "system", f"Organizing {root}...")
                _bg(_organize, self.jarvis, root)
                return ""

        # "how much disk space"
        if re.search(r"disk\s*space|storage\s*(left|free|used|usage)", msg):
            self.jarvis.chat.add_message("system", "Checking disk usage...")
            _bg(_disk_usage, self.jarvis, None)
            return ""

        # "find files containing <text>"
        m = re.search(r"(?:find|search)\s+files?\s+containing\s+(.+)", msg)
        if m:
            text = m.group(1).strip().strip("'\"")
            self.jarvis.chat.add_message(
                "system", f"Searching file contents for '{text}'...")
            _bg(_find_text, self.jarvis, text)
            return ""

        # "show recent files"
        if re.search(r"(show|list)\s+(recent|latest)\s+files?", msg):
            _bg(_recent, self.jarvis, 20)
            return ""

        return None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _resolve_location(name: str) -> str | None:
        """Map a plain name like 'desktop' to an actual path."""
        home = Path.home()
        mapping = {
            "desktop": home / "Desktop",
            "downloads": home / "Downloads",
            "documents": home / "Documents",
            "pictures": home / "Pictures",
            "videos": home / "Videos",
            "music": home / "Music",
        }
        target = mapping.get(name.lower())
        if target and target.is_dir():
            return str(target)
        return None
