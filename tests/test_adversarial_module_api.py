"""Adversarial tests for __all__ and disconnect() — test-owned coverage."""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestAllExports(unittest.TestCase):
    """Verify __all__ matches actual public API."""

    def test_all_is_defined(self):
        """__all__ should exist."""
        self.assertTrue(hasattr(sdev, "__all__"))
        self.assertIsInstance(sdev.__all__, list)

    def test_all_names_are_importable(self):
        """Every name in __all__ should be accessible via getattr."""
        for name in sdev.__all__:
            self.assertTrue(
                hasattr(sdev, name),
                f"__all__ lists {name!r} but it is not accessible on the module"
            )

    def test_all_contains_key_classes_and_functions(self):
        """Critical public API names should be in __all__."""
        required = {
            "SerialResult", "ParseResult", "SerialSession",
            "connect", "cli", "run", "stream", "parse",
            "save_default", "load_defaults",
            "DEFAULT_TIMEOUT", "DEFAULT_BAUD", "DEFAULT_DEVICE",
        }
        self.assertTrue(required.issubset(set(sdev.__all__)))


class TestDisconnect(unittest.TestCase):
    """Verify disconnect() module-level helper."""

    def test_disconnect_closes_default_session(self):
        """disconnect() should call close() on the default session."""
        sess = sdev.SerialSession()
        mock_close = MagicMock()
        sess.close = mock_close

        with patch.object(sdev, "_default_session", sess):
            sdev.disconnect()

        mock_close.assert_called_once()

    def test_disconnect_on_already_closed_is_safe(self):
        """Calling disconnect() when nothing is open should not raise."""
        sess = sdev.SerialSession()
        # _connection is None by default — close() should be a no-op
        sdev.disconnect()  # should not raise

    def test_disconnect_then_ensure_raises(self):
        """After disconnect(), ensure_connection() should raise."""
        mock_sess = MagicMock()
        mock_sess.is_open = True
        mock_sess.close = MagicMock()

        def fake_ensure_open():
            if not mock_sess.is_open:
                raise RuntimeError("Not connected")
            return MagicMock()

        mock_sess._ensure_open = fake_ensure_open

        with patch.object(sdev, "_default_session", mock_sess):
            sdev.disconnect()
            mock_sess.close.assert_called_once()
            mock_sess.is_open = False
            with self.assertRaises(RuntimeError):
                sdev.ensure_connection()

    def test_disconnect_not_in_all_must_be_present(self):
        """disconnect must be listed in __all__ since it's a public helper."""
        self.assertIn("disconnect", sdev.__all__)


if __name__ == "__main__":
    unittest.main()
