#!/usr/bin/env python3
"""AstraEdit 4.5 — hybrid GUI/TUI editor with an interactive console."""

import argparse
import json
import os
import pathlib
import queue
import re
import signal
import subprocess
import sys
import threading
from time import time

from i18n import detect_lang, get_lang, set_lang, t

APP_NAME = "AstraEdit 4.5"
CONFIG_FILE = pathlib.Path.home() / ".astraedit_config.json"
PYTHON_SUFFIXES = (".py", ".pyw")
ICON_FILE = pathlib.Path(__file__).resolve().with_name("astraedit.ico")

# ---- Config ----
def load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def save_config(updates):
    data = load_config()
    data.update(updates)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print_status(t("write_error", path=str(CONFIG_FILE), err=e), "error")


# ---- Diagnostics ----
def print_status(msg, kind="info"):
    symbols = {"info": "ℹ", "success": "✔", "error": "✖", "warn": "⚠"}
    print(f"{symbols.get(kind, '?')} {msg}")


def is_python_source(path):
    return str(path).lower().endswith(PYTHON_SUFFIXES)


def terminate_process_tree(proc):
    """Kill the run child and its descendants. Does not touch this editor."""
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
                creationflags=flags,
            )
            return
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


# ---- Shared I/O ----
def is_binary_file(filepath):
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except Exception:
        return False


def read_text_file_smart(path):
    if is_binary_file(path):
        raise ValueError(t("binary_error"))

    encodings = ["utf-8", "utf-8-sig", "cp1250", "latin-1", "iso-8859-2"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # Always return a real codec name so later saves do not fail.
            return f.read(), "utf-8"
    except Exception as e:
        print_status(t("read_error", path=path, err=e), "error")
        return "", "utf-8"


def read_text_file(path):
    content, _ = read_text_file_smart(path)
    return content


def write_text_file(path, text, encoding="utf-8"):
    codec = encoding if encoding and encoding.isascii() and " " not in encoding else "utf-8"
    try:
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=codec, errors="replace") as f:
            f.write(text)
    except Exception as e:
        print_status(t("write_error", path=path, err=e), "error")
        raise


# ---- Pygments ----
try:
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.util import ClassNotFound
except ImportError:
    print_status(t("pygments_missing"), "warn")
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


class AstraEditTUI:
    def __init__(self, file_path):
        self.file_path = str(pathlib.Path(file_path).expanduser().resolve())
        self.is_modified = False
        self.binary_blocked = False

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
                initial_text = read_text_file(self.file_path)

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

        self.status_text = t("status_tui")
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

    def save_current(self):
        if self.binary_blocked:
            print_status(t("binary_save_blocked"), "error")
            return False
        try:
            write_text_file(self.file_path, self.editor.text)
            self.is_modified = False
            self.frame.title = self.get_title()
            return True
        except Exception as e:
            print_status(t("write_error", path=self.file_path, err=e), "error")
            return False

    def goto_line_dialog(self, app):
        tf = TextArea(multiline=False)

        def go():
            try:
                line_num = int(tf.text.strip())
                self.editor.buffer.cursor_position = (
                    self.editor.buffer.document.translate_row_col_to_index(line_num - 1, 0)
                )
                self._pop_float(app)
            except (ValueError, IndexError):
                self.status_text = t("invalid_line")

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
            try:
                write_text_file(path, self.editor.text)
            except Exception:
                return
            self.file_path = str(pathlib.Path(path).expanduser().resolve())
            self.binary_blocked = False
            self.is_modified = False
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
            print_status(t("run_only_python"), "warn")
            return
        if self.binary_blocked:
            print_status(t("binary_save_blocked"), "error")
            return
        if not self.save_current():
            return

        def _run():
            name = pathlib.Path(self.file_path).name
            print(f"\n{'=' * 60}")
            print(f"  {t('running', name=name)}")
            print(f"{'=' * 60}\n")
            exit_code = os.system(f'"{sys.executable}" "{self.file_path}"')
            print(f"\n{'=' * 60}")
            print(f"  {t('finished', code=exit_code)}")
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


