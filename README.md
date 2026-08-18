# AstraEdit 4.5 — text editor + Python console

[![Version](https://img.shields.io/badge/version-4.5-blue)](https://github.com/Maciej-EriAmo/Astraedit)
[![Python](https://img.shields.io/badge/python-3.7+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

**English** | [Polski](README.pl.md)

Hybrid text editor written in Python. It runs as a **GUI** (Tkinter) or a **TUI** (prompt_toolkit). In the GUI you can run the current **Python** file (F5), type into `input()` on the `>>>` bar, and see stdout/stderr live. TUI F5 drops to the terminal for the same `.py` / `.pyw` run.

---

## Features

### Interface
- **Dual mode**: GUI (Tkinter) and TUI (terminal)
- **Tabs (GUI)**: several files at once; the × in the tab title is a click target, not a separate widget
- **Dark theme**: VS Code–style colors
- **Split view (GUI)**: editor + run console
- **English / Polish**: `--lang en|pl`, View → Language, or `ASTRAEDIT_LANG`

### Editing
- Syntax highlighting when Pygments is installed (keywords, comments, strings, numbers, names, operators)
- Line numbers (width grows with the file; follows mouse-wheel scroll). The editor does not word-wrap — long lines scroll horizontally.
- Bracket matching (`()` `[]` `{}` `<>`, 2000-character search cap)
- Undo / Redo
- Auto-save every 30 seconds when the View checkbox is on (skips read-only files)

### Search
- Find & Replace, including regular expressions
- Find next (F3) — not search-as-you-type
- Case-insensitive by default
- Go to line (Ctrl+G)

### Run
- **Python only** (`.py`, `.pyw`). Other files stay in the editor; F5 explains why.
- GUI console: stdin / stdout / stderr; type into `>>>` (empty Enter sends a newline)
- STOP kills the child process tree (`taskkill /T` on Windows)
- Colored output: green stdin, red stderr, blue status
- F5 saves first, then runs

### Safety
- Binary-file detection (NUL in the first 1 KB). Those files are not saved back as text.
- Encoding tries, in order: UTF-8, UTF-8-SIG, CP1250, ISO-8859-2, then Latin-1 (Latin-1 accepts every byte, so it has to be last)
- Read-only mode when the file is not writable
- Prompt before closing unsaved tabs

### Files
- Last 10 recently opened files
- Open several files at once
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

The old launcher `Astraedit-4.5.py` still works; it just calls `astraedit.py`.

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

### Editing

| Shortcut | Action |
|----------|--------|
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |
| `Ctrl + C` / `V` / `X` | Copy / Paste / Cut (system / widget) |
| `Ctrl + A` | Select all |

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

TUI extras: starts in **English**. `Ctrl + Q` quit, `Ctrl + S` save, `F2` save as, `Ctrl + F` search, `F5` run (drops to the terminal, then returns), `F8` switch EN/PL. Override with `--lang pl`.

---

## Modes

### GUI (Tkinter)

Starts automatically when a display is available (`DISPLAY` / `WAYLAND_DISPLAY` / Windows). Full tabs, console, menus, and language switch.

### TUI (terminal)

```bash
python astraedit.py --tui file.py
```

Useful over SSH or on a machine without a GUI. F5 drops to the terminal, runs the file, then returns after Enter.

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
  "autosave": true
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
- Tried encodings: UTF-8, CP1250, ISO-8859-2, then Latin-1. Unknown bytes fall back to UTF-8 with replacement.

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
- Autocomplete
- Git status / commit / diff
- Debugger
- Split panes
- Minimap
- Plugin API

### 4.6
- Project explorer
- Embedded terminal (not only the run console)
- Snippets
- Multi-cursor
- Code folding

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug fixes, docs, and extra languages are especially welcome.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2025 Maciej Mazur.

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
│  AstraEdit 4.5 [GUI] – main.py                              │
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
