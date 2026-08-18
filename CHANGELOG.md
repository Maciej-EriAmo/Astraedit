# Changelog

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
