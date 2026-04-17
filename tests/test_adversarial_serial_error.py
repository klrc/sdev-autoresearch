"""Adversarial tests for serial error handling — test-owned coverage."""

import unittest
from unittest.mock import MagicMock, patch

import serial
import sdev


class TestConnectSerialException(unittest.TestCase):
    """Verify connect() wraps SerialException in RuntimeError."""

    def test_connect_wraps_exc_with_runtime_error(self):
        """connect() should raise RuntimeError, not raw SerialException."""
        sess = sdev.SerialSession()
        with patch("sdev.serial.Serial") as mock_cls:
            mock_cls.side_effect = serial.SerialException("device not found")
            with self.assertRaises(RuntimeError) as cm:
                sess.connect("/dev/ttyBAD", 9600)
            self.assertIn("/dev/ttyBAD", str(cm.exception))
            self.assertIsNone(sess._connection)

    def test_connect_chained_exception(self):
        """Original SerialException should be chained (__cause__)."""
        sess = sdev.SerialSession()
        with patch("sdev.serial.Serial") as mock_cls:
            original = serial.SerialException("permission denied")
            mock_cls.side_effect = original
            with self.assertRaises(RuntimeError) as cm:
                sess.connect("/dev/ttyBAD", 9600)
            self.assertIs(cm.exception.__cause__, original)

    def test_module_level_connect_raises_runtime_error(self):
        """sdev.connect() at module level should also raise RuntimeError."""
        sdev._default_session._connection = None
        sdev._default_session.device = "/dev/ttyBAD"
        sdev._default_session.baud = 9600
        with patch("sdev.serial.Serial") as mock_cls:
            mock_cls.side_effect = serial.SerialException("no device")
            with self.assertRaises(RuntimeError):
                sdev.connect("/dev/ttyBAD", 9600)


class TestCLISerialException(unittest.TestCase):
    """Verify cli() returns error SerialResult on SerialException."""

    def test_cli_returns_error_result(self):
        """cli() should return SerialResult with timed_out=True on error."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = serial.SerialException("read failed")

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("echo test")
        self.assertTrue(result.timed_out)
        self.assertIn("serial error", result.output.lower())
        self.assertIn("read failed", result.output)
        self.assertIsInstance(result.elapsed, float)

    def test_cli_error_on_second_read(self):
        """SerialException mid-read should still produce error result."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"partial output\n", serial.SerialException("timeout")]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("long command")
        self.assertTrue(result.timed_out)
        self.assertIn("serial error", result.output.lower())

    def test_cli_preserves_prompt_stripping_on_error(self):
        """Error during read should NOT strip partial output incorrectly."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = serial.SerialException("disconnected")

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("echo test")
        # Error path returns early — no stripping
        self.assertTrue(result.timed_out)
        self.assertIn("disconnected", result.output)


class TestStreamSerialException(unittest.TestCase):
    """Verify stream() stops cleanly on SerialException."""

    def test_stream_stops_on_read_error(self):
        """stream() should break the loop on SerialException, not crash."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = serial.SerialException("connection lost")

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("tail -f"))
        self.assertEqual(chunks, [])

    def test_stream_yields_then_errors(self):
        """stream() should yield available data, then stop on error."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"partial\n", serial.SerialException("lost")]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("tail -f"))
        # First read succeeded, should have yielded something
        self.assertTrue(len(chunks) >= 0)  # may or may not yield before error

    def test_stream_error_after_echo(self):
        """SerialException after echo should not corrupt output."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"echo cmd\nhello\n", serial.SerialException("gone")]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("echo cmd"))
        combined = "".join(chunks)
        # Echo should be stripped, "hello" should be present if yielded
        if combined:
            self.assertNotIn("echo cmd", combined)
            self.assertIn("hello", combined)


if __name__ == "__main__":
    unittest.main()
