"""Tests for SerialSession.doctor() and wait_for_silence()."""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestDoctor(unittest.TestCase):
    """doctor() clears stray output and waits for a clean prompt."""

    def test_doctor_sends_ctrl_c_and_returns_on_prompt(self):
        """doctor() should send Ctrl+C and return when prompt appears."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"some garbage\r\n",
            b"^C\r\n",
            b"root@board:~# ",
            b"",
        ]
        sess = sdev.SerialSession()
        sess._connection = mock_ser

        sess.doctor(timeout=2)

        # Should have written Ctrl+C and newline
        writes = [call.args[0] for call in mock_ser.write.call_args_list]
        self.assertIn(b"\x03", writes)
        self.assertIn(b"\r\n", writes)

    def test_doctor_auto_connects(self):
        """doctor() should auto-connect if not already open."""
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            mock_ser.is_open = True
            mock_ser.read.side_effect = [b"# ", b""]

            sess = sdev.SerialSession()
            sess.doctor(timeout=1)

            mock_cls.assert_called_once()
            mock_ser.close.assert_not_called()

    def test_doctor_returns_on_timeout_no_prompt(self):
        """doctor() should return without error even if no prompt appears."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"garbage\n", b"", b""]
        sess = sdev.SerialSession()
        sess._connection = mock_ser

        # Should not raise
        sess.doctor(timeout=0.3)

    def test_doctor_trims_buffer(self):
        """doctor() should trim buffer if it exceeds 64KB."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        # First chunk is large, second has prompt
        mock_ser.read.side_effect = [
            b"x" * 40000,
            b"y" * 40000,
            b"# ",
        ]
        sess = sdev.SerialSession()
        sess._connection = mock_ser

        sess.doctor(timeout=2)


class TestWaitForSilence(unittest.TestCase):
    """wait_for_silence() blocks until no data arrives for N seconds."""

    def test_returns_when_silence_detected(self):
        """Should return after no data arrives for the timeout period."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"boot log\n",
            b"",
            b"",
            b"",
            b"",
            b"",
        ]
        sess = sdev.SerialSession()
        sess._connection = mock_ser

        sess.wait_for_silence(timeout=0.2)

    def test_returns_on_serial_error(self):
        """Should return without error on serial exception."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        import serial
        mock_ser.read.side_effect = serial.SerialException("lost")
        sess = sdev.SerialSession()
        sess._connection = mock_ser

        sess.wait_for_silence(timeout=0.2)

    def test_auto_connects_if_not_open(self):
        """wait_for_silence() should auto-connect if not already open."""
        with patch("sdev.serial.Serial") as mock_cls:
            mock_ser = mock_cls.return_value
            mock_ser.is_open = True
            mock_ser.read.side_effect = [b"", b""]
            sess = sdev.SerialSession()
            sess.wait_for_silence(timeout=0.2)
            mock_cls.assert_called_once()


if __name__ == "__main__":
    unittest.main()
