"""Adversarial tests for run() connect-in-try fix — test-owned coverage."""

import unittest
from unittest.mock import MagicMock, patch

import serial

import sdev


class TestRunConnectInTry(unittest.TestCase):
    """Guard: run() must close session even if connect() fails."""

    def test_run_closes_on_connect_failure(self):
        """run() should call close() even when connect() raises RuntimeError."""
        with patch.object(sdev, "SerialSession") as mock_cls:
            mock_sess = MagicMock()
            mock_cls.return_value = mock_sess
            mock_sess.connect.side_effect = RuntimeError("Cannot open /dev/ttyX: no device")

            with self.assertRaises(RuntimeError):
                sdev.run("/dev/ttyX", 115200, "echo test")

            mock_sess.connect.assert_called_once()
            mock_sess.close.assert_called_once()

    def test_run_closes_on_success(self):
        """run() should call close() on the happy path."""
        with patch.object(sdev, "SerialSession") as mock_cls:
            mock_sess = MagicMock()
            mock_cls.return_value = mock_sess
            mock_sess.cli.return_value = sdev.SerialResult(
                "echo ok", "ok\n", False, 0.1)

            result = sdev.run("/dev/ttyS0", 9600, "echo ok")

            self.assertEqual(result.output, "ok\n")
            mock_sess.connect.assert_called_once()
            mock_sess.cli.assert_called_once()
            mock_sess.close.assert_called_once()

    def test_run_close_despite_cli_error(self):
        """run() should close() even if cli() raises."""
        with patch.object(sdev, "SerialSession") as mock_cls:
            mock_sess = MagicMock()
            mock_cls.return_value = mock_sess
            mock_sess.cli.side_effect = serial.SerialException("broken")

            with self.assertRaises(serial.SerialException):
                sdev.run("/dev/ttyS0", 9600, "echo boom")

            mock_sess.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
