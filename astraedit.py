#!/usr/bin/env python3
"""AstraEdit 4.6 — hybrid GUI/TUI editor with an interactive console."""

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
from time import time

from i18n import detect_lang, get_lang, set_lang, t

VERSION = "4.6"
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
    print(f"{symbols.get(kind, '?')} {msg}")


def is_python_source(path):
    return str(path).lower().endswith(PYTHON_SUFFIXES)


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


def popen_script(file_path):
    """Start a Python file. Callers keep the returned Popen, not a shared slot."""
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
    return subprocess.Popen([sys.executable, "-u", str(file_path)], **popen_kw)


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
    except Exception as err:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        print_status(t("write_error", path=path, err=err), "error")
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

    def __init__(self, pattern, use_regex):
        self.pattern = pattern
        self.use_regex = bool(use_regex)
        try:
            if self.use_regex:
                self.compiled = re.compile(pattern, re.IGNORECASE)
            else:
                self.compiled = re.compile(re.escape(pattern), re.IGNORECASE)
        except re.error as err:
            raise ValueError(str(err)) from err

    def find(self, text, start=0):
        return self.compiled.search(text, start)

    def replace_in(self, text, repl, count=0):
        return self.compiled.subn(repl, text, count=count)


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
            completed = subprocess.run(
                [sys.executable, self.file_path],
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
        Application(
            layout=layout,
            key_bindings=self.kb,
            full_screen=True,
            mouse_support=True,
            style=style,
            clipboard=tui_clipboard,
        ).run()


# ==========================================
# PART 2: GUI (Tkinter)
# ==========================================
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
except ImportError:
    tk = None


class EditorTab(DocumentView):
    """GUI view of a Document (widgets only)."""

    def __init__(self, parent, file_path, app):
        self.app = app
        self.doc = Document.blank(file_path)
        self.last_update = 0
        self._ln_count = -1
        self._ln_width = 0

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
            font=("Consolas", 11),
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
            font=("Consolas", 11),
            border=0,
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
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.text_area.bind(seq, lambda e: self.app.root.after_idle(self.update_line_numbers), add="+")

        self.load_file()

    def load_file(self):
        path = self.file_path
        if os.path.exists(path):
            try:
                if is_binary_file(path):
                    messagebox.showerror(t("error"), t("binary_open", path=path))
                    return False

                draft = newer_autosave(path)
                restored = False
                if draft is not None and messagebox.askyesno(
                    t("autosave_title"),
                    t("autosave_restore", name=pathlib.Path(path).name),
                ):
                    self.doc = Document.open(str(draft))
                    self.doc.path = resolve_doc_path(path)
                    self.doc.modified = True
                    restored = True
                else:
                    self.doc = Document.open(path)

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

    def _approx_size(self):
        lines = int(self.text_area.index("end-1c").split(".")[0])
        return lines * 64

    def on_key_release_combined(self, event=None):
        self.update_line_numbers()
        self.app.update_cursor_position()
        self.highlight_matching_bracket()

        now = time()
        _mode, delay = highlight_policy(self._approx_size())
        if now - self.last_update > delay:
            self.update_syntax_highlighting()
            self.last_update = now

    def update_combined(self):
        self.update_line_numbers()
        self.app.update_cursor_position()

    def _after_paste(self):
        self.update_line_numbers()
        self.update_syntax_highlighting()
        self.app.update_cursor_position()

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
        lexer = get_best_lexer(self.file_path) if get_lexer_for_filename else None
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
        nbytes = len(content.encode("utf-8", errors="replace"))
        mode, _delay = highlight_policy(nbytes)
        if mode == "off":
            self._clear_syntax_tags()
            return
        lexer = get_best_lexer(self.file_path)
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

        self.autosave_enabled = bool(load_config().get("autosave", True))
        self.autosave_interval = 30000

        self.find_window = None
        self.find_entry = None
        self.regex_var = None
        self.last_search = ""
        self.use_regex = False

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
            self.new_tab()

        self.schedule_autosave()
        self.root.after(100, self.process_queue)

    def setup_ui(self):
        self.paned_window = tk.PanedWindow(
            self.root, orient=tk.VERTICAL, sashwidth=4, bg="#333333"
        )
        self.paned_window.pack(fill="both", expand=True)

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

        self.notebook = ttk.Notebook(editor_container)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<ButtonPress-1>", self.on_tab_click)

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

    def on_tab_click(self, event):
        try:
            clicked_tab = self.notebook.tk.call(
                self.notebook._w, "identify", "tab", event.x, event.y
            )
            if clicked_tab == "":
                return

            x, y, width, height = self.notebook.bbox(clicked_tab)
            if event.x > x + width - 25:
                tabs = self.notebook.tabs()
                idx = int(clicked_tab)
                tab_frame = self.notebook.nametowidget(tabs[idx])
                for tab in self._tabs:
                    if tab.frame == tab_frame:
                        self.close_tab(tab)
                        break
        except Exception:
            pass

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
        menubar.add_cascade(label=t("menu_edit"), menu=editmenu)

        runmenu = tk.Menu(menubar, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        runmenu.add_command(label=f"▶ {t('menu_run_file')}", command=self.run_current_file)
        runmenu.add_command(label=f"⬛ {t('menu_stop')}", command=self.stop_process)
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
        self.update_cursor_position()
        if not self.get_current_tab():
            self.status_var.set(t("status_ready"))

    def setup_bindings(self):
        self.root.bind("<Control-n>", lambda e: self.new_tab())
        self.root.bind("<Control-o>", lambda e: self.open_file_dialog())
        self.root.bind("<Control-s>", lambda e: self.save_current())
        self.root.bind("<Control-Shift-S>", lambda e: self.save_all())
        self.root.bind("<Control-Shift-s>", lambda e: self.save_all())
        self.root.bind("<Control-w>", lambda e: self.close_current_tab())
        self.root.bind("<F2>", lambda e: self.save_as())
        self.root.bind("<F1>", lambda e: self.show_help())
        self.root.bind("<F5>", lambda e: self.run_current_file())
        self.root.bind("<Control-f>", lambda e: self.show_find_dialog())
        self.root.bind("<Control-h>", lambda e: self.show_replace_dialog())
        self.root.bind("<Control-g>", lambda e: self.goto_line_dialog())
        self.root.bind("<F3>", lambda e: self.find_next())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())

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

        self.console_area.config(state="normal")
        self.console_area.delete("1.0", tk.END)

        self.log_to_console(f"{'=' * 60}\n", "info")
        self.log_to_console(f"  {t('running', name=pathlib.Path(file_path).name)}\n", "info")
        self.log_to_console(f"{'=' * 60}\n\n", "info")

        self.stop_btn.config(state="normal", bg="#ff3333")
        self.input_entry.focus()

        threading.Thread(target=self._run_subprocess, args=(file_path,), daemon=True).start()

    def _run_subprocess(self, file_path):
        proc = None
        try:
            proc = popen_script(file_path)
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

    def save_current(self):
        tab = self.get_current_tab()
        if tab and tab.save():
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
        self.find_window.geometry("500x150")
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

        self.regex_var = tk.BooleanVar(value=self.use_regex)
        tk.Checkbutton(
            self.find_window,
            text=t("dlg_regex"),
            variable=self.regex_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.line_num_bg,
        ).pack(pady=5)

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
        self.find_window.geometry("500x220")
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

        self.regex_var = tk.BooleanVar(value=self.use_regex)
        tk.Checkbutton(
            self.find_window,
            text=t("dlg_regex"),
            variable=self.regex_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.line_num_bg,
        ).pack(pady=5)

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

    def _search_spec(self, pattern):
        if self.regex_var is not None:
            try:
                self.use_regex = bool(self.regex_var.get())
            except tk.TclError:
                pass
        try:
            return SearchPattern(pattern, self.use_regex)
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
                    except Exception as e:
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
        help_win.geometry("520x600")
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

        self.root.quit()

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
    AstraEditGUI(files if files else None).run()
    return True


def main(argv=None):
    args = parse_args(argv)
    if args.lang:
        set_lang(args.lang)
        save_config({"language": get_lang()})

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
