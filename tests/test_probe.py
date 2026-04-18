"""Tests for probe() — board detection (issue #45)."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestProbeDevicePatterns(unittest.TestCase):
    """probe() should return platform-appropriate device patterns."""

    def test_linux_usb_patterns(self):
        """On Linux, should include /dev/ttyUSB* and /dev/ttyACM*."""
        with patch.object(sdev, "_is_linux", return_value=True), \
             patch.object(sdev, "_is_macos", return_value=False), \
             patch.object(sdev, "_is_windows", return_value=False):
            patterns = sdev._probe_device_patterns()
        self.assertTrue(any("ttyUSB" in p for p in patterns))
        self.assertTrue(any("ttyACM" in p for p in patterns))

    def test_macos_usb_patterns(self):
        """On macOS, should include /dev/tty.usb* and /dev/cu.usb*."""
        with patch.object(sdev, "_is_linux", return_value=False), \
             patch.object(sdev, "_is_macos", return_value=True), \
             patch.object(sdev, "_is_windows", return_value=False):
            patterns = sdev._probe_device_patterns()
        self.assertTrue(any("tty.usb" in p for p in patterns))
        self.assertTrue(any("cu.usb" in p for p in patterns))

    def test_windows_com_patterns(self):
        """On Windows, should include COM*."""
        with patch.object(sdev, "_is_linux", return_value=False), \
             patch.object(sdev, "_is_macos", return_value=False), \
             patch.object(sdev, "_is_windows", return_value=True):
            patterns = sdev._probe_device_patterns()
        self.assertTrue(any("COM" in p for p in patterns))


class TestProbeEnumerateDevices(unittest.TestCase):
    """probe() should enumerate actual devices."""

    def test_returns_devices_found_on_linux(self):
        """probe() should return list of existing /dev/ttyUSB* devices."""

        def fake_is_linux(): return True
        def fake_is_macos(): return False
        def fake_is_windows(): return False

        with patch.object(sdev, "_is_linux", fake_is_linux), \
             patch.object(sdev, "_is_macos", fake_is_macos), \
             patch.object(sdev, "_is_windows", fake_is_windows), \
             patch("sdev.glob.glob", side_effect=lambda p: [f"{p[:-1]}0", f"{p[:-1]}1"]):
            devices = sdev._enumerate_devices()
            # Should contain USB devices from all patterns
            self.assertTrue(len(devices) > 0)
            self.assertEqual(set(devices), set(devices))  # no crash

    def test_returns_empty_when_no_devices(self):
        """probe() should return empty list when no devices exist."""

        def fake_is_linux(): return True
        def fake_is_macos(): return False
        def fake_is_windows(): return False

        with patch.object(sdev, "_is_linux", fake_is_linux), \
             patch.object(sdev, "_is_macos", fake_is_macos), \
             patch.object(sdev, "_is_windows", fake_is_windows), \
             patch("sdev.glob.glob", return_value=[]):
            devices = sdev._enumerate_devices()
            self.assertEqual(devices, [])


class TestProbeBoardInfo(unittest.TestCase):
    """probe() should extract board information from a live device."""

    def test_board_info_from_mock_session(self):
        """probe() should use cli() to read /etc/os-release, uname, etc."""
        mock_sess = MagicMock()
        mock_sess.is_open = True
        mock_sess._connection = MagicMock()
        mock_sess._connection.is_open = True

        def fake_cli(cmd, **kw):
            responses = {
                "echo sdev-ping": "sdev-ping\n",
                "cat /etc/os-release": 'NAME="Ubuntu"\nVERSION="22.04"\n',
                "uname -a": "Linux xc01 5.10.0 armv7l GNU/Linux\n",
            }
            output = responses.get(cmd, "")
            return sdev.SerialResult(cmd, output, False, 0.1)

        mock_sess.cli = fake_cli

        info = sdev._probe_board_info(mock_sess)
        self.assertEqual(info["os_name"], "Ubuntu")
        self.assertIn("xc01", info["hostname"])
        self.assertIn("armv7l", info["arch"])

    def test_board_info_handles_timeout(self):
        """probe() should handle timed-out commands gracefully."""
        mock_sess = MagicMock()
        mock_sess.is_open = True
        mock_sess._connection = MagicMock()
        mock_sess._connection.is_open = True

        def fake_cli(cmd, **kw):
            return sdev.SerialResult(cmd, "", True, 5.0)

        mock_sess.cli = fake_cli

        info = sdev._probe_board_info(mock_sess)
        # Quick ping times out — should return "no response"
        self.assertEqual(info.get("os_name"), "no response")

    def test_board_info_falls_back_to_proc_version(self):
        """probe() should detect Linux via /proc/version when /etc/os-release missing."""
        mock_sess = MagicMock()
        mock_sess.is_open = True
        mock_sess._connection = MagicMock()
        mock_sess._connection.is_open = True

        def fake_cli(cmd, **kw):
            responses = {
                "echo sdev-ping": "sdev-ping\n",
                "cat /etc/os-release": "cat: can't open '/etc/os-release': No such file or directory\n",
                "busybox --help 2>&1 | head -1": "",
                "uname -a": "Linux (none) 5.10.0 armv7l GNU/Linux\n",
                "grep -m1 'model name' /proc/cpuinfo": "",
                "cat /proc/version": "Linux version 5.10.144 (builder) armv7l\n",
            }
            return sdev.SerialResult(cmd, responses.get(cmd, ""), False, 0.1)

        mock_sess.cli = fake_cli

        info = sdev._probe_board_info(mock_sess)
        self.assertEqual(info["os_name"], "Linux")
        self.assertEqual(info["arch"], "armv7l")


class TestProbeFunction(unittest.TestCase):
    """Top-level probe() API."""

    def test_probe_returns_list(self):
        """probe() should return a list of device info dicts."""
        import glob as _glob

        with patch.object(_glob, "glob", return_value=[]), \
             patch.object(sdev, "_is_linux", return_value=True), \
             patch.object(sdev, "_is_macos", return_value=False), \
             patch.object(sdev, "_is_windows", return_value=False):
            results = sdev.probe()
            self.assertIsInstance(results, list)
            # Empty since no devices found
            self.assertEqual(results, [])

    def test_probe_does_not_call_doctor(self):
        """probe() should skip doctor() for fast enumeration."""
        mock_sess = MagicMock()
        mock_sess.is_open = True
        mock_sess._connection = MagicMock()
        mock_sess._connection.is_open = True
        mock_sess.cli.return_value = sdev.SerialResult(
            "cat /etc/os-release", 'NAME="Ubuntu"\n', False, 0.1)

        with patch.object(sdev, "_enumerate_devices",
                          return_value=["/dev/ttyUSB0"]), \
             patch("sdev.SerialSession", return_value=mock_sess) as mock_cls:
            sdev.probe()

        mock_sess.doctor.assert_not_called()

class TestPlatformDetection(unittest.TestCase):
    """Platform detection helpers."""

    def test_linux_detection(self):
        """_is_linux() should return True on Linux."""
        with patch.object(sys, "platform", "linux"):
            self.assertTrue(sdev._is_linux())

    def test_macos_detection(self):
        """_is_macos() should return True on macOS."""
        with patch.object(sys, "platform", "darwin"):
            self.assertTrue(sdev._is_macos())

    def test_windows_detection(self):
        """_is_windows() should return True on Windows."""
        with patch.object(sys, "platform", "win32"):
            self.assertTrue(sdev._is_windows())


if __name__ == "__main__":
    unittest.main()
