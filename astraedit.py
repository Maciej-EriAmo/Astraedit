#!/usr/bin/env python3
"""AstraEdit 4.7 — hybrid GUI/TUI editor with an interactive console."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading

from i18n import detect_lang, get_lang, set_lang, t

VERSION = "4.7"
APP_NAME = "AstraEdit " + VERSION
CONFIG_FILE = pathlib.Path.home() / ".astraedit_config.json"
PYTHON_SUFFIXES = (".py", ".pyw")
ICON_FILE = pathlib.Path(__file__).resolve().with_name("astraedit.ico")
# latin-1 decodes every byte — it must stay last or later codecs never run.
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp1250", "iso-8859-2", "latin-1")
HL_FULL_BYTES = 500 * 1024
HL_DEFER_BYTES = 2 * 1024 * 1024
HL_OFF_BYTES = 5 * 1024 * 1024
MAX_REGEX_CHARS = 2 * 1024 * 1024
BRACKET_SCAN_LIMIT = 2000
DEFAULT_TAB_SIZE = 4
DEFAULT_FONT_SIZE = 11
WATCH_INTERVAL_MS = 1500
TOKEN_TAG_RULES = (
    ("Keyword", "Keyword"),
    ("Comment", "Comment"),
    ("String", "String"),
    ("Number", "Number"),
    ("Builtin", "Name.Builtin"),
    ("Operator", "Operator"),
    ("Punctuation", "Punctuation"),
    ("Name", "Name"),
)
MONO_FONT_CANDIDATES = (
    "Cascadia Mono",
    "Consolas",
    "DejaVu Sans Mono",
    "Menlo",
    "Monaco",
    "Liberation Mono",
    "Courier New",
)
EXPLORER_SKIP = {
    ".git",
    ".astraedit",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vs",
    ".mypy_cache",
    ".pytest_cache",
}
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SNIPPET_FIELD = re.compile(r"\$\{(\d+)(?::([^}]*))?\}")
SNIPPETS = {
    "def": "def ${1:name}(${2}):\n    ${3:pass}",
    "class": "class ${1:Name}:\n    def __init__(self${2}):\n        ${3:pass}",
    "ifmain": 'if __name__ == "__main__":\n    ${1:main()}',
    "try": "try:\n    ${1:pass}\nexcept ${2:Exception} as ${3:err}:\n    ${4:raise}",
    "for": "for ${1:item} in ${2:items}:\n    ${3:pass}",
    "main": 'def main():\n    ${1:pass}\n\n\nif __name__ == "__main__":\n    main()\n',
}
SNIPPET_MENU = (
    ("snippet_def", "def"),
    ("snippet_class", "class"),
    ("snippet_ifmain", "ifmain"),
    ("snippet_try", "try"),
    ("snippet_for", "for"),
    ("snippet_main", "main"),
)

# ---- Config ----
def load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except (OSError, json.JSONDecodeError, UnicodeError):
        pass
    return {}


def save_config(updates):
    data = load_config()
    data.update(updates)
    try:
        write_text_file(
            str(CONFIG_FILE),
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        print_status(t("write_error", path=str(CONFIG_FILE), err=e), "error")


# ---- Diagnostics ----
def print_status(msg, kind="info"):
    symbols = {"info": "ℹ", "success": "✔", "error": "✖", "warn": "⚠"}
    line = "%s %s" % (symbols.get(kind, "?"), msg)
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))


def clear_terminal():
    """Leave a blank screen after the TUI so the shell prompt is not mixed with the editor."""
    try:
        sys.stdout.write("\033[?1049l\033[?25h\033[0m\033[2J\033[3J\033[H")
        sys.stdout.flush()
    except Exception:
        pass
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except OSError:
        pass


def is_python_source(path):
    return str(path).lower().endswith(PYTHON_SUFFIXES)


def file_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def expand_snippet(body):
    """Replace ${n:default} fields; return (text, first_placeholder)."""
    first = {"value": None}

    def repl(match):
        value = match.group(2) if match.group(2) is not None else ""
        if first["value"] is None and value:
            first["value"] = value
        return value

    return _SNIPPET_FIELD.sub(repl, body), first["value"] or ""


def leading_ws(line):
    i = 0
    n = len(line)
    while i < n and line[i] in " \t":
        i += 1
    return line[:i]


def next_line_indent(line, tab_size=DEFAULT_TAB_SIZE, use_spaces=True):
    """Indent for the line inserted after Enter. Colon at the end adds one level."""
    stripped = line.strip()
    ws = leading_ws(line)
    if stripped.endswith(":") and not stripped.startswith("#"):
        extra = (" " * tab_size) if use_spaces else "\t"
        return ws + extra
    return ws


def toggle_hash_comments(lines):
    """Comment or uncomment a block of lines with '# '. Returns (new_lines, uncommented)."""
    nonempty = [ln for ln in lines if ln.strip()]
    if nonempty and all(ln.lstrip().startswith("#") for ln in nonempty):
        out = []
        for ln in lines:
            if not ln.strip():
                out.append(ln)
                continue
            stripped = ln.lstrip()
            ws = ln[: len(ln) - len(stripped)]
            if stripped.startswith("# "):
                out.append(ws + stripped[2:])
            elif stripped.startswith("#"):
                out.append(ws + stripped[1:])
            else:
                out.append(ln)
        return out, True
    out = []
    for ln in lines:
        if not ln.strip():
            out.append(ln)
            continue
        stripped = ln.lstrip()
        ws = ln[: len(ln) - len(stripped)]
        out.append(ws + "# " + stripped)
    return out, False


def buffer_completions(text, prefix, limit=40):
    if not prefix:
        return []
    seen = []
    found = set()
    for match in _IDENT_RE.finditer(text):
        word = match.group(0)
        if word != prefix and word.startswith(prefix) and word not in found:
            found.add(word)
            seen.append(word)
            if len(seen) >= limit:
                break
    seen.sort(key=str.lower)
    return seen


def detect_venv_python(start_path):
    folder = pathlib.Path(start_path)
    if folder.is_file():
        folder = folder.parent
    seen = set()
    relative = (
        (".venv", "Scripts", "python.exe"),
        (".venv", "bin", "python"),
        ("venv", "Scripts", "python.exe"),
        ("venv", "bin", "python"),
    )
    for _ in range(8):
        key = str(folder)
        if key in seen:
            break
        seen.add(key)
        for parts in relative:
            candidate = folder.joinpath(*parts)
            if candidate.is_file():
                return str(candidate)
        parent = folder.parent
        if parent == folder:
            break
        folder = parent
    return None


def resolve_python_executable(file_path, configured=None):
    if configured:
        return configured
    found = detect_venv_python(file_path) if file_path else None
    return found or sys.executable


def windows_dpi_aware():
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def git_status_map(root):
    """path -> porcelain XY (best-effort; empty if git is missing)."""
    git_dir = pathlib.Path(root) / ".git"
    if not git_dir.exists():
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain", "-u"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    mapping = {}
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        rel = line[3:]
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[-1]
        mapping[os.path.normpath(os.path.join(root, rel))] = line[:2].strip()
    return mapping


def next_untitled_name(open_paths, exists=os.path.exists):
    """Name for a new buffer that is not open and does not already exist on disk."""
    open_resolved = {str(pathlib.Path(p).resolve()) for p in open_paths}
    n = 0
    while n < 10000:
        name = t("untitled_file") if n == 0 else t("untitled_n", n=n)
        resolved = str(pathlib.Path(name).resolve())
        if resolved not in open_resolved and not exists(resolved):
            return name
        n += 1
    return t("untitled_n", n=n)


PROC_IDLE = "idle"
PROC_STARTING = "starting"
PROC_RUNNING = "running"
PROC_STOPPING = "stopping"
STOP_TIMEOUT_SEC = 1.5
NEWLINE_LF = "\n"
NEWLINE_CRLF = "\r\n"
NEWLINE_CR = "\r"


def _taskkill(pid, force=False):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = ["taskkill", "/T", "/PID", str(pid)]
    if force:
        cmd.insert(1, "/F")
    subprocess.run(cmd, capture_output=True, check=False, creationflags=flags)


def terminate_process_tree(proc, timeout=STOP_TIMEOUT_SEC):
    """SIGTERM / taskkill, then SIGKILL / taskkill /F if the tree is still alive."""
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            _taskkill(proc.pid, force=False)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            _taskkill(proc.pid, force=True)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class ProcessManager:
    """IDLE → STARTING → RUNNING → STOPPING → IDLE. Blocks a second F5."""

    def __init__(self):
        self._lock = threading.Lock()
        self.state = PROC_IDLE
        self.proc = None

    def is_busy(self):
        with self._lock:
            return self.state != PROC_IDLE

    def try_start(self):
        with self._lock:
            if self.state != PROC_IDLE:
                return False
            self.state = PROC_STARTING
            return True

    def attach(self, proc):
        with self._lock:
            self.proc = proc
            if self.state == PROC_STOPPING:
                return "stop"
            if self.state == PROC_STARTING:
                self.state = PROC_RUNNING
            return "run"

    def request_stop(self):
        with self._lock:
            if self.state not in (PROC_STARTING, PROC_RUNNING):
                return None
            self.state = PROC_STOPPING
            return self.proc

    def running_proc(self):
        with self._lock:
            if self.state == PROC_RUNNING and self.proc is not None and self.proc.poll() is None:
                return self.proc
            return None

    def finish(self):
        with self._lock:
            self.proc = None
            self.state = PROC_IDLE


def popen_script(file_path, python_exe=None):
    """Start a Python file. Callers keep the returned Popen, not a shared slot."""
    exe = python_exe or sys.executable
    popen_kw = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE,
        "text": True,
        "bufsize": 0,
        "cwd": str(pathlib.Path(file_path).parent),
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        popen_kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kw["start_new_session"] = True
    return subprocess.Popen([exe, "-u", str(file_path)], **popen_kw)


# ---- Shared I/O ----
def is_binary_bytes(raw):
    return b"\0" in raw[:1024]


def is_binary_file(filepath):
    try:
        with open(filepath, "rb") as f:
            return is_binary_bytes(f.read(1024))
    except OSError:
        return False


def normalize_codec(encoding):
    if encoding and encoding.isascii() and " " not in encoding:
        return encoding
    return "utf-8"


def detect_newline(raw):
    """First line ending in the file; default LF. Does not rewrite mixed files."""
    i = 0
    n = len(raw)
    while i < n:
        if raw[i] == 13:
            if i + 1 < n and raw[i + 1] == 10:
                return NEWLINE_CRLF
            return NEWLINE_CR
        if raw[i] == 10:
            return NEWLINE_LF
        i += 1
    return NEWLINE_LF


def to_editor_newlines(text, newline):
    if newline == NEWLINE_CRLF:
        return text.replace("\r\n", "\n")
    if newline == NEWLINE_CR:
        return text.replace("\r", "\n")
    return text


def from_editor_newlines(text, newline):
    if newline == NEWLINE_LF:
        return text
    return text.replace("\n", newline)


def encodings_for(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        rest = tuple(enc for enc in TEXT_ENCODINGS if enc != "utf-8-sig")
        return ("utf-8-sig",) + rest
    return TEXT_ENCODINGS


def read_text_file_smart(path):
    """Return (text, encoding, newline). Editor text always uses \\n."""
    with open(path, "rb") as f:
        raw = f.read()
    if is_binary_bytes(raw):
        raise ValueError(t("binary_error"))

    last_err = None
    for enc in encodings_for(raw):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError) as err:
            last_err = err
            continue
        newline = detect_newline(raw)
        return to_editor_newlines(text, newline), enc, newline
    if last_err is not None:
        raise last_err
    raise ValueError(t("read_error", path=path, err="decode"))


def write_text_file(path, text, encoding="utf-8", newline=NEWLINE_LF):
    """Atomic save: temp file → flush → fsync → os.replace. Strict encoding."""
    codec = normalize_codec(encoding)
    payload = from_editor_newlines(text, newline)
    data = payload.encode(codec)
    dest = pathlib.Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".%s." % dest.name, suffix=".tmp", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, dest)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def resolve_doc_path(path):
    return str(pathlib.Path(path).expanduser().resolve())


def autosave_path_for(file_path):
    parent = pathlib.Path(file_path)
    return parent.parent / ".astraedit" / "autosave" / (parent.name + ".autosave")


def newer_autosave(file_path):
    """Return draft path if it exists and is newer than the original (or original is missing)."""
    draft = autosave_path_for(file_path)
    if not draft.is_file():
        return None
    src = pathlib.Path(file_path)
    if src.is_file() and draft.stat().st_mtime <= src.stat().st_mtime:
        return None
    return draft


def highlight_policy(nbytes):
    """Return (mode, debounce_seconds). mode: full | visible | off."""
    if nbytes >= HL_OFF_BYTES:
        return "off", 2.5
    if nbytes >= HL_DEFER_BYTES:
        return "visible", 1.5
    if nbytes >= HL_FULL_BYTES:
        return "full", 1.2
    return "full", 0.5


def token_tag(token):
    name = str(token)
    for needle, tag in TOKEN_TAG_RULES:
        if needle in name:
            return tag
    return None


def token_is_ignorable(token):
    name = str(token)
    return "String" in name or "Comment" in name


def tk_index_to_offset(text, index):
    line_s, col_s = index.split(".")
    line = int(line_s)
    col = int(col_s)
    if line <= 1:
        return min(col, len(text))
    start = 0
    for _ in range(line - 1):
        nxt = text.find("\n", start)
        if nxt < 0:
            return len(text)
        start = nxt + 1
    return min(start + col, len(text))


def offset_to_tk_index(text, offset):
    offset = max(0, min(offset, len(text)))
    chunk = text[:offset]
    lines = chunk.count("\n")
    if lines == 0:
        return "1.%d" % offset
    return "%d.%d" % (1 + lines, offset - chunk.rfind("\n") - 1)


def code_char_mask(text, lexer, around, radius=BRACKET_SCAN_LIMIT):
    """True where a character is code (not a string or comment)."""
    n = len(text)
    mask = [True] * n
    if lexer is None or n == 0:
        return mask
    lo = max(0, around - radius)
    hi = min(n, around + radius)
    pos = lo
    try:
        for tok, val in lexer.get_tokens(text[lo:hi]):
            if token_is_ignorable(tok):
                end = min(pos + len(val), hi)
                for i in range(pos, end):
                    mask[i] = False
            pos += len(val)
            if pos >= hi:
                break
    except (ValueError, TypeError):
        pass
    return mask


def find_matching_bracket(text, start, direction, self_ch, other_ch, mask, max_chars=BRACKET_SCAN_LIMIT):
    count = 1
    i = start + direction
    steps = 0
    n = len(text)
    while 0 <= i < n and steps < max_chars:
        steps += 1
        if mask[i]:
            ch = text[i]
            if ch == self_ch:
                count += 1
            elif ch == other_ch:
                count -= 1
                if count == 0:
                    return i
        i += direction
    return None


class SearchPattern:
    """Unified literal / regex find-replace."""

    def __init__(self, pattern, use_regex, ignore_case=True, whole_word=False):
        self.pattern = pattern
        self.use_regex = bool(use_regex)
        self.ignore_case = bool(ignore_case)
        self.whole_word = bool(whole_word)
        flags = re.IGNORECASE if self.ignore_case else 0
        try:
            body = pattern if self.use_regex else re.escape(pattern)
            if self.whole_word:
                body = r"\b(?:%s)\b" % body
            self.compiled = re.compile(body, flags)
        except re.error as err:
            raise ValueError(str(err)) from err

    def find(self, text, start=0):
        return self.compiled.search(text, start)

    def replace_in(self, text, repl, count=0):
        if self.use_regex:
            return self.compiled.subn(repl, text, count=count)

        def _literal(_match, replacement=repl):
            return replacement

        return self.compiled.subn(_literal, text, count=count)


def search_window(text, start, use_regex):
    """Limit regex scans on huge buffers. Returns (slice, offset, limited)."""
    if not use_regex or len(text) <= MAX_REGEX_CHARS:
        return text[start:], start, False
    return text[start : start + MAX_REGEX_CHARS], start, True


class Document:
    """Editor buffer. GUI tabs and the TUI are views of this object."""

    def __init__(self, path, text="", encoding="utf-8", newline=NEWLINE_LF, readonly=False):
        self.path = resolve_doc_path(path)
        self.text = text
        self.encoding = encoding
        self.newline = newline
        self.readonly = readonly
        self.modified = False

    @classmethod
    def blank(cls, path):
        return cls(path)

    @classmethod
    def open(cls, path):
        text, encoding, newline = read_text_file_smart(path)
        readonly = not os.access(path, os.W_OK)
        return cls(path, text, encoding, newline, readonly=readonly)

    def save(self, text, encoding=None, path=None):
        """Atomic write. On success updates this document and clears modified."""
        dest = resolve_doc_path(path) if path else self.path
        codec = encoding or self.encoding
        write_text_file(dest, text, codec, self.newline)
        self.path = dest
        self.text = text
        self.encoding = codec
        self.modified = False
        self.readonly = False

    def write(self, text=None, encoding=None):
        self.save(self.text if text is None else text, encoding=encoding)


class DocumentView:
    """View mixin: path, encoding, newline, modified, and readonly live on self.doc."""

    @property
    def file_path(self):
        return self.doc.path

    @file_path.setter
    def file_path(self, value):
        self.doc.path = resolve_doc_path(value)

    @property
    def file_encoding(self):
        return self.doc.encoding

    @file_encoding.setter
    def file_encoding(self, value):
        self.doc.encoding = normalize_codec(value)

    @property
    def file_newline(self):
        return self.doc.newline

    @file_newline.setter
    def file_newline(self, value):
        self.doc.newline = value

    @property
    def is_modified(self):
        return self.doc.modified

    @is_modified.setter
    def is_modified(self, value):
        self.doc.modified = bool(value)

    @property
    def is_readonly(self):
        return self.doc.readonly

    @is_readonly.setter
    def is_readonly(self, value):
        self.doc.readonly = bool(value)


# ---- Pygments ----
try:
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.util import ClassNotFound
except ImportError:
    get_lexer_for_filename = None
    TextLexer = None
    ClassNotFound = Exception


def get_best_lexer(filename):
    if not get_lexer_for_filename:
        return None
    try:
        return get_lexer_for_filename(filename)
    except ClassNotFound:
        return TextLexer()


# ==========================================
# PART 1: TUI (prompt_toolkit)
# ==========================================
try:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window, FloatContainer, Float
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import TextArea, Frame, Dialog, Button, Label, SearchToolbar
    from prompt_toolkit.lexers import PygmentsLexer
    from prompt_toolkit.shortcuts.dialogs import yes_no_dialog
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.styles import Style

    try:
        import pyperclip
        from prompt_toolkit.clipboard import Clipboard, ClipboardData

        class SystemClipboard(Clipboard):
            def set_data(self, data: ClipboardData) -> None:
                pyperclip.copy(data.text)

            def get_data(self) -> ClipboardData:
                return ClipboardData(pyperclip.paste())

        tui_clipboard = SystemClipboard()
    except ImportError:
        from prompt_toolkit.clipboard import InMemoryClipboard

        tui_clipboard = InMemoryClipboard()

except ImportError:
    Application = None
    tui_clipboard = None


class AstraEditTUI(DocumentView):
    """Terminal view of a Document."""

    def __init__(self, file_path):
        self.doc = Document.blank(file_path)
        self.binary_blocked = False
        self._utf8_retry = False

        self.search_field = SearchToolbar()
        lexer = None
        if get_lexer_for_filename:
            best = get_best_lexer(self.file_path)
            if best is not None:
                lexer = PygmentsLexer(best.__class__)

        initial_text = ""
        if os.path.exists(self.file_path):
            if is_binary_file(self.file_path):
                initial_text = t("tui_binary")
                self.binary_blocked = True
            else:
                self.doc = Document.open(self.file_path)
                initial_text = self.doc.text
                draft = newer_autosave(self.file_path)
                if draft is not None:
                    self.status_pending = t(
                        "autosave_hint", name=pathlib.Path(draft).name
                    )
        else:
            draft = newer_autosave(self.file_path)
            if draft is not None:
                try:
                    self.doc = Document.open(str(draft))
                    self.doc.path = resolve_doc_path(self.file_path)
                    self.doc.modified = True
                    initial_text = self.doc.text
                    self.status_pending = t(
                        "autosave_hint", name=pathlib.Path(draft).name
                    )
                except (OSError, UnicodeError, ValueError):
                    pass

        self.editor = TextArea(
            text=initial_text,
            scrollbar=True,
            line_numbers=True,
            lexer=lexer,
            multiline=True,
            search_field=self.search_field,
            focus_on_click=True,
        )

        self.editor.buffer.on_text_changed += lambda _: self.on_change()
        self.frame = Frame(self.editor, title=self.get_title())

        self.status_text = getattr(self, "status_pending", None) or t("status_tui")
        self.footer = Window(
            height=1,
            content=FormattedTextControl(self.get_status_bar),
            style="class:status",
        )
        self.kb = self.create_key_bindings()

    def get_title(self):
        mark = "*" if self.is_modified else ""
        return f"{APP_NAME} [TUI] – {self.file_path} {mark}"

    def on_change(self):
        if not self.is_modified:
            self.is_modified = True
            self.frame.title = self.get_title()

    def get_status_bar(self):
        row = self.editor.document.cursor_position_row + 1
        col = self.editor.document.cursor_position_col + 1
        return [("class:status", t("ln_col", row=row, col=col, status=self.status_text))]

    def _pop_float(self, app):
        if app.layout.container.floats:
            app.layout.container.floats.pop()
        app.layout.focus(self.editor)

    def create_key_bindings(self):
        kb = KeyBindings()

        @kb.add("c-s")
        def _(event):
            self.save_current()

        @kb.add("c-q")
        async def _(event):
            if self.is_modified:
                if await yes_no_dialog(t("exit_title"), t("exit_save")).run_async():
                    if not self.save_current():
                        return
            event.app.exit()

        @kb.add("c-f")
        def _(event):
            event.app.layout.focus(self.search_field)

        @kb.add("f2")
        def _(event):
            self.save_as_dialog(event.app)

        @kb.add("c-g")
        def _(event):
            self.goto_line_dialog(event.app)

        @kb.add("f5")
        def _(event):
            self.run_script(event.app)

        @kb.add("f8")
        def _(event):
            self.toggle_language()

        editor_focus = has_focus(self.editor.buffer)

        @kb.add("enter", filter=editor_focus)
        def _(event):
            buf = self.editor.buffer
            line = buf.document.current_line_before_cursor
            buf.insert_text("\n" + next_line_indent(line))

        @kb.add("tab", filter=editor_focus)
        def _(event):
            buf = self.editor.buffer
            before = buf.document.current_line_before_cursor
            i = len(before)
            while i > 0 and (before[i - 1].isalnum() or before[i - 1] == "_"):
                i -= 1
            word = before[i:]
            snippet = SNIPPETS.get(word)
            if snippet and (i == 0 or before[i - 1] in " \t"):
                buf.delete_before_cursor(count=len(word))
                expanded, _first = expand_snippet(snippet)
                buf.insert_text(expanded)
                return
            buf.insert_text(" " * DEFAULT_TAB_SIZE)

        # Terminals send Ctrl+/ as ASCII 0x1F (prompt_toolkit: c-_). There is no c-slash.
        @kb.add("c-_", filter=editor_focus, eager=True)
        def _(event):
            buf = self.editor.buffer
            doc = buf.document
            row = doc.cursor_position_row
            line = doc.current_line
            new_line = toggle_hash_comments([line])[0][0]
            start = doc.translate_row_col_to_index(row, 0)
            buf.cursor_position = start + len(line)
            buf.delete_before_cursor(count=len(line))
            buf.insert_text(new_line)

        return kb

    def apply_language(self):
        self.status_text = t("status_tui")
        self.frame.title = self.get_title()

    def toggle_language(self):
        set_lang("pl" if get_lang() == "en" else "en")
        save_config({"language": get_lang()})
        self.apply_language()

    def save_current(self, encoding=None):
        if self.binary_blocked:
            self.status_text = t("binary_save_blocked")
            return False
        if encoding is None and self._utf8_retry:
            encoding = "utf-8"
            self._utf8_retry = False
        codec = encoding or self.file_encoding
        try:
            self.doc.save(self.editor.text, encoding=codec)
            self._utf8_retry = False
            self.frame.title = self.get_title()
            self.status_text = t("status_tui")
            return True
        except UnicodeEncodeError:
            self._utf8_retry = True
            self.status_text = t("encode_retry_utf8", enc=codec)
            return False
        except OSError as e:
            self.status_text = t("write_error", path=self.file_path, err=e)
            return False

    def goto_line_dialog(self, app):
        tf = TextArea(multiline=False)

        def go():
            try:
                line_num = int(tf.text.strip())
            except ValueError:
                self.status_text = t("invalid_line")
                return
            doc = self.editor.buffer.document
            if line_num < 1 or line_num > doc.line_count:
                self.status_text = t("invalid_line")
                return
            self.editor.buffer.cursor_position = doc.translate_row_col_to_index(
                line_num - 1, 0
            )
            self.status_text = t("status_tui")
            self._pop_float(app)

        dialog = Dialog(
            title=t("dlg_goto"),
            body=HSplit([Label(t("dlg_line_number")), tf]),
            buttons=[
                Button(t("dlg_ok"), handler=go),
                Button(t("dlg_cancel"), handler=lambda: self._pop_float(app)),
            ],
        )
        app.layout.container.floats.append(Float(content=dialog))
        app.layout.focus(tf)

    def save_as_dialog(self, app):
        tf = TextArea(multiline=False)

        def save():
            path = tf.text.strip()
            if not path:
                return
            dest = resolve_doc_path(path)
            try:
                self.doc.save(self.editor.text, path=dest)
            except UnicodeEncodeError:
                self._utf8_retry = True
                self.status_text = t("encode_retry_utf8", enc=self.file_encoding)
                return
            except OSError as e:
                self.status_text = t("write_error", path=dest, err=e)
                return
            self.binary_blocked = False
            self.frame.title = self.get_title()
            self._pop_float(app)

        dialog = Dialog(
            title=t("dlg_save_as"),
            body=HSplit([Label(t("dlg_path")), tf]),
            buttons=[
                Button(t("dlg_ok"), handler=save),
                Button(t("dlg_cancel"), handler=lambda: self._pop_float(app)),
            ],
        )
        app.layout.container.floats.append(Float(content=dialog))
        app.layout.focus(tf)

    def run_script(self, app):
        if not is_python_source(self.file_path):
            self.status_text = t("run_only_python")
            return
        if self.binary_blocked:
            self.status_text = t("binary_save_blocked")
            return
        if not self.save_current():
            return

        def _run():
            name = pathlib.Path(self.file_path).name
            print(f"\n{'=' * 60}")
            print(f"  {t('running', name=name)}")
            print(f"{'=' * 60}\n")
            exe = resolve_python_executable(self.file_path)
            completed = subprocess.run(
                [exe, "-u", self.file_path],
                cwd=str(pathlib.Path(self.file_path).parent),
            )
            print(f"\n{'=' * 60}")
            print(f"  {t('finished', code=completed.returncode)}")
            print(f"{'=' * 60}")
            try:
                input(f"\n{t('press_enter')}")
            except EOFError:
                pass

        # run_in_terminal works on Windows; suspend_to_background/resume do not.
        app.run_in_terminal(_run)

    def run(self):
        style = Style.from_dict({
            "status": "bg:#007acc #ffffff",
            "frame.label": "#ffffff bold",
            "search": "bg:cyan #000000",
        })
        layout = Layout(
            FloatContainer(HSplit([self.frame, self.search_field, self.footer]), floats=[])
        )
        try:
            Application(
                layout=layout,
                key_bindings=self.kb,
                full_screen=True,
                mouse_support=True,
                style=style,
                clipboard=tui_clipboard,
            ).run()
        finally:
            clear_terminal()


# ==========================================
# PART 2: GUI (Tkinter)
# ==========================================
try:
    import tkinter as tk
    from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, ttk
except ImportError:
    tk = None


class EditorTab(DocumentView):
    """GUI view of a Document (widgets only)."""

    def __init__(self, parent, file_path, app):
        self.app = app
        self.doc = Document.blank(file_path)
        self._ln_count = -1
        self._ln_width = 0
        self._hl_job = None
        self._lexer = None
        self._lexer_key = None
        self.disk_mtime = None

        self.frame = tk.Frame(parent, bg=app.bg_color)

        container = tk.Frame(self.frame, bg=app.bg_color)
        container.pack(fill="both", expand=True)

        self.line_numbers = tk.Text(
            container,
            width=5,
            padx=3,
            takefocus=0,
            border=0,
            bg=app.line_num_bg,
            fg=app.line_num_fg,
            state="disabled",
            font=app.editor_font,
        )
        self.line_numbers.pack(side="left", fill="y")

        right = tk.Frame(container, bg=app.bg_color)
        right.pack(side="left", fill="both", expand=True)

        self.hscroll = tk.Scrollbar(right, orient="horizontal", bg=app.line_num_bg)
        self.hscroll.pack(side="bottom", fill="x")

        self.text_area = scrolledtext.ScrolledText(
            right,
            wrap="none",
            undo=True,
            bg=app.bg_color,
            fg=app.fg_color,
            insertbackground=app.cursor_color,
            selectbackground=app.selection_color,
            font=app.editor_font,
            border=0,
            tabs=app.tab_pixels,
        )
        self.text_area.pack(side="top", fill="both", expand=True)
        self.hscroll.config(command=self.text_area.xview)
        self.text_area.config(xscrollcommand=self.hscroll.set)

        self.text_area.vbar.config(command=self.on_scrollbar)

        tags = {
            "Keyword": "#569cd6",
            "Name.Builtin": "#dcdcaa",
            "Comment": "#6a9955",
            "String": "#ce9178",
            "Number": "#b5cea8",
            "Operator": "#d4d4d4",
            "Punctuation": "#d4d4d4",
            "Name": "#9cdcfe",
        }
        for tag, color in tags.items():
            self.text_area.tag_config(tag, foreground=color)

        self.text_area.tag_config("matching_bracket", background="#404040", borderwidth=1)

        self.text_area.bind("<<Modified>>", self.on_modified)
        self.text_area.bind("<KeyRelease>", self.on_key_release_combined)
        self.text_area.bind("<Button-1>", lambda e: self.app.root.after(10, self.update_combined))
        self.text_area.bind("<<Paste>>", lambda e: self.app.root.after(20, self._after_paste), add="+")
        self.text_area.bind("<Return>", self.on_return)
        self.text_area.bind("<Tab>", self.on_tab_key)
        self.text_area.bind("<ISO_Left_Tab>", self.on_shift_tab)
        self.text_area.bind("<Shift-Tab>", self.on_shift_tab)
        self.text_area.bind("<Control-slash>", self.toggle_comment)
        self.text_area.bind("<Control-space>", self.autocomplete)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.text_area.bind(seq, lambda e: self.app.root.after_idle(self.update_line_numbers), add="+")

        self.load_file()

    def load_file(self):
        path = self.file_path
        exists = os.path.exists(path)
        if exists and is_binary_file(path):
            messagebox.showerror(t("error"), t("binary_open", path=path))
            return False

        draft = newer_autosave(path)
        try:
            restored = False
            if draft is not None and messagebox.askyesno(
                t("autosave_title"),
                t("autosave_restore", name=pathlib.Path(path).name),
            ):
                self.doc = Document.open(str(draft))
                self.doc.path = resolve_doc_path(path)
                self.doc.modified = True
                restored = True
            elif exists:
                self.doc = Document.open(path)
            else:
                self.disk_mtime = None
                self.update_line_numbers()
                self.text_area.edit_modified(False)
                self.is_modified = False
                return True

            self.text_area.insert("1.0", self.doc.text)
            self.update_syntax_highlighting(force=True)
            self.text_area.edit_modified(False)
            if not restored:
                self.is_modified = False

            if self.doc.readonly:
                self.text_area.config(state="disabled")
                messagebox.showwarning(
                    t("readonly_title"), t("readonly_msg", path=path)
                )
        except (OSError, UnicodeError, ValueError) as e:
            messagebox.showerror(t("error"), t("load_error", err=e))
            return False

        self.disk_mtime = file_mtime(self.file_path)
        self.update_line_numbers()
        self.text_area.edit_modified(False)
        if not self.doc.modified:
            self.is_modified = False
        return True

    def on_scrollbar(self, *args):
        self.text_area.yview(*args)
        self.line_numbers.yview(*args)

    def on_modified(self, event=None):
        if self.text_area.edit_modified():
            if not self.is_modified:
                self.is_modified = True
                self.app.update_tab_title(self)
            self.text_area.edit_modified(False)

    def _char_count(self):
        try:
            counted = self.text_area.count("1.0", "end-1c", "chars")
            if counted is None:
                return 0
            return int(counted[0] if isinstance(counted, tuple) else counted)
        except (tk.TclError, TypeError, ValueError):
            return 0

    def cached_lexer(self):
        if not get_lexer_for_filename:
            return None
        if self._lexer is not None and self._lexer_key == self.file_path:
            return self._lexer
        self._lexer = get_best_lexer(self.file_path)
        self._lexer_key = self.file_path
        return self._lexer

    def invalidate_lexer(self):
        self._lexer = None
        self._lexer_key = None

    def schedule_highlight(self, force=False):
        if self._hl_job is not None:
            try:
                self.app.root.after_cancel(self._hl_job)
            except tk.TclError:
                pass
            self._hl_job = None
        if force:
            self.update_syntax_highlighting(force=True)
            return
        _mode, delay = highlight_policy(self._char_count())
        try:
            self._hl_job = self.app.root.after(int(delay * 1000), self._hl_fire)
        except tk.TclError:
            self._hl_job = None

    def _hl_fire(self):
        self._hl_job = None
        self.update_syntax_highlighting()

    def on_key_release_combined(self, event=None):
        self.update_line_numbers()
        self.app.update_cursor_position()
        self.highlight_matching_bracket()
        self.schedule_highlight()

    def update_combined(self):
        self.update_line_numbers()
        self.app.update_cursor_position()
        self.highlight_matching_bracket()

    def _after_paste(self):
        self.update_line_numbers()
        self.schedule_highlight(force=True)
        self.app.update_cursor_position()
        self.highlight_matching_bracket()

    def apply_font(self, font, tab_pixels):
        self.text_area.configure(font=font, tabs=tab_pixels)
        self.line_numbers.configure(font=font)

    def on_return(self, event=None):
        text = self.text_area
        before = text.get("insert linestart", "insert")
        text.insert("insert", "\n" + next_line_indent(before, self.app.tab_size, self.app.use_spaces))
        self.update_line_numbers()
        return "break"

    def _word_before_cursor(self):
        before = self.text_area.get("insert linestart", "insert")
        i = len(before)
        while i > 0 and (before[i - 1].isalnum() or before[i - 1] == "_"):
            i -= 1
        return before[i:], i

    def on_tab_key(self, event=None):
        text = self.text_area
        try:
            text.index("sel.first")
            return self._indent_selection(1)
        except tk.TclError:
            pass
        word, col = self._word_before_cursor()
        snippet = SNIPPETS.get(word)
        before = text.get("insert linestart", "insert")
        if snippet and (col == 0 or before[col - 1] in " \t"):
            start = "%s linestart + %dc" % (tk.INSERT, col)
            text.delete(start, tk.INSERT)
            ins = text.index(tk.INSERT)
            expanded, first = expand_snippet(snippet)
            text.insert(tk.INSERT, expanded)
            if first:
                loc = text.search(first, ins, stopindex=tk.INSERT)
                if loc:
                    text.tag_remove("sel", "1.0", tk.END)
                    text.tag_add("sel", loc, "%s+%dc" % (loc, len(first)))
                    text.mark_set(tk.INSERT, "%s+%dc" % (loc, len(first)))
            self.update_line_numbers()
            self.schedule_highlight(force=True)
            return "break"
        pad = (" " * self.app.tab_size) if self.app.use_spaces else "\t"
        text.insert(tk.INSERT, pad)
        return "break"

    def on_shift_tab(self, event=None):
        return self._indent_selection(-1)

    def _indent_selection(self, direction):
        text = self.text_area
        try:
            start_line = int(text.index("sel.first").split(".")[0])
            end_index = text.index("sel.last")
            end_line = int(end_index.split(".")[0])
            if end_index.split(".")[1] == "0":
                end_line -= 1
        except tk.TclError:
            start_line = end_line = int(text.index(tk.INSERT).split(".")[0])
        pad = " " * self.app.tab_size
        text.edit_separator()
        for line in range(start_line, end_line + 1):
            if direction > 0:
                text.insert("%d.0" % line, pad)
            else:
                got = text.get("%d.0" % line, "%d.%d" % (line, self.app.tab_size))
                if got.startswith(pad):
                    text.delete("%d.0" % line, "%d.%d" % (line, len(pad)))
                elif got.startswith("\t"):
                    text.delete("%d.0" % line, "%d.1" % line)
                else:
                    n = len(got) - len(got.lstrip(" "))
                    if n:
                        text.delete("%d.0" % line, "%d.%d" % (line, n))
        self.update_line_numbers()
        return "break"

    def toggle_comment(self, event=None):
        text = self.text_area
        try:
            start = text.index("sel.first linestart")
            end = text.index("sel.last")
            if end.endswith(".0"):
                end = text.index("%s-1c" % end)
            end = text.index("%s lineend" % end)
        except tk.TclError:
            start = text.index("insert linestart")
            end = text.index("insert lineend")
        block = text.get(start, end)
        new_lines, _ = toggle_hash_comments(block.split("\n"))
        text.edit_separator()
        text.delete(start, end)
        text.insert(start, "\n".join(new_lines))
        self.update_line_numbers()
        self.schedule_highlight(force=True)
        return "break"

    def insert_snippet(self, key):
        body = SNIPPETS.get(key)
        if not body:
            return
        text = self.text_area
        expanded, first = expand_snippet(body)
        ins = text.index(tk.INSERT)
        text.insert(tk.INSERT, expanded)
        if first:
            loc = text.search(first, ins, stopindex=tk.INSERT)
            if loc:
                text.tag_remove("sel", "1.0", tk.END)
                text.tag_add("sel", loc, "%s+%dc" % (loc, len(first)))
                text.mark_set(tk.INSERT, "%s+%dc" % (loc, len(first)))
        self.update_line_numbers()
        self.schedule_highlight(force=True)

    def autocomplete(self, event=None):
        text = self.text_area
        prefix, _col = self._word_before_cursor()
        if not prefix:
            return "break"
        content = text.get("1.0", "end-1c")
        words = buffer_completions(content, prefix)
        if not words:
            return "break"
        if len(words) == 1:
            text.insert(tk.INSERT, words[0][len(prefix):])
            return "break"
        self.app.show_completions(self, words, prefix)
        return "break"

    def update_line_numbers(self):
        line_count = int(self.text_area.index("end-1c").split(".")[0])
        width = max(4, len(str(line_count)))
        if line_count != self._ln_count or width != self._ln_width:
            self._ln_count = line_count
            self._ln_width = width
            self.line_numbers.config(state="normal", width=width)
            self.line_numbers.delete("1.0", "end")
            self.line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, line_count + 1)))
            self.line_numbers.config(state="disabled")
        try:
            self.line_numbers.yview_moveto(self.text_area.yview()[0])
        except tk.TclError:
            pass

    def highlight_matching_bracket(self):
        self.text_area.tag_remove("matching_bracket", "1.0", tk.END)
        content = self.text_area.get("1.0", "end-1c")
        if not content:
            return
        cursor = self.text_area.index(tk.INSERT)
        offset = tk_index_to_offset(content, cursor)
        pairs = {"(": ")", "[": "]", "{": "}"}
        rev = {v: k for k, v in pairs.items()}
        if offset > 0 and content[offset - 1] in rev:
            start = offset - 1
            self_ch = content[start]
            other = rev[self_ch]
            direction = -1
        elif offset < len(content) and content[offset] in pairs:
            start = offset
            self_ch = content[start]
            other = pairs[self_ch]
            direction = 1
        else:
            return
        lexer = self.cached_lexer()
        mask = code_char_mask(content, lexer, start)
        if not mask[start]:
            return
        match = find_matching_bracket(content, start, direction, self_ch, other, mask)
        if match is None:
            return
        a = offset_to_tk_index(content, start)
        b = offset_to_tk_index(content, match)
        self.text_area.tag_add("matching_bracket", a, "%s+1c" % a)
        self.text_area.tag_add("matching_bracket", b, "%s+1c" % b)

    def _clear_syntax_tags(self, start="1.0", end="end"):
        for tag in self.text_area.tag_names():
            if tag not in ("sel", "matching_bracket"):
                self.text_area.tag_remove(tag, start, end)

    def _visible_lines(self):
        first = int(self.text_area.index("@0,0").split(".")[0])
        last = int(self.text_area.index("@0,%d" % max(1, self.text_area.winfo_height())).split(".")[0])
        return first, last

    def _apply_tokens(self, lexer, content, line_idx, col_idx):
        for token, text in lexer.get_tokens(content):
            tag_name = token_tag(token)
            lines = text.split("\n")
            start_idx = "%d.%d" % (line_idx, col_idx)
            if len(lines) > 1:
                line_idx += len(lines) - 1
                col_idx = len(lines[-1])
            else:
                col_idx += len(text)
            end_idx = "%d.%d" % (line_idx, col_idx)
            if tag_name:
                self.text_area.tag_add(tag_name, start_idx, end_idx)
        return line_idx, col_idx

    def update_syntax_highlighting(self, force=False):
        if not get_lexer_for_filename:
            return
        content = self.text_area.get("1.0", "end-1c")
        nbytes = self._char_count()
        mode, _delay = highlight_policy(nbytes)
        if mode == "off":
            self._clear_syntax_tags()
            return
        lexer = self.cached_lexer()
        if lexer is None:
            return
        try:
            if mode == "visible":
                first, last = self._visible_lines()
                first = max(1, first - 8)
                last = last + 8
                start = "%d.0" % first
                end = "%d.end" % last
                fragment = self.text_area.get(start, end)
                self._clear_syntax_tags(start, end)
                self._apply_tokens(lexer, fragment, first, 0)
            else:
                self._clear_syntax_tags()
                self._apply_tokens(lexer, content, 1, 0)
        except (ValueError, TypeError):
            pass

    def save(self, path=None, encoding=None):
        if self.is_readonly and path is None:
            return False
        dest = resolve_doc_path(path) if path else self.file_path
        codec = encoding or self.file_encoding
        content = self.text_area.get("1.0", "end-1c")
        try:
            self.doc.save(content, encoding=codec, path=dest)
        except UnicodeEncodeError:
            if not messagebox.askyesno(
                t("save_error_title"), t("encode_retry_utf8", enc=codec)
            ):
                return False
            try:
                self.doc.save(content, encoding="utf-8", path=dest)
            except OSError as e:
                messagebox.showerror(t("save_error_title"), str(e))
                return False
        except OSError as e:
            messagebox.showerror(t("save_error_title"), str(e))
            return False
        self.disk_mtime = file_mtime(self.file_path)
        self.invalidate_lexer()
        self.app.update_tab_title(self)
        return True

    def get_short_name(self):
        return pathlib.Path(self.file_path).name


class AstraEditGUI:
    def __init__(self, file_paths=None):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} [GUI]")
        self.root.geometry("1100x800")
        if ICON_FILE.is_file():
            try:
                self.root.iconbitmap(default=str(ICON_FILE))
            except Exception:
                try:
                    self.root.iconbitmap(str(ICON_FILE))
                except Exception:
                    pass

        self.bg_color = "#1e1e1e"
        self.fg_color = "#d4d4d4"
        self.cursor_color = "#ffffff"
        self.selection_color = "#264f78"
        self.line_num_bg = "#252526"
        self.line_num_fg = "#858585"
        self.console_bg = "#111111"
        self.console_fg = "#cccccc"

        cfg = load_config()
        self.autosave_enabled = bool(cfg.get("autosave", True))
        self.autosave_interval = 30000
        self.tab_size = int(cfg.get("tab_size", DEFAULT_TAB_SIZE) or DEFAULT_TAB_SIZE)
        self.use_spaces = bool(cfg.get("use_spaces", True))
        self.font_size = int(cfg.get("font_size", DEFAULT_FONT_SIZE) or DEFAULT_FONT_SIZE)
        self.python_executable = cfg.get("python_executable") or ""
        self.show_explorer = bool(cfg.get("show_explorer", True))
        self.ignore_case = bool(cfg.get("ignore_case", True))
        self.whole_word = bool(cfg.get("whole_word", False))

        families = set(tkfont.families(self.root))
        self.mono_font = "TkFixedFont"
        for name in MONO_FONT_CANDIDATES:
            if name in families:
                self.mono_font = name
                break
        self.editor_font = (self.mono_font, self.font_size)
        self.tab_pixels = self._measure_tab_pixels()

        self.find_window = None
        self.find_entry = None
        self.regex_var = None
        self.case_var = None
        self.word_var = None
        self.last_search = ""
        self.use_regex = False
        self._complete_win = None
        self._reload_open = False
        self.explorer_root = None

        self._tabs = []
        self.runner = ProcessManager()
        self.msg_queue = queue.Queue()
        self.recent_menu = None

        self.setup_ui()
        self.setup_menu()
        self.setup_bindings()

        if file_paths:
            for fp in file_paths:
                self.open_file(fp)
            if not self._tabs:
                self.new_tab()
        else:
            restored = False
            for path in cfg.get("session_files") or []:
                if os.path.isfile(path):
                    self.open_file(path)
                    restored = True
            if not restored:
                self.new_tab()
            else:
                idx = cfg.get("session_index", 0)
                if isinstance(idx, int) and 0 <= idx < len(self._tabs):
                    self.notebook.select(self._tabs[idx].frame)

        self._set_explorer_root(os.getcwd())
        self.schedule_autosave()
        self.root.after(100, self.process_queue)
        self.root.after(WATCH_INTERVAL_MS, self._watch_files)

    def _measure_tab_pixels(self):
        sample = tkfont.Font(root=self.root, font=(self.mono_font, self.font_size))
        return sample.measure(" " * self.tab_size)

    def setup_ui(self):
        self.status_var = tk.StringVar(value=t("status_ready"))
        self.status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg="#007acc",
            fg="white",
            anchor="w",
            padx=5,
            font=("Arial", 9),
        )
        self.status_bar.pack(side="bottom", fill="x")

        self.hpaned = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL, sashwidth=4, bg="#333333"
        )
        self.hpaned.pack(fill="both", expand=True)

        self.explorer_frame = tk.Frame(self.hpaned, bg=self.line_num_bg, width=220)
        exp_header = tk.Frame(self.explorer_frame, bg="#252526")
        exp_header.pack(fill="x")
        self.explorer_title = tk.Label(
            exp_header,
            text=t("explorer_title"),
            bg="#252526",
            fg="white",
            font=("Arial", 9, "bold"),
            anchor="w",
        )
        self.explorer_title.pack(side="left", padx=8, pady=4)

        self.explorer_tree = ttk.Treeview(
            self.explorer_frame, show="tree", selectmode="browse"
        )
        exp_scroll = ttk.Scrollbar(
            self.explorer_frame, orient="vertical", command=self.explorer_tree.yview
        )
        self.explorer_tree.configure(yscrollcommand=exp_scroll.set)
        exp_scroll.pack(side="right", fill="y")
        self.explorer_tree.pack(side="left", fill="both", expand=True)
        self.explorer_tree.bind("<<TreeviewOpen>>", self._on_explorer_open)
        self.explorer_tree.bind("<Double-1>", self._on_explorer_activate)
        self.explorer_tree.bind("<Return>", self._on_explorer_activate)

        self.paned_window = tk.PanedWindow(
            self.hpaned, orient=tk.VERTICAL, sashwidth=4, bg="#333333"
        )
        if self.show_explorer:
            self.hpaned.add(self.explorer_frame, minsize=140, width=220)
        self.hpaned.add(self.paned_window, stretch="always", minsize=320)

        editor_container = tk.Frame(self.paned_window, bg=self.bg_color)
        self.paned_window.add(editor_container, stretch="always", height=500)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#2d2d2d",
            foreground=self.fg_color,
            padding=[10, 5],
            borderwidth=0,
        )
        style.map("TNotebook.Tab", background=[("selected", "#007acc")])
        style.configure(
            "Treeview",
            background=self.bg_color,
            foreground=self.fg_color,
            fieldbackground=self.bg_color,
            borderwidth=0,
        )
        style.map("Treeview", background=[("selected", "#007acc")])

        self.notebook = ttk.Notebook(editor_container)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<ButtonPress-1>", self.on_tab_click)
        self.notebook.bind("<Button-2>", self.on_tab_middle_click)

        self.tab_context_menu = tk.Menu(self.root, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        self.notebook.bind("<Button-3>", self.show_tab_context_menu)

        console_frame = tk.Frame(self.paned_window, bg=self.console_bg)
        self.paned_window.add(console_frame, stretch="never", height=250)

        cons_toolbar = tk.Frame(console_frame, bg="#252526", height=28)
        cons_toolbar.pack(fill="x", side="top")

        self.console_title = tk.Label(
            cons_toolbar,
            text=f"📟 {t('console_title')}",
            bg="#252526",
            fg="white",
            font=("Arial", 9, "bold"),
        )
        self.console_title.pack(side="left", padx=8)

        self.clear_btn = tk.Button(
            cons_toolbar,
            text=f"🗑 {t('btn_clear')}",
            command=self.clear_console,
            bg="#404040",
            fg="white",
            border=0,
            font=("Arial", 8),
            padx=8,
            pady=2,
        )
        self.clear_btn.pack(side="right", padx=5, pady=3)

        self.stop_btn = tk.Button(
            cons_toolbar,
            text=f"⬛ {t('btn_stop')}",
            command=self.stop_process,
            bg="#8b0000",
            fg="white",
            border=0,
            font=("Arial", 8, "bold"),
            state="disabled",
            padx=8,
            pady=2,
        )
        self.stop_btn.pack(side="right", padx=5, pady=3)

        self.console_area = scrolledtext.ScrolledText(
            console_frame,
            bg=self.console_bg,
            fg=self.console_fg,
            font=("Consolas", 10),
            state="disabled",
            border=0,
        )
        self.console_area.pack(fill="both", expand=True)
        self.console_area.tag_config("stderr", foreground="#ff6b6b")
        self.console_area.tag_config("stdin", foreground="#00ff00")
        self.console_area.tag_config("info", foreground="#61afef")

        input_frame = tk.Frame(console_frame, bg=self.console_bg, height=30)
        input_frame.pack(fill="x", side="bottom")

        tk.Label(
            input_frame,
            text=">>> ",
            bg=self.console_bg,
            fg="#00ff00",
            font=("Consolas", 10, "bold"),
        ).pack(side="left", padx=5)

        self.input_entry = tk.Entry(
            input_frame,
            bg=self.console_bg,
            fg="white",
            insertbackground="white",
            font=("Consolas", 10),
            border=0,
            relief="flat",
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        self.input_entry.bind("<Return>", self.send_input)
        self.console_area.configure(font=(self.mono_font, max(9, self.font_size - 1)))
        self.input_entry.configure(font=(self.mono_font, max(9, self.font_size - 1)))

    def _tab_index_at(self, event):
        try:
            ident = self.notebook.tk.call(
                self.notebook._w, "identify", "tab", event.x, event.y
            )
            if ident == "" or ident is None:
                return None
            return int(ident)
        except (tk.TclError, ValueError, TypeError):
            return None

    def _tab_from_index(self, idx):
        tabs = self.notebook.tabs()
        if idx < 0 or idx >= len(tabs):
            return None
        tab_frame = self.notebook.nametowidget(tabs[idx])
        for tab in self._tabs:
            if tab.frame == tab_frame:
                return tab
        return None

    def on_tab_click(self, event):
        idx = self._tab_index_at(event)
        if idx is None:
            return
        try:
            x, y, width, height = self.notebook.bbox(idx)
        except tk.TclError:
            return
        if event.x > x + width - 25:
            tab = self._tab_from_index(idx)
            if tab:
                self.close_tab(tab)
            return "break"

    def on_tab_middle_click(self, event):
        idx = self._tab_index_at(event)
        if idx is None:
            return
        tab = self._tab_from_index(idx)
        if tab:
            self.close_tab(tab)
        return "break"

    def setup_menu(self):
        menubar = tk.Menu(self.root, bg=self.bg_color, fg=self.fg_color)

        filemenu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        filemenu.add_command(label=t("menu_new"), command=self.new_tab)
        filemenu.add_command(label=t("menu_open"), command=self.open_file_dialog)
        filemenu.add_separator()
        filemenu.add_command(label=t("menu_save"), command=self.save_current)
        filemenu.add_command(label=t("menu_save_as"), command=self.save_as)
        filemenu.add_command(label=t("menu_save_all"), command=self.save_all)
        filemenu.add_separator()
        self.add_recent_files_menu(filemenu)
        filemenu.add_separator()
        filemenu.add_command(label=t("menu_close_tab"), command=self.close_current_tab)
        filemenu.add_command(label=t("menu_quit"), command=self.on_close)
        menubar.add_cascade(label=t("menu_file"), menu=filemenu)

        editmenu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        editmenu.add_command(label=t("menu_undo"), command=self.undo)
        editmenu.add_command(label=t("menu_redo"), command=self.redo)
        editmenu.add_separator()
        editmenu.add_command(label=t("menu_find"), command=self.show_find_dialog)
        editmenu.add_command(label=t("menu_replace"), command=self.show_replace_dialog)
        editmenu.add_command(label=t("menu_goto"), command=self.goto_line_dialog)
        editmenu.add_separator()
        editmenu.add_command(label=t("menu_comment"), command=self.toggle_comment_current)
        snippet_menu = tk.Menu(editmenu, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        for key, snippet_id in SNIPPET_MENU:
            snippet_menu.add_command(
                label=t(key),
                command=lambda sid=snippet_id: self.insert_snippet_current(sid),
            )
        editmenu.add_cascade(label=t("menu_snippets"), menu=snippet_menu)
        menubar.add_cascade(label=t("menu_edit"), menu=editmenu)

        runmenu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        runmenu.add_command(label=f"▶ {t('menu_run_file')}", command=self.run_current_file)
        runmenu.add_command(label=f"⬛ {t('menu_stop')}", command=self.stop_process)
        runmenu.add_separator()
        runmenu.add_command(label=t("menu_interpreter"), command=self.choose_interpreter)
        runmenu.add_command(label=t("menu_interpreter_auto"), command=self.use_auto_interpreter)
        runmenu.add_separator()
        runmenu.add_command(label=f"🗑 {t('menu_clear')}", command=self.clear_console)
        menubar.add_cascade(label=t("menu_run"), menu=runmenu)

        viewmenu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        self.autosave_var = tk.BooleanVar(value=self.autosave_enabled)
        viewmenu.add_checkbutton(
            label=t("menu_autosave"),
            variable=self.autosave_var,
            command=self.toggle_autosave,
        )

        langmenu = tk.Menu(viewmenu, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        self.lang_var = tk.StringVar(value=get_lang())
        langmenu.add_radiobutton(
            label=t("menu_lang_en"),
            variable=self.lang_var,
            value="en",
            command=lambda: self.change_language("en"),
        )
        langmenu.add_radiobutton(
            label=t("menu_lang_pl"),
            variable=self.lang_var,
            value="pl",
            command=lambda: self.change_language("pl"),
        )
        viewmenu.add_cascade(label=t("menu_language"), menu=langmenu)
        viewmenu.add_separator()
        self.explorer_var = tk.BooleanVar(value=self.show_explorer)
        viewmenu.add_checkbutton(
            label=t("menu_explorer"),
            variable=self.explorer_var,
            command=self.toggle_explorer,
        )
        viewmenu.add_separator()
        viewmenu.add_command(label=t("menu_zoom_in"), command=self.zoom_in)
        viewmenu.add_command(label=t("menu_zoom_out"), command=self.zoom_out)
        viewmenu.add_command(label=t("menu_zoom_reset"), command=self.zoom_reset)
        menubar.add_cascade(label=t("menu_view"), menu=viewmenu)

        helpmenu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        helpmenu.add_command(label=t("menu_shortcuts"), command=self.show_help)
        helpmenu.add_separator()
        helpmenu.add_command(label=t("menu_about"), command=self.show_about)
        menubar.add_cascade(label=t("menu_help"), menu=helpmenu)

        self.root.config(menu=menubar)
        self._rebuild_tab_context_menu()

    def _rebuild_tab_context_menu(self):
        self.tab_context_menu.delete(0, "end")
        self.tab_context_menu.add_command(label=t("tab_close"), command=self.close_current_tab)
        self.tab_context_menu.add_command(label=t("tab_close_others"), command=self.close_other_tabs)
        self.tab_context_menu.add_command(label=t("tab_close_all"), command=self.close_all_tabs)

    def change_language(self, lang):
        if get_lang() == lang:
            return
        set_lang(lang)
        save_config({"language": lang})
        self.refresh_ui()

    def refresh_ui(self):
        self.setup_menu()
        self.console_title.config(text=f"📟 {t('console_title')}")
        self.clear_btn.config(text=f"🗑 {t('btn_clear')}")
        self.stop_btn.config(text=f"⬛ {t('btn_stop')}")
        self.explorer_title.config(text=t("explorer_title"))
        self.update_cursor_position()
        if not self.get_current_tab():
            self.status_var.set(t("status_ready"))

    def _bind(self, sequence, fn):
        def handler(event):
            fn()
            return "break"

        self.root.bind(sequence, handler)

    def setup_bindings(self):
        self._bind("<Control-n>", self.new_tab)
        self._bind("<Control-o>", self.open_file_dialog)
        self._bind("<Control-s>", self.save_current)
        self._bind("<Control-Shift-S>", self.save_all)
        self._bind("<Control-Shift-s>", self.save_all)
        self._bind("<Control-w>", self.close_current_tab)
        self._bind("<F2>", self.save_as)
        self._bind("<F1>", self.show_help)
        self._bind("<F5>", self.run_current_file)
        self._bind("<Control-f>", self.show_find_dialog)
        self._bind("<Control-h>", self.show_replace_dialog)
        self._bind("<Control-g>", self.goto_line_dialog)
        self._bind("<F3>", self.find_next)
        self._bind("<Control-z>", self.undo)
        self._bind("<Control-y>", self.redo)
        self._bind("<Control-Tab>", lambda: self.cycle_tab(1))
        self._bind("<Control-Shift-Tab>", lambda: self.cycle_tab(-1))
        self._bind("<Control-ISO_Left_Tab>", lambda: self.cycle_tab(-1))
        self._bind("<Control-Next>", lambda: self.cycle_tab(1))
        self._bind("<Control-Prior>", lambda: self.cycle_tab(-1))
        self._bind("<Control-equal>", self.zoom_in)
        self._bind("<Control-plus>", self.zoom_in)
        self._bind("<Control-minus>", self.zoom_out)
        self._bind("<Control-0>", self.zoom_reset)
        self.root.bind("<Control-MouseWheel>", self._on_zoom_wheel)
        self.root.bind("<Control-Button-4>", lambda e: self.zoom_in() or "break")
        self.root.bind("<Control-Button-5>", lambda e: self.zoom_out() or "break")

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ==========================================
    # RUN CODE
    # ==========================================
    def run_current_file(self):
        tab = self.get_current_tab()
        if not tab:
            return

        if not self.runner.try_start():
            messagebox.showinfo(t("info"), t("process_running"))
            return

        if not is_python_source(tab.file_path):
            self.runner.finish()
            messagebox.showinfo(t("info"), t("run_only_python"))
            return

        if not tab.save():
            self.runner.finish()
            return

        file_path = tab.file_path
        configured = self.python_executable or None
        exe = resolve_python_executable(file_path, configured)

        self.console_area.config(state="normal")
        self.console_area.delete("1.0", tk.END)

        self.log_to_console(f"{'=' * 60}\n", "info")
        self.log_to_console(
            f"  {t('running_with', name=pathlib.Path(file_path).name, python=exe)}\n",
            "info",
        )
        self.log_to_console(f"{'=' * 60}\n\n", "info")

        self.stop_btn.config(state="normal", bg="#ff3333")
        self.input_entry.focus()

        threading.Thread(
            target=self._run_subprocess, args=(file_path, exe), daemon=True
        ).start()

    def _run_subprocess(self, file_path, python_exe=None):
        proc = None
        try:
            proc = popen_script(file_path, python_exe)
            action = self.runner.attach(proc)
            if action == "stop":
                terminate_process_tree(proc)
            else:
                threading.Thread(
                    target=self._reader, args=(proc.stdout, None), daemon=True
                ).start()
                threading.Thread(
                    target=self._reader, args=(proc.stderr, "stderr"), daemon=True
                ).start()
            proc.wait()

            code = proc.returncode if proc else "?"
            self.msg_queue.put(("text", f"\n{'=' * 60}\n", "info"))
            self.msg_queue.put(("text", f"  {t('finished', code=code)}\n", "info"))
            self.msg_queue.put(("text", f"{'=' * 60}\n", "info"))
        except Exception as e:
            self.msg_queue.put(("text", f"\n❌ {t('run_error', err=e)}\n", "stderr"))
        finally:
            self.msg_queue.put(("status", "stopped", None))

    def _reader(self, stream, tag):
        """Flush on newline or a short chunk so input() prompts appear."""
        try:
            buf = []
            while True:
                ch = stream.read(1)
                if ch == "":
                    break
                buf.append(ch)
                if ch == "\n" or len(buf) >= 16:
                    self.msg_queue.put(("text", "".join(buf), tag))
                    buf = []
            if buf:
                self.msg_queue.put(("text", "".join(buf), tag))
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def process_queue(self):
        try:
            while True:
                msg_type, content, tag = self.msg_queue.get_nowait()
                if msg_type == "text":
                    self.log_to_console(content, tag)
                elif msg_type == "status" and content == "stopped":
                    self.stop_btn.config(state="disabled", bg="#8b0000")
                    self.runner.finish()
        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)

    def log_to_console(self, text, tag=None):
        self.console_area.config(state="normal")
        self.console_area.insert(tk.END, text, tag)
        self.console_area.see(tk.END)
        self.console_area.config(state="disabled")

    def send_input(self, event):
        text = self.input_entry.get()
        self.input_entry.delete(0, tk.END)

        proc = self.runner.running_proc()
        if not proc:
            if text:
                self.log_to_console(f"⚠ {t('process_not_running')}\n", "stderr")
            return

        try:
            self.log_to_console(f"{text}\n", "stdin")
            proc.stdin.write(text + "\n")
            proc.stdin.flush()
        except Exception as e:
            self.log_to_console(f"❌ {t('stdin_error', err=e)}\n", "stderr")

    def stop_process(self):
        proc = self.runner.request_stop()
        if proc is None:
            return
        terminate_process_tree(proc)
        self.log_to_console(f"\n⚠ {t('process_stopped')}\n", "stderr")
        self.stop_btn.config(state="disabled", bg="#8b0000")

    def clear_console(self):
        self.console_area.config(state="normal")
        self.console_area.delete("1.0", tk.END)
        self.console_area.config(state="disabled")

    # ==========================================
    # TABS
    # ==========================================
    def new_tab(self, file_path=None):
        if file_path is None:
            file_path = next_untitled_name(tab.file_path for tab in self._tabs)

        tab = EditorTab(self.notebook, file_path, self)
        self._tabs.append(tab)
        self.notebook.add(tab.frame, text=self.format_tab_title(tab))
        self.notebook.select(tab.frame)
        return tab

    def format_tab_title(self, tab):
        title = tab.get_short_name()
        if tab.is_modified:
            title = "● " + title
        if tab.is_readonly:
            title += " 🔒"
        title += "  ×"
        return title

    def update_tab_title(self, tab):
        try:
            tab_id = self.notebook.index(tab.frame)
            self.notebook.tab(tab_id, text=self.format_tab_title(tab))
        except Exception:
            pass

    def get_current_tab(self):
        try:
            current_frame = self.notebook.nametowidget(self.notebook.select())
            for tab in self._tabs:
                if tab.frame == current_frame:
                    return tab
        except Exception:
            pass
        return None

    def close_tab(self, tab, allow_empty=False):
        if tab not in self._tabs:
            return True

        if tab.is_modified:
            self.notebook.select(tab.frame)
            response = messagebox.askyesnocancel(
                t("unsaved_title"), t("unsaved_file", name=tab.get_short_name())
            )
            if response is None:
                return False
            if response and not tab.save():
                return False

        self._tabs.remove(tab)
        self.notebook.forget(tab.frame)

        if not allow_empty and not self._tabs:
            self.new_tab()
        return True

    def close_current_tab(self):
        tab = self.get_current_tab()
        if tab:
            self.close_tab(tab)

    def close_other_tabs(self):
        current = self.get_current_tab()
        if not current:
            return
        for tab in [tab for tab in self._tabs if tab != current]:
            if not self.close_tab(tab):
                break

    def close_all_tabs(self):
        for tab in list(self._tabs):
            if not self.close_tab(tab, allow_empty=True):
                break
        if not self._tabs:
            self.new_tab()

    def on_tab_changed(self, event=None):
        self.update_cursor_position()

    def show_tab_context_menu(self, event):
        idx = self._tab_index_at(event)
        if idx is not None:
            tab = self._tab_from_index(idx)
            if tab:
                self.notebook.select(tab.frame)
        try:
            self.tab_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tab_context_menu.grab_release()

    # ==========================================
    # FILES
    # ==========================================
    def open_file_dialog(self):
        paths = filedialog.askopenfilenames(title=t("dlg_open"))
        for path in paths:
            self.open_file(path)

    def open_file(self, file_path):
        file_path = str(pathlib.Path(file_path).expanduser().resolve())

        for tab in self._tabs:
            if tab.file_path == file_path:
                self.notebook.select(tab.frame)
                return

        if os.path.exists(file_path) and is_binary_file(file_path):
            messagebox.showerror(
                t("error"), t("binary_open", path=pathlib.Path(file_path).name)
            )
            return

        self.new_tab(file_path)
        self.save_recent_file(file_path)
        self._maybe_reveal_in_explorer(file_path)

    def save_current(self):
        tab = self.get_current_tab()
        if not tab:
            return
        if tab.is_readonly:
            messagebox.showinfo(t("readonly_title"), t("readonly_save"))
            self.save_as()
            return
        if tab.save():
            self.status_var.set(t("saved", name=tab.get_short_name()))

    def save_as(self):
        tab = self.get_current_tab()
        if not tab:
            return

        path = filedialog.asksaveasfilename(
            initialfile=tab.get_short_name(),
            initialdir=pathlib.Path(tab.file_path).parent,
        )
        if path:
            dest = str(pathlib.Path(path).resolve())
            if not tab.save(path=dest):
                return
            tab.is_readonly = False
            tab.text_area.config(state="normal")
            self.update_tab_title(tab)
            self.save_recent_file(tab.file_path)
            self.status_var.set(t("saved_as", name=tab.get_short_name()))

    def save_all(self):
        saved = 0
        for tab in self._tabs:
            if tab.is_modified and not tab.is_readonly:
                if tab.save():
                    saved += 1
        self.status_var.set(t("saved_n", n=saved))

    # ==========================================
    # FIND & REPLACE
    # ==========================================
    def _find_dialog_open(self):
        try:
            return self.find_window is not None and bool(self.find_window.winfo_exists())
        except tk.TclError:
            return False

    def _current_find_pattern(self):
        try:
            if self.find_entry is not None and self.find_entry.winfo_exists():
                if self.regex_var is not None:
                    self.use_regex = bool(self.regex_var.get())
                return self.find_entry.get()
        except tk.TclError:
            pass
        return self.last_search

    def show_find_dialog(self):
        if self._find_dialog_open():
            self.find_window.focus()
            return

        self.find_window = tk.Toplevel(self.root)
        self.find_window.title(t("dlg_find"))
        self.find_window.geometry("540x200")
        self.find_window.configure(bg=self.bg_color)
        self.find_window.transient(self.root)

        tk.Label(
            self.find_window, text=t("dlg_search"), bg=self.bg_color, fg=self.fg_color
        ).pack(pady=5)

        self.find_entry = tk.Entry(
            self.find_window,
            width=60,
            bg=self.line_num_bg,
            fg=self.fg_color,
            insertbackground=self.cursor_color,
        )
        self.find_entry.pack(pady=5, padx=10)
        self.find_entry.insert(0, self.last_search)
        self.find_entry.focus()
        self.find_entry.select_range(0, tk.END)

        self._add_search_options(self.find_window)

        btn_frame = tk.Frame(self.find_window, bg=self.bg_color)
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text=t("dlg_find_next"),
            command=self.find_next,
            bg="#007acc",
            fg="white",
            padx=10,
            pady=5,
            border=0,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text=t("dlg_close"),
            command=self.find_window.destroy,
            bg="#555",
            fg="white",
            padx=10,
            pady=5,
            border=0,
        ).pack(side="left")

        self.find_entry.bind("<Return>", lambda e: self.find_next())
        self.find_entry.bind("<Escape>", lambda e: self.find_window.destroy())

    def show_replace_dialog(self):
        if self._find_dialog_open():
            self.find_window.destroy()

        self.find_window = tk.Toplevel(self.root)
        self.find_window.title(t("dlg_replace"))
        self.find_window.geometry("540x280")
        self.find_window.configure(bg=self.bg_color)
        self.find_window.transient(self.root)

        tk.Label(
            self.find_window, text=t("dlg_find_label"), bg=self.bg_color, fg=self.fg_color
        ).pack(pady=5)
        self.find_entry = tk.Entry(
            self.find_window,
            width=60,
            bg=self.line_num_bg,
            fg=self.fg_color,
            insertbackground=self.cursor_color,
        )
        self.find_entry.pack(pady=5, padx=10)
        self.find_entry.insert(0, self.last_search)
        self.find_entry.focus()

        tk.Label(
            self.find_window, text=t("dlg_replace_label"), bg=self.bg_color, fg=self.fg_color
        ).pack(pady=5)
        replace_entry = tk.Entry(
            self.find_window,
            width=60,
            bg=self.line_num_bg,
            fg=self.fg_color,
            insertbackground=self.cursor_color,
        )
        replace_entry.pack(pady=5, padx=10)

        self._add_search_options(self.find_window)

        btn_frame = tk.Frame(self.find_window, bg=self.bg_color)
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text=t("dlg_replace_one"),
            command=lambda: self.replace_one(self.find_entry.get(), replace_entry.get()),
            bg="#007acc",
            fg="white",
            padx=10,
            pady=5,
            border=0,
        ).pack(side="left", padx=3)
        tk.Button(
            btn_frame,
            text=t("dlg_replace_all"),
            command=lambda: self.replace_all(self.find_entry.get(), replace_entry.get()),
            bg="#0e639c",
            fg="white",
            padx=10,
            pady=5,
            border=0,
        ).pack(side="left", padx=3)
        tk.Button(
            btn_frame,
            text=t("dlg_close"),
            command=self.find_window.destroy,
            bg="#555",
            fg="white",
            padx=10,
            pady=5,
            border=0,
        ).pack(side="left", padx=3)

    def _sync_search_options(self):
        try:
            if self.regex_var is not None:
                self.use_regex = bool(self.regex_var.get())
            if self.case_var is not None:
                self.ignore_case = not bool(self.case_var.get())
            if self.word_var is not None:
                self.whole_word = bool(self.word_var.get())
        except tk.TclError:
            pass

    def _add_search_options(self, parent):
        self.regex_var = tk.BooleanVar(value=self.use_regex)
        self.case_var = tk.BooleanVar(value=not self.ignore_case)
        self.word_var = tk.BooleanVar(value=self.whole_word)
        row = tk.Frame(parent, bg=self.bg_color)
        row.pack(pady=4)
        for var, key in (
            (self.regex_var, "dlg_regex"),
            (self.case_var, "dlg_match_case"),
            (self.word_var, "dlg_whole_word"),
        ):
            tk.Checkbutton(
                row,
                text=t(key),
                variable=var,
                bg=self.bg_color,
                fg=self.fg_color,
                selectcolor=self.line_num_bg,
            ).pack(side="left", padx=6)

    def _search_spec(self, pattern):
        self._sync_search_options()
        try:
            return SearchPattern(
                pattern,
                self.use_regex,
                ignore_case=self.ignore_case,
                whole_word=self.whole_word,
            )
        except ValueError as err:
            self.status_var.set(t("regex_error", err=err))
            messagebox.showerror(t("error"), t("regex_error", err=err))
            return None

    def _select_span(self, text_widget, content, abs_start, abs_end):
        pos = offset_to_tk_index(content, abs_start)
        end_pos = offset_to_tk_index(content, abs_end)
        text_widget.tag_remove("sel", "1.0", tk.END)
        text_widget.tag_add("sel", pos, end_pos)
        text_widget.mark_set(tk.INSERT, end_pos)
        text_widget.see(pos)
        return pos

    def find_next(self):
        tab = self.get_current_tab()
        if not tab:
            return

        pattern = self._current_find_pattern()
        if not pattern:
            return

        spec = self._search_spec(pattern)
        if spec is None:
            return

        self.last_search = pattern
        text_widget = tab.text_area
        content = text_widget.get("1.0", "end-1c")
        start_pos = text_widget.index(tk.INSERT)
        try:
            sel_end = text_widget.index(tk.SEL_LAST)
            if sel_end:
                start_pos = sel_end
        except tk.TclError:
            pass
        start = tk_index_to_offset(content, start_pos)

        window, offset, limited = search_window(content, start, spec.use_regex)
        match = spec.find(window)
        wrapped = False
        if match is None and start > 0:
            window, offset, limited = search_window(content, 0, spec.use_regex)
            match = spec.find(window)
            wrapped = match is not None

        if match is None:
            self.status_var.set(t("not_found", pattern=pattern))
            messagebox.showinfo(t("dlg_find"), t("not_found", pattern=pattern))
            return

        pos = self._select_span(text_widget, content, offset + match.start(), offset + match.end())
        if wrapped:
            msg = t("search_wrapped")
        else:
            msg = t("found_line", line=pos.split(".")[0])
        if limited:
            msg = "%s | %s" % (msg, t("search_limited"))
        self.status_var.set(msg)

    def replace_one(self, find_text, replace_text):
        tab = self.get_current_tab()
        if not tab or not find_text:
            return

        spec = self._search_spec(find_text)
        if spec is None:
            return

        self.last_search = find_text
        text_widget = tab.text_area
        try:
            sel_start = text_widget.index(tk.SEL_FIRST)
            sel_end = text_widget.index(tk.SEL_LAST)
            selected = text_widget.get(sel_start, sel_end)
            new_text, n = spec.replace_in(selected, replace_text, count=1)
            if n:
                text_widget.delete(sel_start, sel_end)
                text_widget.insert(sel_start, new_text)
                self.status_var.set(t("replaced_one"))
                self.find_next()
                return
        except tk.TclError:
            pass

        self.find_next()

    def replace_all(self, find_text, replace_text):
        tab = self.get_current_tab()
        if not tab or not find_text:
            return

        spec = self._search_spec(find_text)
        if spec is None:
            return

        self.last_search = find_text
        text_widget = tab.text_area
        content = text_widget.get("1.0", "end-1c")
        limited = spec.use_regex and len(content) > MAX_REGEX_CHARS
        if limited:
            head, tail = content[:MAX_REGEX_CHARS], content[MAX_REGEX_CHARS:]
            new_head, count = spec.replace_in(head, replace_text)
            new_content = new_head + tail
        else:
            new_content, count = spec.replace_in(content, replace_text)
        if count == 0:
            messagebox.showinfo(t("dlg_replace_all"), t("not_found", pattern=find_text))
            return

        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", new_content)
        tab.update_syntax_highlighting(force=True)
        status = t("replaced_n", n=count)
        if limited:
            status = "%s | %s" % (status, t("search_limited"))
        self.status_var.set(status)
        messagebox.showinfo(t("dlg_replace_all"), status)

    # ==========================================
    # MISC
    # ==========================================
    def goto_line_dialog(self):
        tab = self.get_current_tab()
        if not tab:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(t("dlg_goto"))
        dialog.geometry("320x120")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.root)

        tk.Label(dialog, text=t("dlg_line_number"), bg=self.bg_color, fg=self.fg_color).pack(
            pady=10
        )
        line_entry = tk.Entry(
            dialog,
            width=20,
            bg=self.line_num_bg,
            fg=self.fg_color,
            insertbackground=self.cursor_color,
        )
        line_entry.pack(pady=5)
        line_entry.focus()

        def go():
            try:
                line = int(line_entry.get())
            except ValueError:
                messagebox.showerror(t("error"), t("invalid_line"))
                return
            total = int(tab.text_area.index("end-1c").split(".")[0])
            if line < 1 or line > total:
                messagebox.showerror(t("error"), t("invalid_line"))
                return
            tab.text_area.mark_set(tk.INSERT, f"{line}.0")
            tab.text_area.see(f"{line}.0")
            self.update_cursor_position()
            dialog.destroy()

        line_entry.bind("<Return>", lambda e: go())

        btn_frame = tk.Frame(dialog, bg=self.bg_color)
        btn_frame.pack(pady=10)
        tk.Button(
            btn_frame,
            text=t("dlg_go"),
            command=go,
            bg="#007acc",
            fg="white",
            padx=15,
            pady=5,
            border=0,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text=t("dlg_cancel"),
            command=dialog.destroy,
            bg="#555",
            fg="white",
            padx=15,
            pady=5,
            border=0,
        ).pack(side="left")

    def undo(self):
        tab = self.get_current_tab()
        if tab:
            try:
                tab.text_area.edit_undo()
            except tk.TclError:
                pass

    def redo(self):
        tab = self.get_current_tab()
        if tab:
            try:
                tab.text_area.edit_redo()
            except tk.TclError:
                pass

    def update_cursor_position(self):
        tab = self.get_current_tab()
        if not tab:
            return
        try:
            row, col = tab.text_area.index(tk.INSERT).split(".")
            total_lines = tab.text_area.index("end-1c").split(".")[0]
            self.status_var.set(
                t(
                    "status_cursor",
                    row=row,
                    total=total_lines,
                    col=int(col) + 1,
                    encoding=tab.file_encoding,
                    name=tab.get_short_name(),
                )
            )
        except Exception:
            pass

    def toggle_autosave(self):
        self.autosave_enabled = self.autosave_var.get()
        save_config({"autosave": self.autosave_enabled})

    def cycle_tab(self, delta):
        n = len(self._tabs)
        if n < 2:
            return
        try:
            current = self.notebook.index(self.notebook.select())
        except tk.TclError:
            return
        self.notebook.select((current + delta) % n)

    def toggle_comment_current(self):
        tab = self.get_current_tab()
        if tab:
            tab.toggle_comment()

    def insert_snippet_current(self, key):
        tab = self.get_current_tab()
        if tab:
            tab.insert_snippet(key)

    def autocomplete_current(self):
        tab = self.get_current_tab()
        if tab:
            tab.autocomplete()

    def show_completions(self, tab, words, prefix):
        self._hide_completions()
        try:
            bbox = tab.text_area.bbox(tk.INSERT)
        except tk.TclError:
            bbox = None
        if not bbox:
            tab.text_area.insert(tk.INSERT, words[0][len(prefix):])
            return
        x, y, _w, h = bbox
        abs_x = tab.text_area.winfo_rootx() + x
        abs_y = tab.text_area.winfo_rooty() + y + h
        win = tk.Toplevel(self.root)
        win.wm_overrideredirect(True)
        win.geometry("+%d+%d" % (abs_x, abs_y))
        listing = tk.Listbox(
            win,
            height=min(8, len(words)),
            bg=self.line_num_bg,
            fg=self.fg_color,
            selectbackground="#007acc",
            font=self.editor_font,
            border=0,
            highlightthickness=1,
        )
        listing.pack()
        for word in words:
            listing.insert(tk.END, word)
        listing.selection_set(0)
        listing.activate(0)

        def apply(event=None):
            sel = listing.curselection()
            if not sel:
                self._hide_completions()
                return
            chosen = listing.get(sel[0])
            tab.text_area.insert(tk.INSERT, chosen[len(prefix):])
            self._hide_completions()
            tab.text_area.focus_set()

        def cancel(event=None):
            self._hide_completions()
            tab.text_area.focus_set()

        listing.bind("<Return>", apply)
        listing.bind("<Tab>", apply)
        listing.bind("<Double-1>", apply)
        listing.bind("<Escape>", cancel)
        listing.bind("<FocusOut>", cancel)
        self._complete_win = win
        listing.focus_set()

    def _hide_completions(self):
        win = self._complete_win
        self._complete_win = None
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass

    def zoom_in(self):
        if self.font_size < 28:
            self.font_size += 1
            self._apply_fonts()

    def zoom_out(self):
        if self.font_size > 8:
            self.font_size -= 1
            self._apply_fonts()

    def zoom_reset(self):
        self.font_size = DEFAULT_FONT_SIZE
        self._apply_fonts()

    def _on_zoom_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        return "break"

    def _apply_fonts(self):
        self.editor_font = (self.mono_font, self.font_size)
        self.tab_pixels = self._measure_tab_pixels()
        for tab in self._tabs:
            tab.apply_font(self.editor_font, self.tab_pixels)
        cons = (self.mono_font, max(9, self.font_size - 1))
        self.console_area.configure(font=cons)
        self.input_entry.configure(font=cons)
        save_config({"font_size": self.font_size})

    def choose_interpreter(self):
        initial = self.python_executable or sys.executable
        path = filedialog.askopenfilename(
            title=t("interpreter_title"),
            initialdir=str(pathlib.Path(initial).parent),
        )
        if not path:
            return
        self.python_executable = path
        save_config({"python_executable": path})
        self.status_var.set(t("interpreter_current", path=path))

    def use_auto_interpreter(self):
        self.python_executable = ""
        save_config({"python_executable": ""})
        tab = self.get_current_tab()
        path = tab.file_path if tab else os.getcwd()
        exe = resolve_python_executable(path)
        self.status_var.set(t("interpreter_current", path=exe))

    def toggle_explorer(self):
        self.show_explorer = bool(self.explorer_var.get())
        save_config({"show_explorer": self.show_explorer})
        panes = self.hpaned.panes()
        shown = str(self.explorer_frame) in [str(p) for p in panes]
        if self.show_explorer and not shown:
            self.hpaned.add(self.explorer_frame, before=self.paned_window, minsize=140, width=220)
        elif not self.show_explorer and shown:
            try:
                self.hpaned.forget(self.explorer_frame)
            except tk.TclError:
                pass

    def _fs_iid(self, path):
        return os.path.abspath(path).replace("\\", "/")

    def _iid_fs(self, iid):
        return os.path.normpath(iid)

    def _set_explorer_root(self, path):
        root = os.path.abspath(path)
        if not os.path.isdir(root):
            return
        self.explorer_root = root
        self._git_map = git_status_map(root)
        for child in self.explorer_tree.get_children(""):
            self.explorer_tree.delete(child)
        iid = self._fs_iid(root)
        try:
            self.explorer_tree.insert(
                "",
                "end",
                iid=iid,
                text=os.path.basename(root) or root,
                open=True,
            )
        except tk.TclError:
            return
        self._explorer_fill(iid, root)

    def _explorer_label(self, name, full):
        mark = getattr(self, "_git_map", {}).get(os.path.normpath(full))
        if mark:
            return "%s  %s" % (name, mark)
        return name

    def _explorer_fill(self, parent_id, abs_path):
        try:
            names = os.listdir(abs_path)
        except OSError:
            return
        names.sort(key=lambda n: (not os.path.isdir(os.path.join(abs_path, n)), n.lower()))
        for name in names:
            if name in EXPLORER_SKIP:
                continue
            full = os.path.join(abs_path, name)
            iid = self._fs_iid(full)
            try:
                self.explorer_tree.insert(
                    parent_id,
                    "end",
                    iid=iid,
                    text=self._explorer_label(name, full),
                    open=False,
                )
            except tk.TclError:
                continue
            if os.path.isdir(full):
                dummy = iid + "/."
                try:
                    self.explorer_tree.insert(iid, "end", iid=dummy, text="")
                except tk.TclError:
                    pass

    def _on_explorer_open(self, event=None):
        sel = self.explorer_tree.focus()
        if not sel:
            return
        path = self._iid_fs(sel)
        if not os.path.isdir(path):
            return
        children = self.explorer_tree.get_children(sel)
        if len(children) == 1 and self.explorer_tree.item(children[0], "text") == "":
            self.explorer_tree.delete(children[0])
            self._explorer_fill(sel, path)

    def _on_explorer_activate(self, event=None):
        sel = self.explorer_tree.focus()
        if not sel:
            return
        path = self._iid_fs(sel)
        if os.path.isfile(path):
            self.open_file(path)
        elif os.path.isdir(path):
            self.explorer_tree.item(sel, open=True)
            self._on_explorer_open()

    def _maybe_reveal_in_explorer(self, file_path):
        if not self.explorer_root:
            parent = str(pathlib.Path(file_path).parent)
            self._set_explorer_root(parent)

    def _watch_files(self):
        if self._reload_open:
            try:
                self.root.after(WATCH_INTERVAL_MS, self._watch_files)
            except tk.TclError:
                return
            return
        for tab in list(self._tabs):
            if not os.path.isfile(tab.file_path):
                continue
            mtime = file_mtime(tab.file_path)
            if mtime is None or tab.disk_mtime is None:
                tab.disk_mtime = mtime
                continue
            if mtime <= tab.disk_mtime + 1e-3:
                continue
            self._reload_open = True
            try:
                self.notebook.select(tab.frame)
                if tab.is_modified:
                    ok = messagebox.askyesno(
                        t("reload_title"),
                        t("reload_modified", name=tab.get_short_name()),
                    )
                else:
                    ok = messagebox.askyesno(
                        t("reload_title"),
                        t("reload_msg", name=tab.get_short_name()),
                    )
                if ok:
                    self._reload_tab(tab)
                else:
                    tab.disk_mtime = mtime
            finally:
                self._reload_open = False
            break
        try:
            self.root.after(WATCH_INTERVAL_MS, self._watch_files)
        except tk.TclError:
            return

    def _reload_tab(self, tab):
        try:
            doc = Document.open(tab.file_path)
        except (OSError, UnicodeError, ValueError) as err:
            messagebox.showerror(t("error"), t("load_error", err=err))
            tab.disk_mtime = file_mtime(tab.file_path)
            return
        was_disabled = str(tab.text_area.cget("state")) == "disabled"
        tab.text_area.config(state="normal")
        tab.doc = doc
        tab.text_area.delete("1.0", tk.END)
        tab.text_area.insert("1.0", doc.text)
        tab.text_area.edit_modified(False)
        tab.is_modified = False
        tab.disk_mtime = file_mtime(tab.file_path)
        tab.invalidate_lexer()
        tab.update_syntax_highlighting(force=True)
        tab.update_line_numbers()
        if was_disabled or doc.readonly:
            tab.text_area.config(state="disabled")
        self.update_tab_title(tab)

    def _save_session(self):
        paths = []
        for tab in self._tabs:
            if os.path.isfile(tab.file_path):
                paths.append(tab.file_path)
        idx = 0
        current = self.get_current_tab()
        if current and current.file_path in paths:
            idx = paths.index(current.file_path)
        save_config({"session_files": paths, "session_index": idx})

    def schedule_autosave(self):
        if self.autosave_enabled:
            for tab in self._tabs:
                if tab.is_modified and not tab.is_readonly:
                    try:
                        write_text_file(
                            str(autosave_path_for(tab.file_path)),
                            tab.text_area.get("1.0", "end-1c"),
                            tab.file_encoding,
                            tab.file_newline,
                        )
                    except UnicodeEncodeError:
                        try:
                            write_text_file(
                                str(autosave_path_for(tab.file_path)),
                                tab.text_area.get("1.0", "end-1c"),
                                "utf-8",
                                tab.file_newline,
                            )
                        except OSError as e:
                            print_status(
                                t("write_error", path=str(autosave_path_for(tab.file_path)), err=e),
                                "error",
                            )
                    except OSError as e:
                        print_status(
                            t("write_error", path=str(autosave_path_for(tab.file_path)), err=e),
                            "error",
                        )
        self.root.after(self.autosave_interval, self.schedule_autosave)

    def load_recent_files(self):
        recent = load_config().get("recent_files", [])
        return recent if isinstance(recent, list) else []

    def save_recent_file(self, filepath):
        recent = self.load_recent_files()
        filepath = str(pathlib.Path(filepath).resolve())
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        save_config({"recent_files": recent[:10]})
        self.rebuild_recent_menu()

    def add_recent_files_menu(self, filemenu):
        self.recent_menu = tk.Menu(filemenu, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        self.rebuild_recent_menu()
        filemenu.add_cascade(label=t("menu_recent"), menu=self.recent_menu)

    def rebuild_recent_menu(self):
        menu = getattr(self, "recent_menu", None)
        if menu is None:
            return
        menu.delete(0, "end")
        added = False
        for fp in self.load_recent_files()[:10]:
            if os.path.exists(fp):
                menu.add_command(
                    label=pathlib.Path(fp).name,
                    command=lambda p=fp: self.open_file(p),
                )
                added = True
        if not added:
            menu.add_command(label=t("menu_recent_empty"), state="disabled")

    def show_help(self):
        help_win = tk.Toplevel(self.root)
        help_win.title(t("help_title"))
        help_win.geometry("520x720")
        help_win.configure(bg=self.bg_color)
        help_win.transient(self.root)

        tk.Label(
            help_win,
            text=t("help_heading", app=APP_NAME),
            font=("Helvetica", 14, "bold"),
            bg=self.bg_color,
            fg="white",
        ).pack(pady=10)

        shortcuts = [
            ("Ctrl + N", t("sc_new")),
            ("Ctrl + O", t("sc_open")),
            ("Ctrl + S", t("sc_save")),
            ("Ctrl + Shift + S", t("sc_save_all")),
            ("Ctrl + W", t("sc_close")),
            ("Click ×", t("sc_close_x")),
            ("F2", t("sc_save_as")),
            ("F5", t("sc_run")),
            ("Ctrl + F", t("sc_find")),
            ("F3", t("sc_find_next")),
            ("Ctrl + H", t("sc_replace")),
            ("Ctrl + G", t("sc_goto")),
            ("Ctrl + Z", t("sc_undo")),
            ("Ctrl + Y", t("sc_redo")),
            ("Ctrl + /", t("sc_comment")),
            ("Ctrl + Space", t("sc_complete")),
            ("Ctrl + Tab", t("sc_next_tab")),
            ("Ctrl + = / - / 0", t("sc_zoom")),
            ("F1", t("sc_help")),
        ]

        frame = tk.Frame(help_win, bg=self.bg_color)
        frame.pack(pady=10, padx=20, fill="both", expand=True)

        for key, desc in shortcuts:
            row = tk.Frame(frame, bg=self.bg_color)
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=key,
                font=("Consolas", 10, "bold"),
                width=20,
                anchor="w",
                bg=self.bg_color,
                fg="#569cd6",
            ).pack(side="left")
            tk.Label(
                row,
                text=desc,
                font=("Helvetica", 10),
                anchor="w",
                bg=self.bg_color,
                fg=self.fg_color,
            ).pack(side="left")

        tk.Button(
            help_win,
            text=t("dlg_close"),
            command=help_win.destroy,
            bg="#007acc",
            fg="white",
            border=0,
            padx=20,
            pady=8,
        ).pack(pady=15)

    def show_about(self):
        messagebox.showinfo(t("about_title"), t("about_body", app=APP_NAME))

    def on_close(self):
        if self.runner.is_busy():
            response = messagebox.askyesno(t("process_alive_title"), t("process_alive_msg"))
            if not response:
                return
            proc = self.runner.request_stop()
            if proc is not None:
                terminate_process_tree(proc)

        modified_tabs = [tab for tab in self._tabs if tab.is_modified]
        if modified_tabs:
            response = messagebox.askyesnocancel(
                t("exit_title"), t("exit_unsaved_n", n=len(modified_tabs))
            )
            if response is None:
                return
            if response:
                self.save_all()
                if any(tab.is_modified for tab in self._tabs):
                    return

        self._save_session()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self):
        self.root.mainloop()


def resolve_language(cli_lang=None):
    if cli_lang:
        return set_lang(cli_lang)
    saved = load_config().get("language")
    if saved:
        return set_lang(saved)
    return set_lang(detect_lang())


def parse_args(argv=None):
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", choices=["en", "pl", "english", "polish", "polski"])
    pre_args, _ = pre.parse_known_args(argv)
    resolve_language(pre_args.lang)

    parser = argparse.ArgumentParser(description=f"{APP_NAME} — {t('arg_desc')}")
    parser.add_argument("files", nargs="*", help=t("arg_files"))
    parser.add_argument("--gui", action="store_true", help=t("arg_gui"))
    parser.add_argument("--tui", action="store_true", help=t("arg_tui"))
    parser.add_argument(
        "--lang",
        choices=["en", "pl", "english", "polish", "polski"],
        help=t("arg_lang"),
    )
    return parser.parse_args(argv)


def launch_tui(files, cli_lang=None):
    if not Application:
        print_status(t("prompt_toolkit_missing"), "error")
        return False
    # TUI always opens in English unless the user passed --lang.
    if not cli_lang:
        set_lang("en")
    file_path = files[0] if files else next_untitled_name([])
    AstraEditTUI(file_path).run()
    return True


def launch_gui(files):
    if not tk:
        return False
    windows_dpi_aware()
    AstraEditGUI(files if files else None).run()
    return True


def main(argv=None):
    args = parse_args(argv)
    if args.lang:
        set_lang(args.lang)
        save_config({"language": get_lang()})
        print(t("cli_lang_saved", lang=get_lang()))

    use_gui = False
    if args.gui:
        use_gui = True
    elif args.tui:
        use_gui = False
    elif (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.name == "nt") and tk:
        use_gui = True

    print_status(t("start_mode", mode=t("mode_gui") if use_gui else t("mode_tui")))
    if not get_lexer_for_filename:
        print_status(t("pygments_missing"), "warn")

    if use_gui:
        if not tk:
            print_status(t("tk_missing"), "warn")
            if not launch_tui(args.files, cli_lang=args.lang):
                sys.exit(1)
            return
        try:
            launch_gui(args.files)
        except Exception as e:
            print_status(t("gui_crash", err=e), "error")
            import traceback

            traceback.print_exc()
            if not launch_tui(args.files, cli_lang=args.lang):
                sys.exit(1)
    else:
        if not launch_tui(args.files, cli_lang=args.lang):
            if tk:
                launch_gui(args.files)
            else:
                sys.exit(1)


if __name__ == "__main__":
    main()
