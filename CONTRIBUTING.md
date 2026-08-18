# Contributing to AstraEdit

Thanks for helping. This repo is a small hybrid editor (Tkinter GUI + prompt_toolkit TUI). Keep changes focused.

**Polski:** krótka wersja na dole.

## How to work

1. Fork [Maciej-EriAmo/Astraedit](https://github.com/Maciej-EriAmo/Astraedit).
2. Create a branch: `git checkout -b fix/describe-the-change`.
3. Use the entry point `python astraedit.py` (not only `Astraedit-4.5.py`).
4. Commit with a message that says *what* and *why*.
5. Open a pull request against `main`.

## What we want

- Bug fixes (especially run/console, tabs, search, encoding)
- UI/UX polish that does not break both modes
- Documentation in **English** (README.md) and **Polish** (README.pl.md)
- Extra languages: add a table in `i18n.py` and a `--lang` choice

## Code notes

- User-visible strings go through `t("key")` in `i18n.py`. Add the key to **both** `en` and `pl`.
- Do not hard-code a fake encoding name (saves must use a real codec such as `utf-8`).
- Tab close-all / close-others must stop if the user cancels the unsaved-changes dialog. Do not recreate a tab inside the loop.
- TUI F5 must use `Application.run_in_terminal(...)`. `suspend_to_background()` / `resume()` are not portable (Windows).
- Empty Enter in the console `>>>` bar should send a newline to a running process.
- Config lives in `~/.astraedit_config.json` (`recent_files`, `language`, `autosave`). Merge updates; do not wipe other keys.

## Docs

- Default GitHub page is English: `README.md`.
- Polish lives in `README.pl.md`. Keep clone URL, file names, and flags in sync.
- Do not point install instructions at old usernames or `astraedit.py` paths that do not exist.

## Tests / smoke

There is no heavy test suite yet. Before a PR:

```bash
python -m py_compile astraedit.py i18n.py Astraedit-4.5.py
python astraedit.py --help
python astraedit.py --lang en --help
```

If you change GUI behavior, click through: new tab, open, save, find, replace, F5 + `input()`, language switch, close-all with Cancel.

## License

By contributing you agree that your work is MIT-licensed, same as the project.

---

## Polski (skrót)

1. Fork → branch → PR do `main`.
2. Nowe napisy tylko przez `i18n.py` (klucz w `en` i `pl`).
3. README.md = angielski, README.pl.md = polski; te same komendy i ścieżki.
4. Nie psuj zamykania kart (Anuluj nie może zapętlić) ani F5 w TUI (`run_in_terminal`).
