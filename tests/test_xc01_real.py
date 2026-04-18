"""Real-hardware tests against XC01 (MC6357) board (issue #30).

These tests require an actual serial device at /dev/ttyUSB0 (or the
configured device).  They are skipped when the device is unavailable
so CI / mocked environments still pass.

Only safe, bounded commands are used — no benchmarks, no writes to
/sys, no module loading/unloading.
"""

import os
import unittest
from unittest.mock import patch

import sdev

DEVICE = os.environ.get("SDEV_TEST_DEVICE", "/dev/ttyUSB0")
BAUD = int(os.environ.get("SDEV_TEST_BAUD", "115200"))


def _device_available() -> bool:
    """Return True if the serial device path exists on disk."""
    return os.path.exists(DEVICE)


def _skip_if_no_device(test_case):
    """Decorator: skip test when serial device is not available."""
    return unittest.skipUnless(
        _device_available(),
        f"Serial device {DEVICE} not available",
    )(test_case)


@_skip_if_no_device
class TestXC01Basic(unittest.TestCase):
    """Basic read-only commands that should always succeed on a running Linux."""

    def _session(self):
        sess = sdev.SerialSession(DEVICE, BAUD)
        sess.connect()
        return sess

    def test_echo_roundtrip(self):
        """echo should return the exact string we send."""
        with self._session() as sess:
            sess.doctor()
            result = sess.cli("echo hello-sdev")
            self.assertIn("hello-sdev", result.output)
            self.assertFalse(result.timed_out)

    def test_uptime_returns_output(self):
        """uptime should produce output with a time and load average."""
        with self._session() as sess:
            sess.doctor()
            result = sess.cli("uptime")
            self.assertTrue(result.output.strip())
            # Uptime output typically contains "up" and load averages
            self.assertIn("up", result.output.lower())

    def test_meminfo_contains_total(self):
        """cat /proc/meminfo should contain MemTotal line."""
        with self._session() as sess:
            sess.doctor()
            result = sess.cli("cat /proc/meminfo")
            self.assertIn("MemTotal", result.output)
            self.assertFalse(result.timed_out)

    def test_cpuinfo_contains_hardware(self):
        """cat /proc/cpuinfo should contain hardware information."""
        with self._session() as sess:
            sess.doctor()
            result = sess.cli("cat /proc/cpuinfo")
            self.assertTrue(result.output.strip())
            self.assertIn("processor", result.output.lower())

    def test_free_shows_memory(self):
        """free should show memory usage."""
        with self._session() as sess:
            sess.doctor()
            result = sess.cli("free")
            self.assertIn("Mem", result.output)
            self.assertFalse(result.timed_out)

    def test_stream_line_mode_yields_complete_lines(self):
        """stream(line_mode=True) should yield complete lines from dmesg."""
        with self._session() as sess:
            sess.doctor()
            lines = list(sess.stream("dmesg | head -5", line_mode=True, timeout=10))
            self.assertGreater(len(lines), 0)
            # Every yielded line should end with \n
            for line in lines:
                self.assertTrue(line.endswith("\n"), f"Line does not end with \\n: {line!r}")

    def test_end_flag_stops_on_marker(self):
        """cli() with end_flag should stop when the flag appears."""
        with self._session() as sess:
            sess.doctor()
            # Use echo to produce the marker ourselves
            result = sess.cli(
                "echo 'START'; echo 'MARKER: done'; echo 'after'",
                end_flag="MARKER:",
            )
            self.assertIn("MARKER: done", result.output)
            # "after" may or may not appear depending on timing — the key
            # is that we stopped promptly after seeing MARKER:
            self.assertFalse(result.timed_out)

    def test_recover_after_interrupt(self):
        """After sending Ctrl+C, a subsequent command should still work."""
        with self._session() as sess:
            sess.doctor()
            # Send a harmless interrupt
            sess.interrupt(timeout=2)
            # Then run a normal command
            result = sess.cli("echo recovered")
            self.assertIn("recovered", result.output)

    def test_write_raw_bytes(self):
        """write() should send raw bytes and be followed by cli() output."""
        with self._session() as sess:
            sess.doctor()
            n = sess.write(b"echo raw-write-test\n")
            self.assertGreater(n, 0)
            # Follow up with a cli() to verify session is still functional
            result = sess.cli("echo after-write")
            self.assertIn("after-write", result.output)


if __name__ == "__main__":
    unittest.main()
