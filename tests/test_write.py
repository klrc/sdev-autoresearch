"""Tests for SerialSession.write() and sdev.write()."""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestSerialSessionWrite(unittest.TestCase):
    """SerialSession.write() should send bytes and return count."""

    def test_write_returns_byte_count(self):
        """write() should return the number of bytes written."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.write.return_value = 5

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        n = sess.write(b"hello")
        self.assertEqual(n, 5)
        mock_ser.write.assert_called_once_with(b"hello")

    def test_write_calls_flush(self):
        """write() should flush after writing."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        sess.write(b"test")
        mock_ser.flush.assert_called_once()

    def test_write_raises_when_not_connected(self):
        """write() should raise RuntimeError when not connected."""
        sess = sdev.SerialSession()
        with self.assertRaises(RuntimeError):
            sess.write(b"test")


class TestModuleLevelWrite(unittest.TestCase):
    """sdev.write() should delegate to default session."""

    def test_module_write_delegates(self):
        """sdev.write() should call default session's write()."""
        with patch.object(sdev, "_default_session") as mock_sess:
            mock_sess.write.return_value = 4
            n = sdev.write(b"ping")
            mock_sess.write.assert_called_once_with(b"ping")
            self.assertEqual(n, 4)

    def test_write_in_all(self):
        """write should be listed in __all__."""
        self.assertIn("write", sdev.__all__)


if __name__ == "__main__":
    unittest.main()
