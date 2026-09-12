"""Unit tests for encoding, I/O, process control, i18n, and untitled names."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from i18n import _STRINGS, get_lang, normalize_lang, set_lang, t
from astraedit import (
    Application,
    AstraEditTUI,
    NEWLINE_CR,
    NEWLINE_CRLF,
    NEWLINE_LF,
    PROC_RUNNING,
    PROC_STARTING,
    TEXT_ENCODINGS,
    Document,
    DocumentView,
    ProcessManager,
    SearchPattern,
    autosave_path_for,
    buffer_completions,
    code_char_mask,
    compute_fold_end,
    detect_venv_python,
    expand_snippet,
    find_matching_bracket,
    get_best_lexer,
    get_lexer_for_filename,
    highlight_policy,
    is_python_source,
    newer_autosave,
    next_line_indent,
    next_untitled_name,
    offset_to_tk_index,
    popen_script,
    read_text_file_smart,
    resolve_python_executable,
    tk_index_to_offset,
    terminate_process_tree,
    toggle_hash_comments,
    write_text_file,
)

POLISH = "ąćęłńóśźż"


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
            text, enc, newline = read_text_file_smart(str(path))
            self.assertEqual(text, "żółć")
            self.assertEqual(enc, "utf-8")
            self.assertEqual(newline, NEWLINE_LF)

    def test_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.txt"
            path.write_text(POLISH, encoding="utf-8-sig")
            text, enc, _ = read_text_file_smart(str(path))
            self.assertEqual(text, POLISH)
            self.assertEqual(enc, "utf-8-sig")

    def test_cp1250_polish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pl.txt"
            path.write_bytes(POLISH.encode("cp1250"))
            text, enc, _ = read_text_file_smart(str(path))
            self.assertEqual(text, POLISH)
            self.assertEqual(enc, "cp1250")

    def test_iso8859_2_bytes_roundtrip(self):
        raw = POLISH.encode("iso-8859-2")
        self.assertEqual(raw.decode("iso-8859-2"), POLISH)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "l2.txt"
            write_text_file(str(path), POLISH, encoding="iso-8859-2")
            self.assertEqual(path.read_bytes(), raw)

    def test_latin1_bytes_roundtrip(self):
        sample = "café"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "l1.txt"
            write_text_file(str(path), sample, encoding="latin-1")
            self.assertEqual(path.read_bytes(), sample.encode("latin-1"))

    def test_strict_encode_rejects_unmappable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "strict.txt"
            path.write_text("ok", encoding="utf-8")
            with self.assertRaises(UnicodeEncodeError):
                write_text_file(str(path), "alpha α", encoding="cp1250")
            self.assertEqual(path.read_text(encoding="utf-8"), "ok")

    def test_binary_nul_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.bin"
            path.write_bytes(b"abc\x00def")
            with self.assertRaises(ValueError):
                read_text_file_smart(str(path))


class TestFileIO(unittest.TestCase):
    def test_atomic_write_no_tmp_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.txt"
            write_text_file(str(path), POLISH, encoding="utf-8")
            text, enc, _ = read_text_file_smart(str(path))
            self.assertEqual(text, POLISH)
            self.assertEqual(enc, "utf-8")
            leftovers = [p for p in Path(tmp).iterdir() if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_replace_failure_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keep.txt"
            path.write_text("original", encoding="utf-8")

            def boom(src, dst):
                raise OSError("disk full")

            with mock.patch("os.replace", boom):
                with self.assertRaises(OSError):
                    write_text_file(str(path), "new-content", encoding="utf-8")
            self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_save_as_leaves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.txt"
            dest = Path(tmp) / "dest.txt"
            src.write_text("src-body", encoding="utf-8")
            write_text_file(str(dest), "dest-body", encoding="utf-8")
            self.assertEqual(src.read_text(encoding="utf-8"), "src-body")
            self.assertEqual(dest.read_text(encoding="utf-8"), "dest-body")

    def test_autosave_does_not_touch_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dokument.py"
            path.write_text("print(1)\n", encoding="utf-8")
            draft = autosave_path_for(str(path))
            write_text_file(str(draft), "print(2)\n", encoding="utf-8")
            self.assertEqual(path.read_text(encoding="utf-8"), "print(1)\n")
            self.assertEqual(draft.read_text(encoding="utf-8"), "print(2)\n")
            self.assertEqual(draft.parent.name, "autosave")
            self.assertEqual(draft.parent.parent.name, ".astraedit")

    def test_newline_lf_crlf_cr(self):
        cases = (
            (b"a\nb\n", "a\nb\n", NEWLINE_LF),
            (b"a\r\nb\r\n", "a\nb\n", NEWLINE_CRLF),
            (b"a\rb\r", "a\nb\n", NEWLINE_CR),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for raw, editor, newline in cases:
                path = Path(tmp) / "nl.txt"
                path.write_bytes(raw)
                text, _, detected = read_text_file_smart(str(path))
                self.assertEqual(text, editor)
                self.assertEqual(detected, newline)
                write_text_file(str(path), text, encoding="utf-8", newline=detected)
                self.assertEqual(path.read_bytes(), raw)


class TestProcess(unittest.TestCase):
    def test_f5_race_second_start_blocked(self):
        runner = ProcessManager()
        self.assertTrue(runner.try_start())
        self.assertEqual(runner.state, PROC_STARTING)
        self.assertFalse(runner.try_start())
        runner.finish()
        self.assertTrue(runner.try_start())

    def test_stop_during_start_attaches_as_stop(self):
        runner = ProcessManager()
        self.assertTrue(runner.try_start())
        self.assertIsNone(runner.request_stop())
        fake = mock.Mock()
        fake.poll.return_value = None
        self.assertEqual(runner.attach(fake), "stop")

    def test_attach_running_then_stdin_target(self):
        runner = ProcessManager()
        runner.try_start()
        fake = mock.Mock()
        fake.poll.return_value = None
        self.assertEqual(runner.attach(fake), "run")
        self.assertEqual(runner.state, PROC_RUNNING)
        self.assertIs(runner.running_proc(), fake)

    def _script(self, tmp, body):
        path = Path(tmp) / "script.py"
        path.write_text(body, encoding="utf-8")
        return path

    def test_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._script(tmp, "print('hello-out')")
            proc = popen_script(str(path))
            out, err = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("hello-out", out)

    def test_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._script(tmp, "import sys; sys.stderr.write('hello-err\\n')")
            proc = popen_script(str(path))
            out, err = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("hello-err", err)

    def test_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._script(tmp, "print(input())")
            proc = popen_script(str(path))
            out, err = proc.communicate("ping\n", timeout=15)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("ping", out)

    def test_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._script(tmp, "import time; time.sleep(30)")
            proc = popen_script(str(path))
            terminate_process_tree(proc, timeout=0.8)
            proc.communicate(timeout=15)
            self.assertIsNotNone(proc.returncode)
            self.assertNotEqual(proc.returncode, 0)


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


class TestDocumentView(unittest.TestCase):
    def test_view_writes_through_to_document(self):
        doc = Document("x.txt", text="a")

        class View(DocumentView):
            def __init__(self, document):
                self.doc = document

        view = View(doc)
        view.is_modified = True
        view.file_encoding = "cp1250"
        self.assertTrue(doc.modified)
        self.assertEqual(doc.encoding, "cp1250")
        view.is_modified = False
        self.assertFalse(doc.modified)

    def test_save_failure_keeps_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keep.txt"
            path.write_text("old", encoding="utf-8")
            doc = Document.open(str(path))
            doc.modified = True

            def boom(src, dst):
                raise OSError("disk full")

            with mock.patch("os.replace", boom):
                with self.assertRaises(OSError):
                    doc.save("new")
            self.assertTrue(doc.modified)
            self.assertEqual(path.read_text(encoding="utf-8"), "old")

    def test_newer_autosave_when_original_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "untitled.txt"
            draft = autosave_path_for(str(path))
            write_text_file(str(draft), "draft-body", encoding="utf-8")
            self.assertEqual(newer_autosave(str(path)), draft)


class TestEditingHelpers(unittest.TestCase):
    def test_next_line_indent_colon(self):
        self.assertEqual(next_line_indent("def foo():", tab_size=4), "    ")
        self.assertEqual(next_line_indent("    if x:", tab_size=4), "        ")
        self.assertEqual(next_line_indent("    x = 1", tab_size=4), "    ")
        self.assertEqual(next_line_indent("# todo:", tab_size=4), "")

    def test_toggle_hash_comments(self):
        commented, uncommented = toggle_hash_comments(["    x = 1", "    y = 2"])
        self.assertFalse(uncommented)
        self.assertEqual(commented, ["    # x = 1", "    # y = 2"])
        restored, was_uncomment = toggle_hash_comments(commented)
        self.assertTrue(was_uncomment)
        self.assertEqual(restored, ["    x = 1", "    y = 2"])

    def test_compute_fold_end(self):
        lines = [
            "def foo():",
            "    x = 1",
            "    y = 2",
            "",
            "def bar():",
            "    pass",
        ]
        self.assertEqual(compute_fold_end(lines, 0), 2)
        self.assertEqual(compute_fold_end(lines, 4), 5)
        self.assertIsNone(compute_fold_end(lines, 1))
        self.assertIsNone(compute_fold_end(lines, 5))

    def test_compute_fold_end_nested(self):
        lines = [
            "if True:",
            "    if False:",
            "        z = 1",
            "    w = 2",
            "after",
        ]
        self.assertEqual(compute_fold_end(lines, 0), 3)
        self.assertEqual(compute_fold_end(lines, 1), 2)

    def test_compute_fold_end_no_body(self):
        self.assertIsNone(compute_fold_end(["def x():", "", "", "y = 1"], 0))

    def test_expand_snippet(self):
        text, first = expand_snippet("def ${1:name}(${2}):\n    ${3:pass}")
        self.assertEqual(first, "name")
        self.assertIn("def name():", text)
        self.assertIn("    pass", text)

    def test_buffer_completions(self):
        words = buffer_completions("foo_bar foo_baz foo", "foo_")
        self.assertEqual(words, ["foo_bar", "foo_baz"])

    def test_detect_venv_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            if os.name == "nt":
                exe = Path(tmp) / ".venv" / "Scripts" / "python.exe"
            else:
                exe = Path(tmp) / ".venv" / "bin" / "python"
            exe.parent.mkdir(parents=True)
            exe.write_text("", encoding="utf-8")
            nested = Path(tmp) / "pkg" / "mod.py"
            nested.parent.mkdir(parents=True)
            nested.write_text("x=1\n", encoding="utf-8")
            self.assertEqual(detect_venv_python(str(nested)), str(exe))
            self.assertEqual(
                resolve_python_executable(str(nested), configured="C:/Custom/python.exe"),
                "C:/Custom/python.exe",
            )

    def test_newer_autosave_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.txt"
            path.write_text("orig", encoding="utf-8")
            draft = autosave_path_for(str(path))
            write_text_file(str(draft), "draft", encoding="utf-8")
            os.utime(draft, (path.stat().st_mtime + 10, path.stat().st_mtime + 10))
            self.assertEqual(newer_autosave(str(path)), draft)


class TestSearch(unittest.TestCase):
    def test_bad_regex_raises(self):
        with self.assertRaises(ValueError):
            SearchPattern("[", True)

    def test_literal_find(self):
        spec = SearchPattern("AbC", False)
        match = spec.find("xxabcxx")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "abc")

    def test_replace_first_in_selection(self):
        spec = SearchPattern("a+", True)
        text, count = spec.replace_in("aaa b aa", "X", count=1)
        self.assertEqual(count, 1)
        self.assertEqual(text, "X b aa")

    def test_replace_does_not_require_fullmatch(self):
        spec = SearchPattern("foo", True)
        text, count = spec.replace_in("foo bar", "baz", count=1)
        self.assertEqual(count, 1)
        self.assertEqual(text, "baz bar")

    def test_literal_replace_preserves_backslashes(self):
        spec = SearchPattern("a", False)
        text, count = spec.replace_in("a", r"\1", count=1)
        self.assertEqual(count, 1)
        self.assertEqual(text, r"\1")

    def test_case_sensitive(self):
        spec = SearchPattern("AbC", False, ignore_case=False)
        self.assertIsNone(spec.find("xxabcxx"))
        self.assertIsNotNone(spec.find("xxAbCxx"))

    def test_whole_word(self):
        spec = SearchPattern("cat", False, ignore_case=True, whole_word=True)
        self.assertIsNone(spec.find("category"))
        match = spec.find("a cat sat")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "cat")


class TestHighlightAndBrackets(unittest.TestCase):
    def test_highlight_policy(self):
        self.assertEqual(highlight_policy(100)[0], "full")
        self.assertEqual(highlight_policy(600 * 1024)[0], "full")
        self.assertGreater(highlight_policy(600 * 1024)[1], highlight_policy(100)[1])
        self.assertEqual(highlight_policy(3 * 1024 * 1024)[0], "visible")
        self.assertEqual(highlight_policy(6 * 1024 * 1024)[0], "off")

    def test_tk_offset_roundtrip(self):
        text = "ab\ncd\nef"
        self.assertEqual(offset_to_tk_index(text, 4), "2.1")
        self.assertEqual(tk_index_to_offset(text, "2.1"), 4)
        self.assertEqual(tk_index_to_offset(text, offset_to_tk_index(text, 0)), 0)

    @unittest.skipUnless(get_lexer_for_filename, "Pygments not installed")
    def test_bracket_skips_string(self):
        text = 'x = "("\ny = (1)'
        lexer = get_best_lexer("sample.py")
        str_paren = text.index("(")
        mask = code_char_mask(text, lexer, str_paren)
        self.assertFalse(mask[str_paren])
        real = text.rfind("(")
        mask2 = code_char_mask(text, lexer, real)
        match = find_matching_bracket(text, real, 1, "(", ")", mask2)
        self.assertEqual(match, text.rfind(")"))


class TestTUIBindings(unittest.TestCase):
    @unittest.skipUnless(Application, "prompt_toolkit not installed")
    def test_key_bindings_construct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.py"
            path.write_text("x = 1\n", encoding="utf-8")
            tui = AstraEditTUI(str(path))
            kb = tui.create_key_bindings()
            self.assertTrue(len(kb.bindings) > 0)


if __name__ == "__main__":
    unittest.main()
