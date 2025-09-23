# AstraEdit

Konsolowy edytor tekstu w Pythonie zbudowany na `prompt_toolkit`.

## Co robi
- otwieranie / zapis plików
- podświetlanie składni (py/json/html)
- schowek przez `pyperclip`
- dialogi "Zapisz jako" i "Otwórz plik"

## Fałszywe alarmy AV (False positives)
AstraEdit może być czasem błędnie oznaczany przez niektóre programy antywirusowe, zwłaszcza jeśli binarka jest skompilowana (Nuitka/PyInstaller). Kod źródłowy jest publiczny:
https://github.com/<twoja_nazwa_użytkownika>/AstraEdit

Jeśli napotkasz fałszywy alarm:
- zgłoś false positive do producenta AV (np. Microsoft Defender),
- 
## Jak zbudować (krótko)
Instrukcja (opcjonalna) jak budować z Nuitka / PyInstaller — dodaj tu swoje kroki.

## Licencja
MIT — zobacz plik LICENSE.