class EditorTab:
    """A single editor tab."""

    def __init__(self, parent, file_path, app):
        self.app = app
        self.file_path = str(pathlib.Path(file_path).expanduser().resolve())
        self.is_modified = False
        self.file_encoding = "utf-8"
        self.is_readonly = False
        self.last_update = 0

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

        self.text_area = scrolledtext.ScrolledText(
            container,
            wrap="word",
            undo=True,
            bg=app.bg_color,
            fg=app.fg_color,
            insertbackground=app.cursor_color,
            selectbackground=app.selection_color,
            font=("Consolas", 11),
            border=0,
        )
        self.text_area.pack(side="left", fill="both", expand=True)

        self.text_area.vbar.config(command=self.on_scrollbar)
        self.line_numbers.config(yscrollcommand=self.text_area.vbar.set)

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
        if os.path.exists(self.file_path):
            try:
                if is_binary_file(self.file_path):
                    messagebox.showerror(t("error"), t("binary_open", path=self.file_path))
                    return False

                content, self.file_encoding = read_text_file_smart(self.file_path)
                self.text_area.insert("1.0", content)
                self.update_syntax_highlighting()

                if not os.access(self.file_path, os.W_OK):
                    self.is_readonly = True
                    self.text_area.config(state="disabled")
                    messagebox.showwarning(
                        t("readonly_title"), t("readonly_msg", path=self.file_path)
                    )
            except Exception as e:
                messagebox.showerror(t("error"), t("load_error", err=e))
                return False

        self.update_line_numbers()
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

    def on_key_release_combined(self, event=None):
        self.update_line_numbers()
        self.app.update_cursor_position()
        self.highlight_matching_bracket()

        now = time()
        if now - self.last_update > 0.5:
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
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")

        end_index = self.text_area.index("end-1c")
        line_count = int(end_index.split(".")[0])
        width = max(4, len(str(line_count)))
        self.line_numbers.config(width=width)
        nums = "\n".join(str(i) for i in range(1, line_count + 1))

        self.line_numbers.insert("1.0", nums)
        self.line_numbers.config(state="disabled")

        try:
            first_visible = self.text_area.yview()[0]
            self.line_numbers.yview_moveto(first_visible)
        except Exception:
            pass

    def highlight_matching_bracket(self):
        self.text_area.tag_remove("matching_bracket", "1.0", tk.END)

        cursor_pos = self.text_area.index(tk.INSERT)

        try:
            prev_pos = f"{cursor_pos}-1c"
            char_before = self.text_area.get(prev_pos, cursor_pos)
        except Exception:
            char_before = ""

        try:
            char_at = self.text_area.get(cursor_pos, f"{cursor_pos}+1c")
        except Exception:
            char_at = ""

        brackets = {"(": ")", "[": "]", "{": "}", "<": ">"}
        rev_brackets = {v: k for k, v in brackets.items()}
        max_chars = 2000

        if char_before in rev_brackets:
            self.find_opening_bracket(prev_pos, char_before, rev_brackets[char_before], max_chars)
        elif char_at in brackets:
            self.find_closing_bracket(cursor_pos, char_at, brackets[char_at], max_chars)

    def find_closing_bracket(self, start, open_br, close_br, max_chars):
        count = 1
        pos = start
        chars_searched = 0

        while chars_searched < max_chars:
            chars_searched += 1
            pos = f"{pos}+1c"
            if self.text_area.compare(pos, ">=", tk.END):
                break
            ch = self.text_area.get(pos, f"{pos}+1c")
            if ch == open_br:
                count += 1
            elif ch == close_br:
                count -= 1
                if count == 0:
                    self.text_area.tag_add("matching_bracket", start, f"{start}+1c")
                    self.text_area.tag_add("matching_bracket", pos, f"{pos}+1c")
                    break

    def find_opening_bracket(self, start, close_br, open_br, max_chars):
        count = 1
        pos = start
        chars_searched = 0

        while chars_searched < max_chars:
            chars_searched += 1
            if self.text_area.compare(pos, "<=", "1.0"):
                break
            pos = f"{pos}-1c"
            ch = self.text_area.get(pos, f"{pos}+1c")
            if ch == close_br:
                count += 1
            elif ch == open_br:
                count -= 1
                if count == 0:
                    self.text_area.tag_add("matching_bracket", pos, f"{pos}+1c")
                    self.text_area.tag_add("matching_bracket", start, f"{start}+1c")
                    break

    def update_syntax_highlighting(self):
        if not get_lexer_for_filename:
            return

        content = self.text_area.get("1.0", "end-1c")

        for tag in self.text_area.tag_names():
            if tag not in ("sel", "matching_bracket"):
                self.text_area.tag_remove(tag, "1.0", "end")

        lexer = get_best_lexer(self.file_path)
        if lexer is None:
            return

        try:
            line_idx = 1
            col_idx = 0

            for token, text in lexer.get_tokens(content):
                str_token = str(token)
                tag_name = None

                if "Keyword" in str_token:
                    tag_name = "Keyword"
                elif "Comment" in str_token:
                    tag_name = "Comment"
                elif "String" in str_token:
                    tag_name = "String"
                elif "Number" in str_token:
                    tag_name = "Number"
                elif "Builtin" in str_token:
                    tag_name = "Name.Builtin"
                elif "Operator" in str_token:
                    tag_name = "Operator"
                elif "Punctuation" in str_token:
                    tag_name = "Punctuation"
                elif "Name" in str_token:
                    tag_name = "Name"

                lines = text.split("\n")
                start_idx = f"{line_idx}.{col_idx}"
                if len(lines) > 1:
                    line_idx += len(lines) - 1
                    col_idx = len(lines[-1])
                else:
                    col_idx += len(text)
                end_idx = f"{line_idx}.{col_idx}"

                if tag_name:
                    self.text_area.tag_add(tag_name, start_idx, end_idx)
        except Exception:
            pass

    def save(self):
        if self.is_readonly:
            return False
        try:
            content = self.text_area.get("1.0", "end-1c")
            write_text_file(self.file_path, content, self.file_encoding)
            self.is_modified = False
            self.app.update_tab_title(self)
            return True
        except Exception as e:
            messagebox.showerror(t("save_error_title"), str(e))
            return False

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
        self.process = None
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

        if self.process and self.process.poll() is None:
            messagebox.showinfo(t("info"), t("process_running"))
            return

        if not is_python_source(tab.file_path):
            messagebox.showinfo(t("info"), t("run_only_python"))
            return

        if not tab.save():
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
        try:
            cmd = [sys.executable, "-u", file_path]

            popen_kw = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "stdin": subprocess.PIPE,
                "text": True,
                "bufsize": 1,
                "cwd": str(pathlib.Path(file_path).parent),
                "encoding": "utf-8",
                "errors": "replace",
            }
            if os.name == "nt":
                popen_kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                popen_kw["start_new_session"] = True

            self.process = subprocess.Popen(cmd, **popen_kw)

            threading.Thread(
                target=self._reader, args=(self.process.stdout, None), daemon=True
            ).start()
            threading.Thread(
                target=self._reader, args=(self.process.stderr, "stderr"), daemon=True
            ).start()

            self.process.wait()

            code = self.process.returncode if self.process else "?"
            self.msg_queue.put(("text", f"\n{'=' * 60}\n", "info"))
            self.msg_queue.put(("text", f"  {t('finished', code=code)}\n", "info"))
            self.msg_queue.put(("text", f"{'=' * 60}\n", "info"))
        except Exception as e:
            self.msg_queue.put(("text", f"\n❌ {t('run_error', err=e)}\n", "stderr"))
        finally:
            self.msg_queue.put(("status", "stopped", None))

    def _reader(self, stream, tag):
        try:
            for line in iter(stream.readline, ""):
                if line:
                    self.msg_queue.put(("text", line, tag))
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
                    self.process = None
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

        running = self.process and self.process.poll() is None
        if not running:
            if text:
                self.log_to_console(f"⚠ {t('process_not_running')}\n", "stderr")
            return

        try:
            self.log_to_console(f"{text}\n", "stdin")
            self.process.stdin.write(text + "\n")
            self.process.stdin.flush()
        except Exception as e:
            self.log_to_console(f"❌ {t('stdin_error', err=e)}\n", "stderr")

    def stop_process(self):
        if self.process and self.process.poll() is None:
            terminate_process_tree(self.process)
            self.log_to_console(f"\n⚠ {t('process_stopped')}\n", "stderr")
            self.stop_btn.config(state="disabled", bg="#8b0000")
            self.process = None

    def clear_console(self):
        self.console_area.config(state="normal")
        self.console_area.delete("1.0", tk.END)
        self.console_area.config(state="disabled")

    # ==========================================
    # TABS
    # ==========================================
    def new_tab(self, file_path=None):
        if file_path is None:
            file_path = t("untitled_file")
            counter = 1
            while any(
                tab.file_path == str(pathlib.Path(file_path).resolve()) for tab in self._tabs
            ):
                file_path = t("untitled_n", n=counter)
                counter += 1

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
            tab.file_path = str(pathlib.Path(path).resolve())
            tab.is_readonly = False
            tab.text_area.config(state="normal")
            if tab.save():
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

    def find_next(self):
        tab = self.get_current_tab()
        if not tab:
            return

        pattern = self._current_find_pattern()
        if not pattern:
            return

        self.last_search = pattern
        text_widget = tab.text_area
        start_pos = text_widget.index(tk.INSERT)

        try:
            sel_end = text_widget.index(tk.SEL_LAST)
            if sel_end:
                start_pos = sel_end
        except tk.TclError:
            pass

        pos = None
        end_pos = None

        if self.use_regex:
            try:
                content = text_widget.get(start_pos, tk.END)
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    start_line, start_col = map(int, start_pos.split("."))
                    match_start, match_end = match.start(), match.end()
                    lines_before = content[:match_start].count("\n")
                    if lines_before > 0:
                        last_newline = content[:match_start].rfind("\n")
                        col_offset = match_start - last_newline - 1
                    else:
                        col_offset = match_start + start_col
                    pos = f"{start_line + lines_before}.{col_offset}"
                    end_pos = f"{pos}+{match_end - match_start}c"
                else:
                    content = text_widget.get("1.0", tk.END)
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        self.status_var.set(t("search_wrapped"))
                        match_start, match_end = match.start(), match.end()
                        lines_before = content[:match_start].count("\n")
                        if lines_before > 0:
                            last_newline = content[:match_start].rfind("\n")
                            col_offset = match_start - last_newline - 1
                        else:
                            col_offset = match_start
                        pos = f"{1 + lines_before}.{col_offset}"
                        end_pos = f"{pos}+{match_end - match_start}c"
            except re.error as e:
                self.status_var.set(t("regex_error", err=e))
                messagebox.showerror(t("error"), str(e))
                return
        else:
            pos = text_widget.search(pattern, start_pos, stopindex=tk.END, nocase=True)
            if not pos:
                pos = text_widget.search(pattern, "1.0", stopindex=tk.END, nocase=True)
                if pos:
                    self.status_var.set(t("search_wrapped"))
            if pos:
                end_pos = f"{pos}+{len(pattern)}c"

        if pos:
            text_widget.tag_remove("sel", "1.0", tk.END)
            text_widget.tag_add("sel", pos, end_pos)
            text_widget.mark_set(tk.INSERT, end_pos)
            text_widget.see(pos)
            line = pos.split(".")[0]
            self.status_var.set(t("found_line", line=line))
        else:
            self.status_var.set(t("not_found", pattern=pattern))
            messagebox.showinfo(t("dlg_find"), t("not_found", pattern=pattern))

    def replace_one(self, find_text, replace_text):
        tab = self.get_current_tab()
        if not tab or not find_text:
            return

        text_widget = tab.text_area
        if self.regex_var is not None:
            try:
                self.use_regex = bool(self.regex_var.get())
            except tk.TclError:
                pass

        try:
            sel_start = text_widget.index(tk.SEL_FIRST)
            sel_end = text_widget.index(tk.SEL_LAST)
            selected = text_widget.get(sel_start, sel_end)
            should_replace = False
            new_text = replace_text

            if self.use_regex:
                try:
                    if re.match(find_text, selected, re.IGNORECASE):
                        should_replace = True
                        new_text = re.sub(find_text, replace_text, selected, flags=re.IGNORECASE)
                except re.error:
                    pass
            elif selected.lower() == find_text.lower():
                should_replace = True

            if should_replace:
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

        text_widget = tab.text_area
        content = text_widget.get("1.0", "end-1c")
        if self.regex_var is not None:
            try:
                self.use_regex = bool(self.regex_var.get())
            except tk.TclError:
                pass

        try:
            if self.use_regex:
                new_content, count = re.subn(find_text, replace_text, content, flags=re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                new_content, count = pattern.subn(replace_text, content)

            if count == 0:
                messagebox.showinfo(t("dlg_replace_all"), t("not_found", pattern=find_text))
                return

            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", new_content)
            tab.update_syntax_highlighting()
            self.status_var.set(t("replaced_n", n=count))
            messagebox.showinfo(t("dlg_replace_all"), t("replaced_n", n=count))
        except re.error as e:
            messagebox.showerror(t("error"), str(e))

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
                tab.text_area.mark_set(tk.INSERT, f"{line}.0")
                tab.text_area.see(f"{line}.0")
                self.update_cursor_position()
                dialog.destroy()
            except ValueError:
                messagebox.showerror(t("error"), t("invalid_line"))

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
                    tab.save()
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
        if self.process and self.process.poll() is None:
            response = messagebox.askyesno(t("process_alive_title"), t("process_alive_msg"))
            if not response:
                return
            terminate_process_tree(self.process)

        modified_tabs = [tab for tab in self._tabs if tab.is_modified]
        if modified_tabs:
            response = messagebox.askyesnocancel(
                t("exit_title"), t("exit_unsaved_n", n=len(modified_tabs))
            )
            if response is None:
                return
            if response:
                self.save_all()

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
    file_path = files[0] if files else t("untitled_file")
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
