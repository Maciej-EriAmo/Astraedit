# 🚀 AstraEdit 4.5 - Interactive IDE

![Version](https://img.shields.io/badge/version-4.5-blue)
![Python](https://img.shields.io/badge/python-3.7+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

**Hybrydowy edytor tekstu / IDE z pełną obsługą interaktywnej konsoli**

AstraEdit to nowoczesny edytor tekstowy i IDE napisany w Pythonie, oferujący zarówno interfejs graficzny (GUI) jak i konsolowy (TUI). Idealny do szybkiego edytowania kodu, uruchamiania skryptów Pythona z interaktywnym debugowaniem oraz pracy z wieloma plikami jednocześnie.

---

## ✨ Główne funkcje

### 🎨 Interfejs
- **Dual Mode**: GUI (Tkinter) i TUI (prompt_toolkit)
- **System kart**: Wielokrotne otwarte pliki z przyciskami zamykania (×)
- **Dark Mode**: Profesjonalny ciemny motyw inspirowany VS Code
- **Split View**: Edytor + interaktywna konsola w jednym oknie

### 📝 Edycja
- **Syntax Highlighting**: Kolorowanie składni dla wielu języków (Pygments)
- **Numeracja linii**: Automatyczna z synchronizacją scroll
- **Bracket Matching**: Inteligentne podświetlanie par nawiasów (optymalizowane)
- **Undo/Redo**: Pełna historia zmian
- **Auto-save**: Automatyczne zapisywanie co 30s

### 🔍 Wyszukiwanie
- **Find & Replace**: Z obsługą wyrażeń regularnych (Regex)
- **Incremental Search**: Wyszukiwanie przyrostowe (F3)
- **Case-insensitive**: Domyślnie ignoruje wielkość liter
- **Go to Line**: Szybkie przejście do linii (Ctrl+G)

### ▶️ Uruchamianie kodu (NOWOŚĆ!)
- **Interaktywna konsola**: Pełna obsługa stdin/stdout/stderr
- **Input handling**: Możliwość wprowadzania danych (`input()`) w czasie rzeczywistym
- **Proces kontroli**: Przycisk STOP do przerywania wykonania
- **Kolorowanie outputu**: 
  - 🟢 Zielony: stdin (twoje wejście)
  - 🔴 Czerwony: stderr (błędy)
  - 🔵 Niebieski: info (komunikaty systemu)
- **Uruchom przez F5**: Natychmiastowe wykonanie aktualnego pliku

### 🛡️ Bezpieczeństwo
- **Binary file detection**: Automatyczne wykrywanie plików binarnych
- **Encoding auto-detection**: Inteligentne rozpoznawanie kodowania (UTF-8, CP1250, Latin-1, etc.)
- **Read-only mode**: Automatyczny tryb tylko do odczytu dla plików bez uprawnień
- **Unsaved changes protection**: Ostrzeżenie przed zamknięciem niezapisanych plików

### 📂 Zarządzanie plikami
- **Ostatnio otwierane**: Historia 10 ostatnich plików
- **Multi-file open**: Otwieranie wielu plików jednocześnie
- **Drag & drop support**: Przeciąganie plików (w planach)
- **Tab management**: Menu kontekstowe (prawy przycisk myszy na karcie)

---

## 📋 Wymagania systemowe

### Minimalne
- **Python**: 3.7 lub nowszy
- **System**: Windows, Linux, macOS
- **RAM**: 256 MB
- **Dysk**: 50 MB wolnego miejsca

### Wymagane biblioteki

#### Tryb GUI (zalecany)
```bash
tkinter  # Zwykle wbudowane w Pythonie
```

#### Tryb TUI (opcjonalny)
```bash
pip install prompt_toolkit
pip install pyperclip  # Opcjonalnie dla systemowego schowka
```

#### Syntax Highlighting (opcjonalny)
```bash
pip install pygments
```

---

## 🚀 Instalacja

### Szybka instalacja (wszystkie zależności)
```bash
# Klonowanie repozytorium
git clone https://github.com/Maciej615/AstraEdit.git
cd AstraEdit

# Instalacja zależności
pip install -r requirements.txt
```

### Plik `requirements.txt`
```
prompt_toolkit>=3.0.0
pygments>=2.10.0
pyperclip>=1.8.2
```

### Bez zależności (tylko GUI)
```bash
# Python zwykle ma wbudowany tkinter
python astraedit.py
```

---

## 🎮 Użycie

### Podstawowe uruchomienie
```bash
# Uruchom z domyślnym plikiem
python astraedit.py

# Otwórz konkretny plik
python astraedit.py moj_skrypt.py

# Otwórz wiele plików (każdy w osobnej karcie)
python astraedit.py main.py utils.py config.json

# Wymuś tryb GUI
python astraedit.py --gui moj_plik.py

# Wymuś tryb TUI (terminal)
python astraedit.py --tui moj_plik.py
```

### Przykład interaktywnego użycia

1. **Utwórz plik testowy** `hello.py`:
```python
name = input("Jak masz na imię? ")
print(f"Cześć, {name}!")

age = input("Ile masz lat? ")
print(f"Masz {age} lat - świetnie!")

for i in range(3):
    print(f"Liczę: {i+1}")
print("Koniec!")
```

2. **Uruchom AstraEdit**:
```bash
python astraedit.py hello.py
```

3. **Naciśnij F5** aby uruchomić

4. **Wpisz odpowiedzi** w pasku `>>>` na dole konsoli

5. **Zobacz wyniki** w czasie rzeczywistym!

---

## ⌨️ Skróty klawiszowe

### 📁 Pliki i karty
| Skrót | Akcja |
|-------|-------|
| `Ctrl + N` | Nowa karta |
| `Ctrl + O` | Otwórz plik(i) |
| `Ctrl + S` | Zapisz bieżącą kartę |
| `Ctrl + Shift + S` | Zapisz wszystkie karty |
| `Ctrl + W` | Zamknij kartę |
| `F2` | Zapisz jako... |
| Klik na `×` | Zamknij kartę (przycisk) |

### ✏️ Edycja
| Skrót | Akcja |
|-------|-------|
| `Ctrl + Z` | Cofnij |
| `Ctrl + Y` | Ponów |
| `Ctrl + C` | Kopiuj |
| `Ctrl + V` | Wklej |
| `Ctrl + X` | Wytnij |
| `Ctrl + A` | Zaznacz wszystko |

### 🔍 Wyszukiwanie
| Skrót | Akcja |
|-------|-------|
| `Ctrl + F` | Znajdź (z opcją Regex) |
| `F3` | Znajdź następny |
| `Ctrl + H` | Znajdź i zamień |
| `Ctrl + G` | Przejdź do linii |

### ▶️ Uruchamianie kodu
| Skrót | Akcja |
|-------|-------|
| `F5` | Uruchom aktualny plik |
| Przycisk `STOP` | Zatrzymaj proces |
| Przycisk `Wyczyść` | Wyczyść konsolę |
| `Enter` w `>>>` | Wyślij input do programu |

### ℹ️ Pomoc
| Skrót | Akcja |
|-------|-------|
| `F1` | Okno pomocy |

---

## 🎨 Tryby pracy

### GUI Mode (Tkinter)
- **Automatyczna detekcja**: Uruchamia się gdy dostępny jest serwer X/Wayland/Windows
- **Funkcje**: Pełna obsługa kart, interaktywna konsola, menu kontekstowe
- **Zalecany dla**: Codziennej pracy, debugowania, projektów wieloplikowych

### TUI Mode (Terminal)
- **Uruchomienie**: `python astraedit.py --tui plik.py`
- **Funkcje**: Pełny edytor w terminalu, syntax highlighting, search
- **Zalecany dla**: Pracy zdalnej (SSH), serwerów bez GUI, minimalistów
- **Uruchamianie kodu**: Zawiesza edytor i przełącza do konsoli (F5)

---

## 🛠️ Zaawansowane funkcje

### Wyrażenia regularne (Regex)

W oknie wyszukiwania zaznacz checkbox **"Użyj wyrażeń regularnych"**:
```regex
# Znajdź wszystkie liczby
\d+

# Znajdź funkcje w Pythonie
def\s+\w+\s*\(

# Znajdź adresy email
[\w\.-]+@[\w\.-]+\.\w+

# Znajdź i zamień
Znajdź: (\w+)_(\w+)
Zamień: \2_\1
```

### Auto-save

- **Domyślnie włączone**: Zapisuje co 30 sekund
- **Wyłączenie**: Menu → Widok → ☐ Auto-zapisywanie
- **Nie zapisuje**: Plików tylko do odczytu
- **Wskaźnik**: Kropka (●) przy nazwie karty oznacza niezapisane zmiany

### Menu kontekstowe kart

**Prawy przycisk myszy** na karcie:
- Zamknij kartę
- Zamknij inne karty
- Zamknij wszystko

### Bracket Matching

Automatyczne podświetlanie par nawiasów:
- Wspiera: `()` `[]` `{}` `<>`
- Limit przeszukiwania: 2000 znaków (optymalizacja wydajności)
- Podświetla gdy kursor jest przy nawiasie

---

## 📊 Obsługiwane języki (Syntax Highlighting)

Dzięki Pygments, AstraEdit rozpoznaje setki języków:

**Popularne:**
- Python (.py)
- JavaScript (.js, .jsx)
- C/C++ (.c, .cpp, .h)
- Java (.java)
- HTML/CSS (.html, .css)
- Markdown (.md)
- JSON (.json)
- XML (.xml)
- SQL (.sql)
- Bash/Shell (.sh, .bash)

**I wiele więcej...**

---

## 🐛 Rozwiązywanie problemów

### Nie działa Syntax Highlighting
```bash
pip install pygments
```

### Nie działa schowek systemowy (TUI)
```bash
pip install pyperclip
```

### Błąd "Brak biblioteki prompt_toolkit"
```bash
pip install prompt_toolkit
```

### Plik się nie otwiera
- Sprawdź czy to plik binarny (AstraEdit obsługuje tylko pliki tekstowe)
- Sprawdź uprawnienia do pliku
- Sprawdź kodowanie (wspierane: UTF-8, CP1250, Latin-1, ISO-8859-2)

### Konsola nie pokazuje outputu
- Upewnij się że używasz `print()` w kodzie
- Sprawdź czy proces się uruchomił (status na pasku)
- Dla programów które wymagają terminala użyj trybu TUI

### Proces się nie zatrzymuje
- Kliknij przycisk **⬛ STOP**
- Jeśli to nie pomoże, zamknij AstraEdit (proces zostanie zabity automatycznie)

---

## 🗺️ Roadmap (Przyszłe funkcje)

### Wersja 5.0
- [ ] Autocomplete (IntelliSense)
- [ ] Git integration (status, commit, diff)
- [ ] Debugger (breakpoints, step-through)
- [ ] Split panes (podział edytora pionowo/poziomo)
- [ ] Minimap (mapa kodu jak w VS Code)
- [ ] Plugins system (rozszerzenia)

### Wersja 4.6
- [ ] Project explorer (drzewo plików)
- [ ] Terminal wbudowany (nie tylko konsola)
- [ ] Snippets (szablony kodu)
- [ ] Multi-cursor editing
- [ ] Code folding (zwijanie bloków)

---

## 🤝 Wkład w projekt

Chcesz pomóc? Świetnie! 

### Jak zacząć?
1. Fork repozytorium
2. Stwórz branch: `git checkout -b feature/super-funkcja`
3. Commit zmian: `git commit -m 'Dodaj super funkcję'`
4. Push: `git push origin feature/super-funkcja`
5. Otwórz Pull Request

### Czego szukamy?
- 🐛 Naprawy bugów
- ✨ Nowe funkcje
- 📝 Poprawki dokumentacji
- 🌍 Tłumaczenia (internationalization)
- 🎨 Ulepszenia UI/UX

---

## 📜 Licencja

MIT License

Copyright (c) 2025 Maciej Mazur

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 👨‍💻 Autor

**Maciej Mazur** (@drwisz)
- GitHub: [@Maciej615](https://github.com/Maciej615)
- Medium: [@drwisz](https://medium.com/@drwisz)
- Email: [maciej.mazur@example.com]

---

## 🙏 Podziękowania

- **Anthropic Claude** - za pomoc w tworzeniu tego projektu
- **Gemini Google** -za pomoc w usuwaniu błędów i pomysły na rozwój
- **Pygments** - za doskonałą bibliotekę syntax highlighting
- **prompt_toolkit** - za potężne narzędzia do budowy TUI
- **Społeczność Python** - za nieustające wsparcie

---

## 📸 Screenshots
```
┌─────────────────────────────────────────────────────────────┐
│  AstraEdit 4.5 [GUI] – main.py                      ☐ ☒ ✕  │
├─────────────────────────────────────────────────────────────┤
│ Plik  Edycja  Uruchom  Widok  Pomoc                        │
├─────────────────────────────────────────────────────────────┤
│ main.py  ×  │  utils.py  ×  │  config.json  ×             │
├────┬────────────────────────────────────────────────────────┤
│  1 │ def hello_world():                                     │
│  2 │     name = input("Imię: ")                            │
│  3 │     print(f"Cześć, {name}!")                          │
│  4 │                                                        │
│  5 │ if __name__ == "__main__":                            │
│  6 │     hello_world()                                     │
│    │                                                        │
├────┴────────────────────────────────────────────────────────┤
│ 📟 Konsola Interaktywna              🗑 Wyczyść  ⬛ STOP   │
├─────────────────────────────────────────────────────────────┤
│ ============================================================│
│   Uruchamianie: main.py                                    │
│ ============================================================│
│                                                             │
│ Imię: Maciej                                               │
│ Cześć, Maciej!                                             │
│                                                             │
│ >>> _                                                       │
├─────────────────────────────────────────────────────────────┤
│ Ln 3/6, Col 15 | utf-8 | main.py | F5: Uruchom | F1: Pomoc│
└─────────────────────────────────────────────────────────────┘
```

---

## ⭐ Daj gwiazdkę!

Jeśli AstraEdit okazał się przydatny, zostaw ⭐ na GitHubie!

**Happy Coding! 🚀**

---

*"Code is poetry, and every editor is a canvas."* - AstraEdit Philosophy
