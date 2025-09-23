from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, Window, FloatContainer, Float
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea, Frame, Dialog, Button, RadioList, Label
from prompt_toolkit.lexers import PygmentsLexer
from pygments.lexers import PythonLexer, JsonLexer, TextLexer
try:
    from pygments.lexers.html import HtmlLexer
except:
    from pygments.lexers import HtmlLexer
from prompt_toolkit.shortcuts.dialogs import yes_no_dialog

import sys
import os
import pathlib
import asyncio

# ---- Schowek ----
try:
    import pyperclip
    from prompt_toolkit.clipboard import Clipboard, ClipboardData

    class SystemClipboard(Clipboard):
        def set_data(self, data: ClipboardData) -> None:
            pyperclip.copy(data.text)

        def get_data(self) -> ClipboardData:
            return ClipboardData(pyperclip.paste())

    clipboard = SystemClipboard()
except Exception:
    from prompt_toolkit.clipboard import InMemoryClipboard
    clipboard = InMemoryClipboard()

# ---- Funkcje ----
def get_lexer_for_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        return PygmentsLexer(PythonLexer)
    elif ext == ".json":
        return PygmentsLexer(JsonLexer)
    elif ext in (".html", ".htm"):
        return PygmentsLexer(HtmlLexer)
    else:
        return PygmentsLexer(TextLexer)

def read_text_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def write_text_file(path, text):
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)

def get_file_list(folder):
    folder = pathlib.Path(folder).resolve()
    try:
        files = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        file_list = [(str(f), f.name + ("/" if f.is_dir() else "")) for f in files]
        root = pathlib.Path(folder.anchor if folder.anchor else "/")
        if folder != root:
            file_list.insert(0, (str(folder.parent), "../"))
        return file_list
    except Exception:
        return []

