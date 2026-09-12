"""AstraEdit translations (English / Polish).

GUI language resolution:
  1. --lang
  2. saved config (~/.astraedit_config.json → language)
  3. ASTRAEDIT_LANG
  4. system locale (pl_* → Polish, otherwise English)

TUI always starts in English unless --lang is passed. F8 toggles EN/PL.
"""

from __future__ import annotations

import locale
import os
from typing import Any, Dict

SUPPORTED = ("en", "pl")
_ALIASES = {
    "en": "en",
    "english": "en",
    "pl": "pl",
    "polish": "pl",
    "polski": "pl",
}

_STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "untitled_file": "untitled.txt",
        "untitled_n": "untitled_{n}.txt",
        "status_ready": "Ready | F5: Run | F1: Help",
        "status_tui": "F5:Run | F2:Save As | Ctrl+S:Save | Ctrl+Q:Quit | Ctrl+F:Search | F8:EN/PL",
        "ln_col": " Ln {row}, Col {col} | {status} ",
        "status_cursor": "Ln {row}/{total}, Col {col} | {encoding} | {name} | F5: Run | F1: Help",
        "saved": "Saved: {name}",
        "saved_as": "Saved as: {name}",
        "saved_n": "Saved {n} file(s)",
        "found_line": "Found on line {line}",
        "not_found": "Not found: '{pattern}'",
        "search_wrapped": "Search wrapped to the beginning of the document",
        "regex_error": "Regex error: {err}",
        "replaced_one": "Replaced 1 occurrence",
        "replaced_n": "Replaced {n} occurrence(s)",
        "binary_error": "Binary file — cannot open as text",
        "binary_open": "Cannot open binary file:\n{path}\n\nOnly text files are supported.",
        "read_error": "Read error {path}: {err}",
        "write_error": "Write error {path}: {err}",
        "load_error": "Cannot load file:\n{err}",
        "save_error_title": "Save error",
        "encode_retry_utf8": "Cannot save this file as {enc} without losing characters.\nSave as UTF-8 instead? (TUI: press Ctrl+S again)",
        "autosave_title": "Recover draft",
        "autosave_restore": "A newer auto-save draft exists for {name}. Restore it?",
        "autosave_hint": "Newer draft: {name} (open in GUI to restore)",
        "search_limited": "Search limited to 2 MB",
        "readonly_title": "Read-only",
        "readonly_msg": "File opened in read-only mode.\n{path}",
        "readonly_save": "This file is read-only. Use Save As to write a new copy.",
        "reload_title": "File changed",
        "reload_msg": "{name} changed on disk. Reload?",
        "reload_modified": "{name} changed on disk and you have unsaved edits. Reload and lose your changes?",
        "interpreter_title": "Python interpreter",
        "interpreter_current": "Interpreter: {path}",
        "menu_explorer": "Project explorer",
        "menu_interpreter": "Python interpreter…",
        "menu_interpreter_auto": "Use auto-detect interpreter",
        "menu_zoom_in": "Zoom in (Ctrl+=)",
        "menu_zoom_out": "Zoom out (Ctrl+-)",
        "menu_zoom_reset": "Reset zoom (Ctrl+0)",
        "menu_snippets": "Snippets ▸",
        "menu_comment": "Toggle comment (Ctrl+/)",
        "menu_toggle_fold": "Toggle fold (F9)",
        "menu_add_occurrence": "Add next occurrence (Ctrl+D)",
        "dlg_match_case": "Match case",
        "dlg_whole_word": "Whole word",
        "explorer_title": "Explorer",
        "snippet_def": "def function",
        "snippet_class": "class",
        "snippet_ifmain": "if __name__ == '__main__'",
        "snippet_try": "try / except",
        "snippet_for": "for loop",
        "snippet_main": "main() skeleton",
        "running_with": "Running: {name}  ({python})",
        "sc_comment": "Toggle comment",
        "sc_fold": "Fold / unfold block (or click the gutter)",
        "sc_multi_cursor": "Select word, then add next occurrence; type to edit all at once (Esc to exit)",
        "sc_zoom": "Zoom in / out / reset",
        "sc_next_tab": "Next / previous tab",
        "sc_complete": "Complete word from buffer",
        "error": "Error",
        "info": "Info",
        "run_only_python": "F5 runs Python files only (.py, .pyw). Other files stay in the editor.",
        "binary_save_blocked": "This path is a binary file. Use Save As to write a new text file.",
        "process_running": "A process is already running. Use STOP to terminate it.",
        "running": "Running: {name}",
        "finished": "Finished (exit code: {code})",
        "press_enter": "Press Enter to return to the editor...",
        "run_error": "Failed to start: {err}",
        "stdin_error": "Failed to write to stdin: {err}",
        "process_not_running": "No process is running.",
        "process_stopped": "Process stopped by user.",
        "unsaved_title": "Unsaved changes",
        "unsaved_file": "Save changes to {name}?",
        "exit_title": "Quit",
        "exit_save": "Save changes?",
        "exit_unsaved_n": "You have {n} unsaved file(s). Save all?",
        "process_alive_title": "Process is running",
        "process_alive_msg": "A process is still running. Stop it and quit?",
        "invalid_line": "Enter a valid line number",
        "pygments_missing": "Pygments is not installed. Syntax highlighting disabled.",
        "prompt_toolkit_missing": "The 'prompt_toolkit' library is missing.",
        "tk_missing": "Tkinter is unavailable. Falling back to TUI...",
        "gui_crash": "GUI failed: {err}. Falling back to TUI...",
        "start_mode": "Starting in mode: {mode}",
        "mode_gui": "GUI (Tkinter)",
        "mode_tui": "TUI (terminal)",
        "console_title": "Interactive Console",
        "btn_clear": "Clear",
        "btn_stop": "STOP",
        "tab_close": "Close tab",
        "tab_close_others": "Close others",
        "tab_close_all": "Close all",
        "menu_file": "File",
        "menu_new": "New tab (Ctrl+N)",
        "menu_open": "Open... (Ctrl+O)",
        "menu_save": "Save (Ctrl+S)",
        "menu_save_as": "Save As... (F2)",
        "menu_save_all": "Save All (Ctrl+Shift+S)",
        "menu_recent": "Recent files ▸",
        "menu_recent_empty": "(empty)",
        "menu_close_tab": "Close tab (Ctrl+W)",
        "menu_quit": "Quit",
        "menu_edit": "Edit",
        "menu_undo": "Undo (Ctrl+Z)",
        "menu_redo": "Redo (Ctrl+Y)",
        "menu_find": "Find... (Ctrl+F)",
        "menu_replace": "Find and Replace... (Ctrl+H)",
        "menu_goto": "Go to Line... (Ctrl+G)",
        "menu_run": "Run",
        "menu_run_file": "Run Python file (F5)",
        "menu_stop": "Stop process",
        "menu_clear": "Clear console",
        "menu_view": "View",
        "menu_autosave": "Auto-save draft (30s)",
        "menu_language": "Language",
        "menu_lang_en": "English",
        "menu_lang_pl": "Polski",
        "menu_help": "Help",
        "menu_shortcuts": "Keyboard shortcuts (F1)",
        "menu_about": "About",
        "dlg_open": "Open files",
        "dlg_find": "Find",
        "dlg_replace": "Find and Replace",
        "dlg_search": "Search:",
        "dlg_find_label": "Find:",
        "dlg_replace_label": "Replace with:",
        "dlg_regex": "Use regular expressions",
        "dlg_find_next": "Find next (F3)",
        "dlg_close": "Close",
        "dlg_replace_one": "Replace",
        "dlg_replace_all": "Replace all",
        "dlg_goto": "Go to Line",
        "dlg_line_number": "Line number:",
        "dlg_go": "Go",
        "dlg_cancel": "Cancel",
        "dlg_ok": "OK",
        "dlg_path": "Path:",
        "dlg_save_as": "Save As",
        "help_title": "Help — Keyboard shortcuts",
        "help_heading": "{app} — Shortcuts",
        "sc_new": "New tab",
        "sc_open": "Open file",
        "sc_save": "Save current tab",
        "sc_save_all": "Save all tabs",
        "sc_close": "Close tab",
        "sc_close_x": "Close tab (button)",
        "sc_save_as": "Save As...",
        "sc_run": "Run Python file in console",
        "sc_find": "Find (+ Regex option)",
        "sc_find_next": "Find next",
        "sc_replace": "Find and Replace",
        "sc_goto": "Go to Line",
        "sc_undo": "Undo",
        "sc_redo": "Redo",
        "sc_help": "This help window",
        "about_title": "About",
        "about_body": (
            "{app}\n\n"
            "Text editor (GUI + TUI) with a Python run console.\n\n"
            "Features:\n"
            "- Multiple files in the GUI (tabs; click × to close)\n"
            "- Console stdin/stdout/stderr for .py / .pyw (F5)\n"
            "- Syntax highlighting (Pygments, if installed)\n"
            "- Find & Replace with Regex\n"
            "- Bracket matching\n"
            "- Draft auto-save every 30s (does not overwrite the original)\n"
            "- Binary files are not overwritten as text\n"
            "- Project explorer, snippets, venv-aware F5\n"
            "- English / Polish interface\n"
            "- Dark theme\n\n"
            "Author: Maciej Mazur\n"
            "GitHub: @Maciej-EriAmo"
        ),
        "arg_desc": "Text editor with a Python run console",
        "arg_files": "Files to open",
        "arg_gui": "Force GUI mode",
        "arg_tui": "Force terminal (TUI) mode",
        "arg_lang": "Interface language (en or pl)",
        "tui_binary": "# ERROR: Binary files cannot be opened in a text editor\n",
        "cli_lang_saved": "Language set to {lang}",
    },
    "pl": {
        "untitled_file": "notatka.txt",
        "untitled_n": "notatka_{n}.txt",
        "status_ready": "Gotowy | F5: Uruchom | F1: Pomoc",
        "status_tui": "F5:Uruchom | F2:Zapisz jako | Ctrl+S:Zapisz | Ctrl+Q:Wyjdź | Ctrl+F:Szukaj | F8:EN/PL",
        "ln_col": " Ln {row}, Col {col} | {status} ",
        "status_cursor": "Ln {row}/{total}, Col {col} | {encoding} | {name} | F5: Uruchom | F1: Pomoc",
        "saved": "Zapisano: {name}",
        "saved_as": "Zapisano jako: {name}",
        "saved_n": "Zapisano {n} plików",
        "found_line": "Znaleziono w linii {line}",
        "not_found": "Nie znaleziono: '{pattern}'",
        "search_wrapped": "Szukanie od początku dokumentu",
        "regex_error": "Błąd regex: {err}",
        "replaced_one": "Zamieniono 1 wystąpienie",
        "replaced_n": "Zamieniono {n} wystąpień",
        "binary_error": "Plik binarny - nie można otworzyć jako tekst",
        "binary_open": "Nie można otworzyć pliku binarnego:\n{path}\n\nObsługiwane są tylko pliki tekstowe.",
        "read_error": "Błąd odczytu {path}: {err}",
        "write_error": "Błąd zapisu {path}: {err}",
        "load_error": "Nie można wczytać pliku:\n{err}",
        "save_error_title": "Błąd zapisu",
        "encode_retry_utf8": "Nie można zapisać tego pliku jako {enc} bez utraty znaków.\nZapisać jako UTF-8? (TUI: naciśnij Ctrl+S ponownie)",
        "autosave_title": "Odzyskaj szkic",
        "autosave_restore": "Jest nowszy szkic auto-zapisu dla {name}. Przywrócić?",
        "autosave_hint": "Nowszy szkic: {name} (przywróć w GUI)",
        "search_limited": "Szukanie ograniczone do 2 MB",
        "readonly_title": "Tylko odczyt",
        "readonly_msg": "Plik otwarty w trybie tylko do odczytu.\n{path}",
        "readonly_save": "Plik jest tylko do odczytu. Użyj Zapisz jako, aby zapisać kopię.",
        "reload_title": "Plik się zmienił",
        "reload_msg": "{name} zmienił się na dysku. Wczytać ponownie?",
        "reload_modified": "{name} zmienił się na dysku, a masz niezapisane zmiany. Wczytać ponownie i odrzucić edycje?",
        "interpreter_title": "Interpreter Pythona",
        "interpreter_current": "Interpreter: {path}",
        "menu_explorer": "Eksplorator projektu",
        "menu_interpreter": "Interpreter Pythona…",
        "menu_interpreter_auto": "Automatyczny interpreter",
        "menu_zoom_in": "Powiększ (Ctrl+=)",
        "menu_zoom_out": "Pomniejsz (Ctrl+-)",
        "menu_zoom_reset": "Resetuj powiększenie (Ctrl+0)",
        "menu_snippets": "Snippety ▸",
        "menu_comment": "Komentarz (Ctrl+/)",
        "menu_toggle_fold": "Zwiń/rozwiń blok (F9)",
        "menu_add_occurrence": "Dodaj kolejne wystąpienie (Ctrl+D)",
        "dlg_match_case": "Rozróżniaj wielkość liter",
        "dlg_whole_word": "Całe słowo",
        "explorer_title": "Eksplorator",
        "snippet_def": "def funkcja",
        "snippet_class": "class",
        "snippet_ifmain": "if __name__ == '__main__'",
        "snippet_try": "try / except",
        "snippet_for": "pętla for",
        "snippet_main": "szkielet main()",
        "running_with": "Uruchamianie: {name}  ({python})",
        "sc_comment": "Włącz/wyłącz komentarz",
        "sc_fold": "Zwiń/rozwiń blok (albo klik na numer linii)",
        "sc_multi_cursor": "Zaznacz słowo, dodaj kolejne wystąpienie; pisz, by edytować wszystkie naraz (Esc kończy)",
        "sc_zoom": "Powiększ / pomniejsz / reset",
        "sc_next_tab": "Następna / poprzednia karta",
        "sc_complete": "Uzupełnij słowo z bufora",
        "error": "Błąd",
        "info": "Info",
        "run_only_python": "F5 uruchamia tylko pliki Pythona (.py, .pyw). Inne zostają w edytorze.",
        "binary_save_blocked": "Ta ścieżka to plik binarny. Użyj Zapisz jako, żeby zapisać nowy plik tekstowy.",
        "process_running": "Proces już działa. Użyj przycisku STOP aby go zatrzymać.",
        "running": "Uruchamianie: {name}",
        "finished": "Zakończono (kod wyjścia: {code})",
        "press_enter": "Naciśnij Enter, aby wrócić do edytora...",
        "run_error": "Błąd uruchamiania: {err}",
        "stdin_error": "Błąd zapisu do stdin: {err}",
        "process_not_running": "Proces nie działa.",
        "process_stopped": "Proces zatrzymany przez użytkownika.",
        "unsaved_title": "Niezapisane zmiany",
        "unsaved_file": "Czy zapisać zmiany w {name}?",
        "exit_title": "Wyjście",
        "exit_save": "Zapisać zmiany?",
        "exit_unsaved_n": "Masz {n} niezapisanych plików. Zapisać wszystkie?",
        "process_alive_title": "Proces działa",
        "process_alive_msg": "Proces nadal jest uruchomiony. Zatrzymać go i wyjść?",
        "invalid_line": "Podaj prawidłowy numer linii",
        "pygments_missing": "Brak biblioteki Pygments. Kolorowanie składni wyłączone.",
        "prompt_toolkit_missing": "Brak biblioteki 'prompt_toolkit'.",
        "tk_missing": "Tkinter niedostępny. Przełączanie na TUI...",
        "gui_crash": "Awaria GUI: {err}. Przełączanie na TUI...",
        "start_mode": "Uruchamianie w trybie: {mode}",
        "mode_gui": "GUI (Tkinter)",
        "mode_tui": "TUI (Konsola)",
        "console_title": "Konsola Interaktywna",
        "btn_clear": "Wyczyść",
        "btn_stop": "STOP",
        "tab_close": "Zamknij kartę",
        "tab_close_others": "Zamknij inne",
        "tab_close_all": "Zamknij wszystko",
        "menu_file": "Plik",
        "menu_new": "Nowa karta (Ctrl+N)",
        "menu_open": "Otwórz... (Ctrl+O)",
        "menu_save": "Zapisz (Ctrl+S)",
        "menu_save_as": "Zapisz jako... (F2)",
        "menu_save_all": "Zapisz wszystko (Ctrl+Shift+S)",
        "menu_recent": "Ostatnio otwierane ▸",
        "menu_recent_empty": "(puste)",
        "menu_close_tab": "Zamknij kartę (Ctrl+W)",
        "menu_quit": "Wyjście",
        "menu_edit": "Edycja",
        "menu_undo": "Cofnij (Ctrl+Z)",
        "menu_redo": "Ponów (Ctrl+Y)",
        "menu_find": "Znajdź... (Ctrl+F)",
        "menu_replace": "Znajdź i zamień... (Ctrl+H)",
        "menu_goto": "Przejdź do linii... (Ctrl+G)",
        "menu_run": "Uruchom",
        "menu_run_file": "Uruchom plik Pythona (F5)",
        "menu_stop": "Zatrzymaj proces",
        "menu_clear": "Wyczyść konsolę",
        "menu_view": "Widok",
        "menu_autosave": "Szkic auto-zapisu (30s)",
        "menu_language": "Język",
        "menu_lang_en": "English",
        "menu_lang_pl": "Polski",
        "menu_help": "Pomoc",
        "menu_shortcuts": "Skróty klawiszowe (F1)",
        "menu_about": "O programie",
        "dlg_open": "Otwórz pliki",
        "dlg_find": "Znajdź",
        "dlg_replace": "Znajdź i zamień",
        "dlg_search": "Szukaj:",
        "dlg_find_label": "Znajdź:",
        "dlg_replace_label": "Zamień na:",
        "dlg_regex": "Użyj wyrażeń regularnych",
        "dlg_find_next": "Znajdź następny (F3)",
        "dlg_close": "Zamknij",
        "dlg_replace_one": "Zamień",
        "dlg_replace_all": "Zamień wszystkie",
        "dlg_goto": "Przejdź do linii",
        "dlg_line_number": "Numer linii:",
        "dlg_go": "Przejdź",
        "dlg_cancel": "Anuluj",
        "dlg_ok": "OK",
        "dlg_path": "Ścieżka:",
        "dlg_save_as": "Zapisz jako",
        "help_title": "Pomoc - Skróty klawiszowe",
        "help_heading": "{app} - Skróty",
        "sc_new": "Nowa karta",
        "sc_open": "Otwórz plik",
        "sc_save": "Zapisz bieżącą kartę",
        "sc_save_all": "Zapisz wszystkie karty",
        "sc_close": "Zamknij kartę",
        "sc_close_x": "Zamknij kartę (przycisk)",
        "sc_save_as": "Zapisz jako...",
        "sc_run": "Uruchom plik Pythona w konsoli",
        "sc_find": "Znajdź (+ opcja Regex)",
        "sc_find_next": "Znajdź następny",
        "sc_replace": "Znajdź i zamień",
        "sc_goto": "Przejdź do linii",
        "sc_undo": "Cofnij",
        "sc_redo": "Ponów",
        "sc_help": "To okno pomocy",
        "about_title": "O programie",
        "about_body": (
            "{app}\n\n"
            "Edytor tekstu (GUI + TUI) z konsolą dla Pythona.\n\n"
            "Funkcje:\n"
            "- Wiele plików w GUI (karty; kliknij × żeby zamknąć)\n"
            "- Konsola stdin/stdout/stderr dla .py / .pyw (F5)\n"
            "- Kolorowanie składni (Pygments, jeśli jest)\n"
            "- Znajdź i zamień z regex\n"
            "- Dopasowanie nawiasów\n"
            "- Szkic auto-zapisu co 30 s (nie nadpisuje oryginału)\n"
            "- Pliki binarne nie są nadpisywane jako tekst\n"
            "- Eksplorator projektu, snippety, F5 z venv\n"
            "- Interfejs angielski / polski\n"
            "- Ciemny motyw\n\n"
            "Autor: Maciej Mazur\n"
            "GitHub: @Maciej-EriAmo"
        ),
        "arg_desc": "Edytor tekstu z konsolą dla Pythona",
        "arg_files": "Pliki do otwarcia",
        "arg_gui": "Wymuś tryb GUI",
        "arg_tui": "Wymuś tryb konsolowy (TUI)",
        "arg_lang": "Język interfejsu (en lub pl)",
        "tui_binary": "# BŁĄD: Plik binarny nie może być otwarty w edytorze tekstu\n",
        "cli_lang_saved": "Ustawiono język: {lang}",
    },
}

_lang = "en"


def normalize_lang(value: str | None) -> str | None:
    if not value:
        return None
    code = value.strip().lower().replace("-", "_")
    if code in _ALIASES:
        return _ALIASES[code]
    primary = code.split("_", 1)[0]
    if primary in _ALIASES:
        return _ALIASES[primary]
    if code.startswith("pl"):
        return "pl"
    if code.startswith("en"):
        return "en"
    return None


def detect_lang() -> str:
    env = normalize_lang(os.environ.get("ASTRAEDIT_LANG") or os.environ.get("LANG"))
    if env:
        return env
    try:
        found = normalize_lang(locale.getlocale()[0])
        if found:
            return found
    except Exception:
        pass
    return "en"


def set_lang(lang: str | None) -> str:
    global _lang
    _lang = normalize_lang(lang) or "en"
    return _lang


def get_lang() -> str:
    return _lang


def t(key: str, **kwargs: Any) -> str:
    table = _STRINGS.get(_lang) or _STRINGS["en"]
    text = table.get(key) or _STRINGS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
