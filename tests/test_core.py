"""Unit tests for encoding order, i18n, untitled names, and language helpers."""

import os
import tempfile
import unittest
from pathlib import Path

from i18n import _STRINGS, get_lang, normalize_lang, set_lang, t
from astraedit import TEXT_ENCODINGS, is_python_source, next_untitled_name, read_text_file_smart


class TestI18n(unittest.TestCase):
    def test_key_parity(self):
        self.assertEqual(set(_STRINGS["en"]), set(_STRINGS["pl"]))

    def test_aliases(self):
        self.assertEqual(normalize_lang("polish"), "pl")
        self.assertEqual(normalize_lang("polski"), "pl")
        self.assertEqual(normalize_lang("english"), "en")
        self.assertEqual(normalize_lang("pl_PL"), "pl")
        self.assertEqual(normalize_lang("en-US"), "en")

    def test_toggle_roundtrip(self):
        set_lang("en")
        self.assertIn("F8:EN/PL", t("status_tui"))
        set_lang("pl")
        self.assertIn("F8:EN/PL", t("status_tui"))
        self.assertEqual(get_lang(), "pl")
        set_lang("en")


class TestPythonSuffix(unittest.TestCase):
    def test_suffixes(self):
        self.assertTrue(is_python_source("main.py"))
        self.assertTrue(is_python_source(r"C:\x\App.PYW"))
        self.assertFalse(is_python_source("notes.txt"))
        self.assertFalse(is_python_source("script.py.bak"))


class TestEncodings(unittest.TestCase):
    def test_latin1_is_last_strict_codec(self):
        self.assertEqual(TEXT_ENCODINGS[-1], "latin-1")
        self.assertLess(TEXT_ENCODINGS.index("iso-8859-2"), TEXT_ENCODINGS.index("latin-1"))

    def test_utf8_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            path.write_text("żółć", encoding="utf-8")
            text, enc = read_text_file_smart(str(path))
            self.assertEqual(text, "żółć")
            self.assertEqual(enc, "utf-8")

    def test_binary_nul_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.bin"
            path.write_bytes(b"abc\x00def")
            with self.assertRaises(ValueError):
                read_text_file_smart(str(path))


class TestUntitled(unittest.TestCase):
    def test_skips_existing_disk_and_open_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                set_lang("en")
                Path("untitled.txt").write_text("taken", encoding="utf-8")
                name = next_untitled_name([])
                self.assertNotEqual(name, "untitled.txt")
                self.assertFalse(Path(name).exists())
                taken = {str(Path(name).resolve())}
                name2 = next_untitled_name(taken)
                self.assertNotEqual(name2, name)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
