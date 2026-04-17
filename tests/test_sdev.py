"""Tests for sdev — no real hardware required."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import sdev


class TestSerialResult(unittest.TestCase):
    def test_dataclass_fields(self):
        r = sdev.SerialResult("echo hi", "hi\n", False, 0.5)
        self.assertEqual(r.command, "echo hi")
        self.assertEqual(r.output, "hi\n")
        self.assertFalse(r.timed_out)
        self.assertAlmostEqual(r.elapsed, 0.5)


class TestParseResult(unittest.TestCase):
    def test_empty(self):
        r = sdev.ParseResult()
        self.assertEqual(r.lines, [])
        self.assertEqual(r.matched, [])
        self.assertEqual(r.raw, "")


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._orig = sdev.CONFIG_FILE

    def tearDown(self):
        sdev.CONFIG_FILE = self._orig

    def test_save_and_load_defaults(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            sdev.CONFIG_FILE = Path(td) / "defaults.json"
            sdev.save_default("/dev/ttyUSB1", 9600)
            d = sdev.load_defaults()
            self.assertEqual(d, {"device": "/dev/ttyUSB1", "baud": 9600})

    def test_load_defaults_missing(self):
        with patch.object(sdev, "CONFIG_FILE", Path("/nonexistent/path")):
            self.assertEqual(sdev.load_defaults(), {})


class TestPromptDetection(unittest.TestCase):
    def test_hash_prompt(self):
        self.assertTrue(sdev._prompt_detected(b"root@box:~# "))
        self.assertTrue(sdev._prompt_detected(b"output\n# "))

    def test_dollar_prompt(self):
        self.assertTrue(sdev._prompt_detected(b"user@host $ "))

    def test_no_prompt(self):
        self.assertFalse(sdev._prompt_detected(b"some random output"))


class TestStripPrompt(unittest.TestCase):
    def test_removes_trailing_prompt(self):
        self.assertEqual(sdev._strip_prompt(b"output\n# "), b"output\n")

    def test_leaves_promptless(self):
        self.assertEqual(sdev._strip_prompt(b"just output"), b"just output")


class TestStripEcho(unittest.TestCase):
    def test_removes_echoed_command(self):
        self.assertEqual(sdev._strip_echo(b"echo hi\nresult\n# ", "echo hi"), b"result\n# ")

    def test_no_match(self):
        self.assertEqual(sdev._strip_echo(b"result\n# ", "echo hi"), b"result\n# ")


class TestSerialSession(unittest.TestCase):
    def test_init_defaults(self):
        sess = sdev.SerialSession()
        self.assertEqual(sess.device, sdev.DEFAULT_DEVICE)
        self.assertEqual(sess.baud, sdev.DEFAULT_BAUD)

    def test_connect_opens_port(self):
        with patch("sdev.serial.Serial") as mock_cls:
            sess = sdev.SerialSession("/dev/ttyS0", 9600)
            sess.connect()
            mock_cls.assert_called_once_with("/dev/ttyS0", 9600, timeout=0.1)
            self.assertTrue(sess.is_open)

    def test_close(self):
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            sess = sdev.SerialSession()
            sess.connect()
            sess.close()
            mock_ser.close.assert_called_once()
            self.assertFalse(sess.is_open)

    def test_ensure_open_raises(self):
        sess = sdev.SerialSession()
        with self.assertRaises(RuntimeError):
            sess._ensure_open()

    def test_context_manager(self):
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            with sdev.SerialSession() as sess:
                self.assertTrue(sess.is_open)
            mock_ser.close.assert_called_once()

    def test_cli_timeout(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("sleep 999", timeout=0.2)
        self.assertTrue(result.timed_out)
        self.assertGreater(result.elapsed, 0.15)

    def test_stream_yields_chunks(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"hello ", b"world\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("echo hello world"))
        self.assertEqual(chunks, ["hello ", "world\n"])

    def test_stream_timeout(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("long-running", timeout=0.2))
        self.assertEqual(chunks, [])

    def test_parse_no_pattern(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"line1\nline2\n\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        r = sess.parse("cat file")
        self.assertEqual(r.lines, ["line1", "line2"])
        self.assertEqual(r.matched, [])

    def test_parse_with_pattern(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"error: bad\nok: fine\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        r = sess.parse("cat file", pattern=r"^error")
        self.assertEqual(r.matched, ["error: bad"])


class TestModuleLevelAPI(unittest.TestCase):
    """Backward-compat wrappers delegate to _default_session."""

    def test_ensure_raises_when_not_connected(self):
        sdev._default_session._connection = None
        with self.assertRaises(RuntimeError):
            sdev.ensure_connection()

    def test_cli_delegates_timeout(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sdev._default_session._connection = mock_ser
        result = sdev.cli("sleep 999", timeout=0.2)
        self.assertTrue(result.timed_out)


class TestRunOneShot(unittest.TestCase):
    def test_run_opens_and_closes(self):
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            mock_ser.is_open = True
            mock_ser.read.side_effect = [b"done\n# ", b""]

            result = sdev.run("/dev/ttyS0", 9600, "echo done")
            mock_cls.assert_called_once_with("/dev/ttyS0", 9600, timeout=0.1)
            mock_ser.close.assert_called_once()
            self.assertFalse(result.timed_out)


class TestCLIEntrypoint(unittest.TestCase):
    """Test __main__.py argument parsing and dispatch."""

    def test_stream_mode(self):
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            mock_ser.is_open = True
            mock_ser.read.side_effect = [b"chunk1\n", b"chunk2\n# ", b""]

            from sdev.__main__ import main
            import io
            captured = io.StringIO()
            with patch("sys.argv", ["sdev", "-p", "tail -f", "--stream",
                                     "-d", "/dev/ttyS0", "-b", "9600"]), \
                 patch("sys.stdout", captured):
                main()
            mock_cls.assert_called_once_with("/dev/ttyS0", 9600, timeout=0.1)
            mock_ser.close.assert_called_once()
            self.assertIn("chunk1", captured.getvalue())
            self.assertIn("chunk2", captured.getvalue())

    def test_parse_mode(self):
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            mock_ser.is_open = True
            mock_ser.read.side_effect = [b"MemTotal: 1000\nMemFree: 500\n# ", b""]

            from sdev.__main__ import main
            import io
            captured = io.StringIO()
            with patch("sys.argv", ["sdev", "-p", "cat /proc/meminfo",
                                     "--parse", "MemTotal",
                                     "-d", "/dev/ttyS0", "-b", "9600"]), \
                 patch("sys.stdout", captured):
                main()
            self.assertIn("MemTotal: 1000", captured.getvalue())
            self.assertNotIn("MemFree: 500", captured.getvalue())

    def test_parse_no_match(self):
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            mock_ser.is_open = True
            mock_ser.read.side_effect = [b"hello\n# ", b""]

            from sdev.__main__ import main
            with patch("sys.argv", ["sdev", "-p", "echo hello",
                                     "--parse", "NOTFOUND",
                                     "-d", "/dev/ttyS0", "-b", "9600"]):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 3)

    def test_normal_mode(self):
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            mock_ser.is_open = True
            mock_ser.read.side_effect = [b"output\n# ", b""]

            from sdev.__main__ import main
            import io
            captured = io.StringIO()
            with patch("sys.argv", ["sdev", "-p", "echo output",
                                     "-d", "/dev/ttyS0", "-b", "9600"]), \
                 patch("sys.stdout", captured):
                main()
            self.assertIn("output", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
