# AstraEdit 4.6 — edytor + konsola Pythona

[![Version](https://img.shields.io/badge/version-4.6-blue)](https://github.com/Maciej-EriAmo/Astraedit)
[![Python](https://img.shields.io/badge/python-3.7+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

[English](README.md) | **Polski**

Hybrydowy edytor tekstu w Pythonie. Działa jako **GUI** (Tkinter) albo **TUI** (prompt_toolkit). W GUI **F5 uruchamia tylko pliki Pythona** (`.py` / `.pyw`): `input()` z paska `>>>`, stdout/stderr na żywo. W TUI F5 schodzi do terminala dla tego samego uruchomienia.

---

## Funkcje

### Interfejs
- **Dwa tryby**: GUI (Tkinter) i TUI (terminal)
- **Karty (GUI)**: wiele plików; × w tytule karty to pole kliknięcia
- **Ciemny motyw**: kolory w stylu VS Code
- **Podział (GUI)**: edytor + konsola uruchamiania
- **Polski / angielski**: `--lang pl|en`, Widok → Język, albo `ASTRAEDIT_LANG`

### Edycja
- Kolorowanie składni (Pygments; pełne do 500 KB, potem okno widoczne, wyłączone powyżej 5 MB)
- Numeracja linii (szerokość rośnie z plikiem). Bez zawijania wierszy — długie linie mają poziomy scroll.
- Dopasowanie nawiasów (`()` `[]` `{}`; pomija stringi i komentarze; `<`/`>` to operatory)
- Cofnij / Ponów
- Szkic auto-zapisu co 30 s (`.astraedit/autosave/*.autosave` obok pliku; Ctrl+S zapisuje oryginał)

### Wyszukiwanie
- Znajdź i zamień, w tym wyrażenia regularne
- Znajdź następny (F3) — to nie jest szukanie w trakcie pisania
- Domyślnie bez rozróżniania wielkości liter
- Przejdź do linii (Ctrl+G)

### Uruchamianie
- **Tylko Python** (`.py`, `.pyw`). Inne pliki zostają w edytorze; F5 mówi dlaczego
- Konsola GUI: stdin / stdout / stderr; `>>>` (pusty Enter wysyła nową linię)
- STOP najpierw kończy proces, potem zabija drzewo, jeśli nadal działa
- Kolory: zielony stdin, czerwony stderr, niebieski status
- F5 najpierw zapisuje, potem uruchamia

### Bezpieczeństwo
- Wykrywanie plików binarnych (bajt NUL w pierwszym 1 KB); taki plik nie jest zapisywany z powrotem jako tekst
- Próby kodowania po kolei: UTF-8, UTF-8-SIG, CP1250, ISO-8859-2, na końcu Latin-1 (Latin-1 przyjmuje każdy bajt, więc musi być ostatni)
- Zapis atomowy (tmp + fsync + replace) i `errors=strict`. Przy błędzie kodowania proponowane jest UTF-8; dokument zostaje brudny
- Wykryte kodowanie i końce linii (`LF` / `CRLF` / `CR`) są zachowywane w GUI i TUI
- Tryb tylko do odczytu bez uprawnień zapisu
- Pytanie przed zamknięciem niezapisanych kart

### Pliki
- 10 ostatnio otwartych
- Otwieranie wielu plików naraz
- Menu kontekstowe karty: zamknij / zamknij inne / zamknij wszystko

---

## Wymagania

- **Python** 3.7+
- **System**: Windows, Linux, macOS
- GUI używa Tkinter (zwykle wbudowane)
- TUI i podświetlanie to opcjonalne dodatki

```bash
pip install -r requirements.txt
```

---

## Instalacja

```bash
git clone https://github.com/Maciej-EriAmo/Astraedit.git
cd Astraedit
pip install -r requirements.txt
```

---

## Użycie

```bash
python astraedit.py
python astraedit.py main.py utils.py config.json
python astraedit.py --gui main.py
python astraedit.py --tui main.py
# TUI zawsze startuje po angielsku; F8 przełącza EN/PL. Wymuś polski: --lang pl
python astraedit.py --lang pl
python astraedit.py --lang en
```

Stary launcher `Astraedit-4.5.py` nadal działa — wywołuje `astraedit.py`.

Zmienna środowiskowa: `ASTRAEDIT_LANG=pl` albo `en`.

Bez `--lang`: zapisany config, potem środowisko, potem locale systemu (`pl_*` → polski, inaczej angielski).

Pełna dokumentacja skrótów, trybów i rozwiązywania problemów: **[README.md](README.md)** (wersja angielska, ten sam zakres).

---

## Język

| Sposób | Przykład |
|--------|----------|
| CLI | `python astraedit.py --lang pl` |
| Menu | Widok → Język → Polski / English |
| Środowisko | `set ASTRAEDIT_LANG=pl` |
| Config | pole `language` w `~/.astraedit_config.json` |

Tłumaczenia są w `i18n.py`.

---

## Licencja

MIT — zobacz [LICENSE](LICENSE). Copyright (c) 2025 Maciej Mazur.

## Autor

**Maciej Mazur** — [@Maciej-EriAmo](https://github.com/Maciej-EriAmo)