# ---- Klasa edytora ----
class AstraEdit:
    def __init__(self, file_path="notatka.txt"):
        self.file_path = file_path if os.path.exists(file_path) else "notatka.txt"
        self.is_modified = False
        self.current_folder = pathlib.Path(".").resolve()

        text = read_text_file(self.file_path)
        self.editor = TextArea(
            text=text,
            scrollbar=True,
            line_numbers=True,
            lexer=get_lexer_for_file(self.file_path),
            multiline=True
        )
        self.editor.buffer.on_text_changed += lambda _: self.mark_modified()
        self.frame = Frame(self.editor, title=f"AstraEdit 2.0 – {self.file_path}")

        self.footer_text = "Ctrl+S=Zapisz | F2=Zapisz jako | Ctrl+O=Otwórz | Ctrl+Q=Wyjście | Ctrl+C/V/X/A=Kopiuj/Wklej/Wytnij/Zaznacz"
        self.footer = Window(height=1, content=FormattedTextControl(lambda: [("class:status", self.footer_text)]))

        self.kb = self.create_key_bindings()

    def mark_modified(self):
        self.is_modified = True

    async def update_footer(self, text, app, timeout=2):
        self.footer_text = text
        app.invalidate()
        await asyncio.sleep(timeout)
        self.footer_text = "Ctrl+S=Zapisz | F2=Zapisz jako | Ctrl+O=Otwórz | Ctrl+Q=Wyjście | Ctrl+C/V/X/A=Kopiuj/Wklej/Wytnij/Zaznacz"
        app.invalidate()

    # ---- Dialog „Zapisz jako” ----
    def save_as_dialog(self, app):
        text_area = TextArea(height=1)

        def save_handler():
            path = text_area.text.strip()
            if path:
                try:
                    write_text_file(path, self.editor.text)
                    self.file_path = path
                    self.frame.title = f"AstraEdit 2.0 – {path}"
                    self.editor.lexer = get_lexer_for_file(path)
                    self.is_modified = False
                except Exception as e:
                    app.create_background_task(self.update_footer(f"✖ Błąd zapisu: {e}", app))
            if app.layout.container.floats:
                app.layout.container.floats.pop()
            app.layout.focus(self.editor)

        def cancel_handler():
            if app.layout.container.floats:
                app.layout.container.floats.pop()
            app.layout.focus(self.editor)

        dialog = Dialog(
            title="Zapisz jako",
            body=HSplit([Label(text="Podaj nazwę pliku:"), text_area]),
            buttons=[Button(text="Zapisz", handler=save_handler),
                     Button(text="Anuluj", handler=cancel_handler)],
            width=60, modal=True
        )
        app.layout.container.floats.insert(0, Float(content=dialog))
        app.layout.focus(text_area)

    # ---- Dialog „Otwórz plik” ----
    def open_file_dialog(self, app):
        file_list = get_file_list(self.current_folder)
        if not file_list:
            app.create_background_task(self.update_footer("✖ Brak plików w katalogu", app))
            return

        radio = RadioList(file_list)

        def open_selected():
            selected = radio.current_value
            if selected:
                path = pathlib.Path(selected)
                if path.is_dir():
                    self.current_folder = path
                    radio.values = get_file_list(self.current_folder)
                    app.invalidate()
                    return
                elif path.is_file():
                    self.editor.text = read_text_file(path)
                    self.editor.buffer.cursor_position = len(self.editor.text)
                    self.file_path = str(path)
                    self.frame.title = f"AstraEdit 2.0 – {self.file_path}"
                    self.editor.lexer = get_lexer_for_file(self.file_path)
                    self.is_modified = False
            if app.layout.container.floats:
                app.layout.container.floats.pop()
            app.layout.focus(self.editor)

        def cancel():
            if app.layout.container.floats:
                app.layout.container.floats.pop()
            app.layout.focus(self.editor)

        dialog = Dialog(
            title=f"Przeglądarka plików ({self.current_folder})",
            body=radio,
            buttons=[Button(text="Otwórz", handler=open_selected),
                     Button(text="Anuluj", handler=cancel)],
            width=60, modal=True
        )
        app.layout.container.floats.insert(0, Float(content=dialog))
        app.layout.focus(radio)

    # ---- Skróty klawiszowe ----
    def create_key_bindings(self):
        kb = KeyBindings()

        @kb.add("c-s")
        def _(event):
            try:
                write_text_file(self.file_path, self.editor.text)
                self.is_modified = False
                event.app.create_background_task(self.update_footer(f"✔ Zapisano: {self.file_path}", event.app))
            except Exception as e:
                event.app.create_background_task(self.update_footer(f"✖ Błąd zapisu: {e}", event.app))

        @kb.add("f2")
        def _(event):
            self.save_as_dialog(event.app)

        @kb.add("c-o")
        def _(event):
            self.open_file_dialog(event.app)

        @kb.add("c-q")
        async def _(event):
            if self.is_modified:
                save = await yes_no_dialog(title="Niezapisane zmiany", text="Zapisz przed wyjściem?").run_async()
                if save:
                    write_text_file(self.file_path, self.editor.text)
            event.app.exit()

        @kb.add("c-c")
        def _(event):
            try:
                pyperclip.copy(self.editor.buffer.copy_selection().text)
            except Exception:
                pass

        @kb.add("c-v")
        def _(event):
            try:
                self.editor.buffer.paste_clipboard_data(ClipboardData(pyperclip.paste()))
            except Exception:
                pass

        @kb.add("c-x")
        def _(event):
            try:
                pyperclip.copy(self.editor.buffer.cut_selection().text)
            except Exception:
                pass

        @kb.add("c-a")
        def _(event):
            self.editor.buffer.cursor_position = 0
            self.editor.buffer.start_selection()
            self.editor.buffer.cursor_position = len(self.editor.text)

        return kb

    # ---- Uruchomienie aplikacji ----
    def run(self):
        from prompt_toolkit.styles import Style
        style = Style.from_dict({"status": "reverse"})
        app = Application(
            layout=Layout(FloatContainer(content=HSplit([self.frame, self.footer]), floats=[])),
            key_bindings=self.kb,
            full_screen=True,
            mouse_support=True,
            clipboard=clipboard,
            style=style
        )
        app.run()
        os.system('cls' if os.name == 'nt' else 'clear')

# ---- Start ----
if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "notatka.txt"
    editor_app = AstraEdit(file_path)
    try:
        editor_app.run()
    except KeyboardInterrupt:
        print("\nPrzerwano program (Ctrl+C).")
    finally:
        if editor_app.is_modified:
            try:
                write_text_file(editor_app.file_path, editor_app.editor.text)
                print(f"✔ Zapisano automatycznie: {editor_app.file_path}")
            except Exception as e:
                print(f"✖ Błąd zapisu przy zamykaniu: {e}")
        print("Do widzenia 👋")
        sys.exit(0)
