# Changelog

## 4.7 — Python editor, not only a notepad

Includes the 4.6.1 correctness fixes, then the 4.7 editor features from the review roadmap. File layout is still a single `astraedit.py` (plus `i18n.py`).

### 4.6.1 (included)

- Autosave drafts restore when the original path does not exist yet (`untitled.txt` / `notatka.txt`). TUI auto-loads that draft.
- Tab context menu (right-click) targets the tab under the cursor, not the active tab. Middle-click closes that tab.
- Bracket matching after click and paste, not only KeyRelease.
- Ctrl+S on a read-only file explains why and opens Save As.
- Literal find/replace no longer interprets `\1` in the replacement.
- Highlighting is debounced; lexer and size are cached on the tab. Line-count×64 size guess is gone.
- Failed `write_text_file` no longer prints and re-raises (callers show the error). Autosave drafts fall back to UTF-8 if the original codec cannot encode.
- Docs: encoding notes no longer claim a UTF-8-with-replacement path (latin-1 always succeeds).

### 4.7 features

- Auto-indent on Enter (extra level after a `:`) and Tab = 4 spaces. Shift+Tab outdents. Tab on `def` / `class` / `try` / `for` / `ifmain` / `main` expands a snippet.
- Ctrl+/ toggles `# ` comments (GUI selection or TUI current line).
- Project explorer (cwd). Double-click opens a file. `git status --porcelain` marks show next to names when `.git` exists.
- F5 uses `.venv`/`venv` walking up from the file, or Run → Python interpreter. TUI F5 also passes `-u`.
- Disk watcher: prompt to reload when a file changes outside the editor.
- Find/Replace: Match case, Whole word.
- Ctrl+Tab / Ctrl+Shift+Tab cycle tabs. Ctrl+= / − / 0 and Ctrl+wheel zoom. Monospace font is picked from a fallback list. Windows DPI awareness.
- Session restore: last open files (on disk) come back when you start without CLI paths.
- Ctrl+Space completes a prefix from identifiers in the current buffer.
- Compatibility launcher is `Astraedit-4.7.py` (the 4.5 and 4.6 names are gone).

### TUI

- Ctrl+/ comment uses `c-_` (prompt_toolkit has no `c-slash`; that name crashed startup).
- Leaving the editor (`Ctrl+Q`) clears the terminal so the shell prompt is not mixed with the last frame.

Deferred (still not 4.7): embedded terminal, multi-cursor, code folding. 5.0 still holds a real debugger, Git commit/diff, split panes, minimap, plugin API.

## 4.6 — Stability release

Numbering: this is the 4.5.x follow-up. **5.0 stays reserved** for the feature milestone in the README roadmap (autocomplete, Git, debugger).

Data safety and run-process correctness. No new editor features. File layout is unchanged (no modularization).

- `Document` is the source of truth; GUI tab and TUI are `DocumentView`s.
- Shared find/replace (`SearchPattern`); bad regex is reported and the previous search is kept.
- `replace_one` replaces the first match inside the selection (no `fullmatch`).
- Regex on files over 2 MB is windowed; replace-all never truncates the buffer.
- Highlight: full / deferred / visible-window / off by size; debounce scales with size.
- Line-number gutter rebuilds only when the line count or width changes.
- Bracket match uses Pygments tokens and skips strings/comments.
- Autosave draft can be restored (GUI prompt). `.astraedit/` is gitignored.
- Config load/save uses concrete exceptions and atomic write.

- Atomic save: write `.tmp` in the same directory, `flush` + `fsync`, then `os.replace`.
- Strict encoding on save (`errors="strict"`). Failed encode offers UTF-8; the buffer stays dirty.
- TUI keeps the encoding and newline detected on open (same as GUI).
- Line endings `LF` / `CRLF` / `CR` are preserved across open/save.
- Autosave writes `.astraedit/autosave/<name>.autosave` next to the file. Ctrl+S still writes the original.
- Run uses a process state machine (`IDLE` → `STARTING` → `RUNNING` → `STOPPING`). A second F5 cannot start another worker.
- The worker holds a local `Popen`; STOP is terminate, then kill if still alive.
- `<` / `>` are no longer treated as matching brackets.
- Shared `Document` model for path, text, encoding, newline, and readonly.
- Tests cover encodings, atomic write, failed replace, autosave, Save As, and subprocess stdout/stderr/stdin/stop/F5-race.

## 4.5.4 — Thesis-review correctness

- Opening a file no longer marks the tab dirty (`<<Modified>>` after insert).
- New tab / TUI default buffer will not silently open an existing `untitled.txt` / `notatka.txt`.
- Encoding order: ISO-8859-2 before Latin-1 (Latin-1 never fails).
- GUI wrap is off; horizontal scrollbar added so line numbers match.
- TUI run uses `subprocess.run` (real exit code, no shell). Errors go to the status bar, not a hidden stdout.
- Console reader flushes short chunks so `input()` prompts appear.
- Replace-one regex uses `fullmatch`. Go-to-line rejects out-of-range numbers.
- Quit-after-save-all aborts if a save still failed.
- No Pygments warning on `import`. `tests/test_core.py` covers i18n, encodings, untitled names.

## 4.5.3 — TUI starts in English

- TUI opens in English (locale / saved language do not apply). `--lang pl` still forces Polish.
- Status bar: `F8:EN/PL` toggles the interface.

## 4.5.2 — Make advertised behavior real

- Auto-save timer always runs; the View checkbox actually turns saving back on.
- Recent-files menu refreshes after each open (not only after a language change).
- F5 runs `.py` / `.pyw` only; other files stay in the editor with a clear message.
- STOP kills the child process tree (`taskkill /T` on Windows, process group elsewhere).
- TUI will not Save over a binary path (use Save As).
- Window icon uses `astraedit.ico` when the file is next to the script.
- Highlighting applies name / operator / punctuation tags, and refreshes after paste.
- Line numbers follow mouse-wheel scroll.
- Docs drop “incremental search” and “IDE” claims that the code did not match.

## 4.5.1 — English UI, docs, and bug fixes

### Language
- Full English / Polish interface (`i18n.py`).
- `--lang en|pl`, View → Language, `ASTRAEDIT_LANG`, and a saved `language` key in `~/.astraedit_config.json`.
- System locale `pl_*` still selects Polish; otherwise English.

### Docs
- README.md rewritten in English (correct clone URL, `astraedit.py`, real `requirements.txt`).
- README.pl.md kept as the Polish guide.
- CONTRIBUTING.md in English (short Polish section).

### Bugs
- **Close all tabs** no longer loops forever (last tab used to spawn a new untitled tab inside the `while` loop; Cancel also re-prompted forever).
- **TUI F5** uses `run_in_terminal` instead of non-portable `suspend_to_background` / missing `resume`.
- Fallback decode no longer stores the invalid encoding name `utf-8 (z błędami)`, which broke later saves.
- Find (F3) no longer touches a destroyed Find dialog widget.
- Console `>>>` can send an empty line (needed for some `input()` prompts).
- Config file is read/written as UTF-8; autosave and language are merged, not overwritten blindly.
- Subprocess I/O uses UTF-8 with replacement (Polish and other non-ASCII output).
- Line-number gutter grows past 4 digits.
- `print_status(..., type=...)` no longer shadows the builtin `type`.

### Layout
- Main program is `astraedit.py`.
- `Astraedit-4.5.py` is a compatibility launcher.
- `requirements.txt` is now in the repo.
