# AstraEdit 4.5 — Interactive IDE

[![Version](https://img.shields.io/badge/version-4.5-blue)](https://github.com/Maciej-EriAmo/Astraedit)
[![Python](https://img.shields.io/badge/python-3.7+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

[English](README.md) | **Polski**

Hybrydowy edytor tekstu / małe IDE w Pythonie. Działa jako **GUI** (Tkinter) albo **TUI** (prompt_toolkit), z interaktywną konsolą: F5 uruchamia bieżący plik, `input()` przyjmuje dane z paska `>>>`, stdout/stderr widać na żywo.

---

## Funkcje

### Interfejs
- **Dwa tryby**: GUI (Tkinter) i TUI (terminal)
- **Karty**: wiele plików, zamykanie przez ×
- **Ciemny motyw**: kolory w stylu VS Code
- **Podział**: edytor + konsola
- **Polski / angielski**: `--lang pl|en`, Widok → Język, albo `ASTRAEDIT_LANG`

### Edycja
- Kolorowanie składni (Pygments)
- Numeracja linii (szerokość rośnie z plikiem)
- Dopasowanie nawiasów (`()` `[]` `{}` `<>`, limit 2000 znaków)
- Cofnij / Ponów
- Auto-zapis co 30 s (pomija pliki tylko do odczytu)

### Wyszukiwanie
- Znajdź i zamień, w tym wyrażenia regularne
- Następne wystąpienie (F3)
- Domyślnie bez rozróżniania wielkości liter
- Przejdź do linii (Ctrl+G)

### Uruchamianie
- Konsola z stdin / stdout / stderr
- `input()` z paska `>>>` (pusty Enter wysyła nową linię)
- Przycisk STOP przerywa proces
- Kolory: zielony stdin, czerwony stderr, niebieski status
- F5 uruchamia bieżący plik (najpierw zapis)

### Bezpieczeństwo
- Wykrywanie plików binarnych (bajt NUL w pierwszym 1 KB)
- Autodetekcja kodowania: UTF-8, UTF-8-SIG, CP1250, Latin-1, ISO-8859-2
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
