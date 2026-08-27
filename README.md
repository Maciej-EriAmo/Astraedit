# AstraEdit 4.7 — text editor + Python console

[![Version](https://img.shields.io/badge/version-4.7-blue)](https://github.com/Maciej-EriAmo/Astraedit)
[![Python](https://img.shields.io/badge/python-3.7+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

**English** | [Polski](README.pl.md)

Hybrid text editor written in Python. It runs as a **GUI** (Tkinter) or a **TUI** (prompt_toolkit). In the GUI you can run the current **Python** file (F5), type into `input()` on the `>>>` bar, and see stdout/stderr live. TUI F5 drops to the terminal for the same `.py` / `.pyw` run.

---

## Features

### Interface
- **Dual mode**: GUI (Tkinter) and TUI (terminal)
- **Tabs (GUI)**: several files at once; the × in the tab title is a click target, not a separate widget. Right-click and middle-click apply to that tab. Ctrl+Tab cycles.
- **Project explorer (GUI)**: folder tree of the working directory; Git porcelain marks when `.git` is present
- **Dark theme**: VS Code–style colors
- **Split view (GUI)**: explorer + editor + run console
- **English / Polish**: `--lang en|pl`, View → Language, or `ASTRAEDIT_LANG`
- **Zoom (GUI)**: Ctrl+= / Ctrl+- / Ctrl+0, or Ctrl+mouse wheel

### Editing
- Syntax highlighting when Pygments is installed (full under 500 KB, slower then visible-window, off above 5 MB)
- Line numbers (width grows with the file; follows mouse-wheel scroll). The editor does not word-wrap — long lines scroll horizontally.
- Auto-indent on Enter (extra level after `:`); Tab inserts 4 spaces; Shift+Tab outdents
- Snippets: Tab on `def`, `class`, `try`, `for`, `ifmain`, `main` (or Edit → Snippets)
- Toggle comment (Ctrl+/)
- Word complete from the current buffer (Ctrl+Space)
- Bracket matching (`()` `[]` `{}`; skips strings/comments; `<`/`>` are comparisons)
- Undo / Redo
- Draft auto-save every 30 seconds (`.astraedit/autosave/*.autosave` next to the file; Ctrl+S writes the original). A newer draft is offered even for an unsaved untitled buffer.

### Search
- Find & Replace, including regular expressions
- Find next (F3) — not search-as-you-type
- Case-insensitive by default; optional Match case and Whole word
- Go to line (Ctrl+G)

### Run
- **Python only** (`.py`, `.pyw`). Other files stay in the editor; F5 explains why.
- Interpreter: nearest `.venv`/`venv` walking up from the file, else AstraEdit's Python. Override with Run → Python interpreter
- GUI console: stdin / stdout / stderr; type into `>>>` (empty Enter sends a newline)
- STOP sends terminate, then kills the process tree if it is still alive
- Colored output: green stdin, red stderr, blue status
- F5 saves first, then runs
- Reload prompt when the file changes on disk

### Safety
- Binary-file detection (NUL in the first 1 KB). Those files are not saved back as text.
- Encoding tries, in order: UTF-8, UTF-8-SIG, CP1250, ISO-8859-2, then Latin-1 (Latin-1 accepts every byte, so it has to be last)
- Saves are atomic (temp + fsync + replace) and use strict encoding. A failed encode offers UTF-8; the document stays dirty
- Detected encoding and newline (`LF` / `CRLF` / `CR`) are kept on save in both GUI and TUI
- Read-only mode when the file is not writable
- Prompt before closing unsaved tabs

### Files
- Last 10 recently opened files
- Open several files at once
- Session restore (files that still exist on disk) when started with no paths
- Tab context menu (right-click): close / close others / close all

---

## Requirements

- **Python** 3.7 or newer
- **OS**: Windows, Linux, macOS
- GUI uses Tkinter (usually bundled with Python)
- TUI and highlighting are optional extras

```bash
pip install -r requirements.txt
```

`requirements.txt`:

```
prompt_toolkit>=3.0.0
pygments>=2.10.0
pyperclip>=1.8.2
```

GUI-only (no extras):

```bash
python astraedit.py
```

---

## Install

```bash
git clone https://github.com/Maciej-EriAmo/Astraedit.git
cd Astraedit
pip install -r requirements.txt
```

---

## Usage

```bash
# Default file (untitled / notatka, depending on language)
python astraedit.py

# Open one or more files (each in its own tab)
python astraedit.py main.py utils.py config.json

# Force GUI or TUI
python astraedit.py --gui main.py
python astraedit.py --tui main.py

# Interface language (saved in ~/.astraedit_config.json)
python astraedit.py --lang en
python astraedit.py --lang pl
```

The compatibility launcher `Astraedit-4.7.py` still works; it just calls `astraedit.py`.

Environment override: `ASTRAEDIT_LANG=en` or `ASTRAEDIT_LANG=pl`.

If `--lang` is omitted, AstraEdit uses the saved config, then the environment, then the system locale (`pl_*` → Polish, otherwise English).

### Interactive run

1. Open a `.py` file that calls `input()`.
2. Press **F5** (non-Python files are not executed).
3. Type answers in the `>>>` bar at the bottom of the console.
4. Watch stdout/stderr update live. **STOP** kills the process.

---

## Keyboard shortcuts

### Files and tabs

| Shortcut | Action |
|----------|--------|
| `Ctrl + N` | New tab |
| `Ctrl + O` | Open file(s) |
| `Ctrl + S` | Save current tab |
| `Ctrl + Shift + S` | Save all tabs |
| `Ctrl + W` | Close tab |
| `F2` | Save As… |
| Click `×` | Close that tab |
| Middle-click tab | Close that tab |
| `Ctrl + Tab` / `Ctrl + Shift + Tab` | Next / previous tab |

### Editing

| Shortcut | Action |
|----------|--------|
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |
| `Ctrl + C` / `V` / `X` | Copy / Paste / Cut (system / widget) |
| `Ctrl + A` | Select all |
| `Tab` / `Shift + Tab` | Indent / outdent (or expand a snippet) |
| `Ctrl + /` | Toggle comment |
| `Ctrl + Space` | Complete word from buffer |
| `Ctrl + =` / `-` / `0` | Zoom in / out / reset |

### Search

| Shortcut | Action |
|----------|--------|
| `Ctrl + F` | Find (optional Regex) |
| `F3` | Find next |
| `Ctrl + H` | Find and Replace |
| `Ctrl + G` | Go to line |

### Run

| Shortcut | Action |
|----------|--------|
| `F5` | Run current Python file |
| `STOP` | Kill the process |
| `Clear` | Clear the console |
| `Enter` in `>>>` | Send a line to stdin (empty line is allowed) |

### Help

| Shortcut | Action |
|----------|--------|
| `F1` | Shortcuts window |

TUI extras: starts in **English**. `Ctrl + Q` quit (then clears the terminal), `Ctrl + S` save, `F2` save as, `Ctrl + F` search, `F5` run (drops to the terminal, then returns), `Ctrl + /` toggle comment, `Tab` indent or snippet, `F8` switch EN/PL. Override with `--lang pl`.

---

## Modes

### GUI (Tkinter)

Starts automatically when a display is available (`DISPLAY` / `WAYLAND_DISPLAY` / Windows). Full tabs, console, menus, and language switch.

### TUI (terminal)

```bash
python astraedit.py --tui file.py
```

Useful over SSH or on a machine without a GUI. F5 drops to the terminal, runs the file, then returns after Enter. Quit clears the screen.

---

## Language

| How | Example |
|-----|---------|
| CLI | `python astraedit.py --lang en` |
| Menu | View → Language → English / Polski |
| Environment | `set ASTRAEDIT_LANG=en` (Windows) / `export ASTRAEDIT_LANG=en` |
| Config | `language` in `~/.astraedit_config.json` |

The same keys live in `i18n.py` (`en` and `pl`). Adding another language means a new table plus a `--lang` choice.

---

## Config

Path: `~/.astraedit_config.json`

```json
{
  "recent_files": ["C:/proj/main.py"],
  "language": "en",
  "autosave": true,
  "font_size": 11,
  "tab_size": 4,
  "use_spaces": true,
  "python_executable": "",
  "show_explorer": true,
  "session_files": ["C:/proj/main.py"],
  "session_index": 0
}
```

---

## Troubleshooting

**No syntax highlighting**

```bash
pip install pygments
```

**TUI clipboard does not use the system clipboard**

```bash
pip install pyperclip
```

**`prompt_toolkit` missing** (TUI)

```bash
pip install prompt_toolkit
```

**File will not open**

- Binary files are rejected (NUL byte in the first 1 KB) and cannot be overwritten via Save.
- Check permissions.
- Tried encodings: UTF-8, UTF-8-SIG, CP1250, ISO-8859-2, then Latin-1. Latin-1 accepts every byte, so a decode always succeeds; there is no UTF-8-with-replacement fallback.

**Console shows no output**

- Use `print()` (and `python -u` is already passed for `.py` files).
- Check the status line / STOP state.
- Programs that need a real TTY should be run from TUI mode (F5).

**Process will not die**

- Click **STOP**.
- Closing AstraEdit also kills the child process.

---

## Roadmap

### 5.0
- Smarter autocomplete (not only buffer words)
- Git commit / diff (explorer already shows porcelain marks)
- Debugger
- Split panes
- Minimap
- Plugin API

### 4.8
- Embedded terminal (not only the run console)
- Multi-cursor
- Code folding

### 4.7
Shipped: project explorer, snippets, venv-aware F5, auto-indent, comments, session restore, find options, zoom. See [CHANGELOG.md](CHANGELOG.md).

### 4.6
Shipped: atomic save, process state machine, `Document` model, safer search, scaled highlighting.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug fixes, docs, and extra languages are especially welcome.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2025-2026 Maciej Mazur.

---

## Author

**Maciej Mazur**
- GitHub: [@Maciej-EriAmo](https://github.com/Maciej-EriAmo)
- Medium: [@drwisz](https://medium.com/@drwisz)

---

## Thanks

- [Pygments](https://pygments.org/) — highlighting
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) — TUI
- The Python community

---

## Screenshot (layout)

```
┌─────────────────────────────────────────────────────────────┐
│  AstraEdit 4.7 [GUI] – main.py                              │
├─────────────────────────────────────────────────────────────┤
│ File  Edit  Run  View  Help                                 │
├─────────────────────────────────────────────────────────────┤
│ main.py  ×  │  utils.py  ×  │  config.json  ×               │
├────┬────────────────────────────────────────────────────────┤
│  1 │ def hello_world():                                     │
│  2 │     name = input("Name: ")                             │
│  3 │     print(f"Hello, {name}!")                           │
│  4 │                                                        │
│  5 │ if __name__ == "__main__":                             │
│  6 │     hello_world()                                      │
├────┴────────────────────────────────────────────────────────┤
│ Interactive Console                    Clear    STOP        │
├─────────────────────────────────────────────────────────────┤
│   Running: main.py                                          │
│ Name: Ada                                                   │
│ Hello, Ada!                                                 │
│ >>> _                                                       │
├─────────────────────────────────────────────────────────────┤
│ Ln 3/6, Col 15 | utf-8 | main.py | F5: Run | F1: Help       │
└─────────────────────────────────────────────────────────────┘
```

If AstraEdit helps you, a star on GitHub is appreciated.

*Code is poetry, and every editor is a canvas.*
