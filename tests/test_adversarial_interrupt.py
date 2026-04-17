"""Adversarial tests for interrupt() method — test-owned coverage."""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestSerialSessionInterrupt(unittest.TestCase):
    """Verify SerialSession.interrupt() sends Ctrl+C correctly."""

    def test_interrupt_writes_ctrl_c(self):
        """interrupt() should write \\x03 and flush."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        sess.interrupt()

        mock_ser.write.assert_called_once_with(b"\x03")
        mock_ser.flush.assert_called_once()

    def test_interrupt_raises_when_not_connected(self):
        """interrupt() should raise if no connection is open."""
        sess = sdev.SerialSession()
        with self.assertRaises(RuntimeError):
            sess.interrupt()


class TestModuleLevelInterrupt(unittest.TestCase):
    """Verify module-level sdev.interrupt() delegates to default session."""

    def test_interrupt_delegates_to_default_session(self):
        """sdev.interrupt() should call interrupt() on the default session."""
        mock_sess = MagicMock()
        mock_sess.is_open = True

        with patch.object(sdev, "_default_session", mock_sess):
            sdev.interrupt()

        mock_sess.interrupt.assert_called_once()

    def test_interrupt_raises_when_default_not_connected(self):
        """sdev.interrupt() should raise if default session isn't open."""
        with patch.object(sdev, "_default_session", sdev.SerialSession()):
            with self.assertRaises(RuntimeError):
                sdev.interrupt()


class TestInterruptInAll(unittest.TestCase):
    """Verify interrupt is in __all__."""

    def test_interrupt_in_all(self):
        """interrupt should be listed in __all__."""
        self.assertIn("interrupt", sdev.__all__)

    def test_interrupt_importable(self):
        """interrupt should be accessible on the module."""
        self.assertTrue(hasattr(sdev, "interrupt"))
        self.assertTrue(callable(getattr(sdev, "interrupt")))


if __name__ == "__main__":
    unittest.main()
