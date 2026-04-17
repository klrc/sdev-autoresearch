"""Basic tests for sdev — no real hardware required."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sdev


class TestSerialResult(unittest.TestCase):
    def test_dataclass_fields(self):
        r = sdev.SerialResult("echo hi", "hi\n", False, 0.5)
        self.assertEqual(r.command, "echo hi")
        self.assertEqual(r.output, "hi\n")
        self.assertFalse(r.timed_out)
        self.assertAlmostEqual(r.elapsed, 0.5)


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


class TestEnsureConnection(unittest.TestCase):
    def test_raises_when_not_connected(self):
        with patch.object(sdev, "_connection", None):
            with self.assertRaises(RuntimeError):
                sdev.ensure_connection()


class TestCliWithTimeout(unittest.TestCase):
    def test_timeout_returns_early(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        with patch.object(sdev, "_connection", mock_ser):
            result = sdev.cli("sleep 999", timeout=0.2)
            self.assertTrue(result.timed_out)
            self.assertGreater(result.elapsed, 0.15)


if __name__ == "__main__":
    unittest.main()
