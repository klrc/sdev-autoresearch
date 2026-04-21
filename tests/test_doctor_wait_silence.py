"""Tests for module-level doctor(), wait_for_silence(), and --doctor-only CLI."""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestModuleLevelDoctor(unittest.TestCase):
    """sdev.doctor() should delegate to default session."""

    def test_doctor_delegates(self):
        """sdev.doctor() should call _default_session.doctor()."""
        with patch.object(sdev, "_default_session") as mock_sess:
            sdev.doctor(timeout=5)
            mock_sess.doctor.assert_called_once_with(5)

    def test_doctor_default_timeout(self):
        """sdev.doctor() should use default timeout of 10 if not specified."""
        with patch.object(sdev, "_default_session") as mock_sess:
            sdev.doctor()
            mock_sess.doctor.assert_called_once_with(10)


class TestModuleLevelWaitForSilence(unittest.TestCase):
    """sdev.wait_for_silence() should delegate to default session."""

    def test_wait_for_silence_delegates(self):
        """sdev.wait_for_silence() should call _default_session.wait_for_silence()."""
        with patch.object(sdev, "_default_session") as mock_sess:
            sdev.wait_for_silence(timeout=3.0)
            mock_sess.wait_for_silence.assert_called_once_with(3.0)

    def test_wait_for_silence_default_timeout(self):
        """sdev.wait_for_silence() should use default timeout of 1.5 if not specified."""
        with patch.object(sdev, "_default_session") as mock_sess:
            sdev.wait_for_silence()
            mock_sess.wait_for_silence.assert_called_once_with(1.5)


class TestDoctorOnlyCLI(unittest.TestCase):
    """CLI --doctor-only flag should run doctor and exit."""

    def setUp(self):
        # Clear cached module so we get fresh import for each test
        import sys
        self._saved = sys.modules.pop("sdev.__main__", None)

    def tearDown(self):
        import sys
        if self._saved:
            sys.modules["sdev.__main__"] = self._saved

    def test_doctor_only_runs_doctor(self):
        """--doctor-only should call doctor() and not run a command."""
        mock_sess = MagicMock()
        mock_sess.__enter__ = MagicMock(return_value=mock_sess)
        mock_sess.__exit__ = MagicMock(return_value=False)

        with patch("sys.argv", ["sdev", "--doctor-only",
                                "-d", "/dev/ttyUSB0", "-b", "115200"]), \
             patch("sdev.SerialSession", return_value=mock_sess):
            from sdev.__main__ import main
            main()

        mock_sess.doctor.assert_called_once()

    def test_doctor_only_uses_defaults(self):
        """--doctor-only should use saved defaults if -d/-b not provided."""
        mock_sess = MagicMock()
        mock_sess.__enter__ = MagicMock(return_value=mock_sess)
        mock_sess.__exit__ = MagicMock(return_value=False)

        with patch("sdev.load_defaults", return_value={
                "device": "/dev/ttyUSB1", "baud": 9600}), \
             patch("sys.argv", ["sdev", "--doctor-only"]), \
             patch("sdev.SerialSession", return_value=mock_sess):
            from sdev.__main__ import main
            main()

        mock_sess.doctor.assert_called_once()


if __name__ == "__main__":
    unittest.main()
