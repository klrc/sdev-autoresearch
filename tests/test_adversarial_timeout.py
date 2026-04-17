"""Adversarial tests for CLI timeout and stream buffer trimming — test-owned coverage."""

import unittest
from unittest.mock import MagicMock

import sdev


class TestCLITimeoutOverride(unittest.TestCase):
    """Verify --timeout flag propagates to session methods."""

    def test_cli_timeout_override(self):
        """cli() should use caller's timeout, not DEFAULT_TIMEOUT."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("sleep 999", timeout=0.2)
        self.assertTrue(result.timed_out)
        self.assertLess(result.elapsed, 1.0)


class TestStreamBufferTrimming(unittest.TestCase):
    """Guards for buffer trimming logic in stream()."""

    def test_trim_bug_echo_skip_after_trim(self):
        """BUG: after buffer trim, echo_skip adjustment is a no-op.

        In the stream() method, the trim code does:
            if consumed > 65536:
                buf = buf[consumed:]
                consumed = 0                    # reset FIRST
                echo_skip = max(0, echo_skip - consumed)  # uses 0, not old consumed!

        This means echo_skip is never reduced, so after a trim the
        stream will continue skipping the wrong number of leading bytes,
        dropping real output.
        """
        mock_ser = MagicMock()
        mock_ser.is_open = True

        # Build a response that exceeds 65KB after echo is stripped
        big_payload = b"X" * 70000
        response = b"echo big_cmd\n" + big_payload + b"\n# "

        mock_ser.read.side_effect = [response[i:i+4096] for i in range(0, len(response), 4096)]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("echo big_cmd"))
        combined = "".join(chunks)

        # All payload bytes should be present
        self.assertEqual(combined.count("X"), 70000,
            f"Expected 70000 X's, got {combined.count('X')} — "
            "buffer trim corrupted echo_skip, dropping data")


class TestStreamTimeoutWithTrim(unittest.TestCase):
    """Stream timeout still works with trimming code present."""

    def test_stream_timeout_no_data(self):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("idle", timeout=0.2))
        self.assertEqual(chunks, [])


class TestCLIEntrypointTimeout(unittest.TestCase):
    """Verify CLI entry point passes timeout to all three modes."""

    def test_normal_mode_timeout(self):
        """Normal mode passes timeout to cli()."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        from sdev.__main__ import main
        import io
        captured = io.StringIO()

        with unittest.mock.patch("sdev.SerialSession") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess.is_open = True
            mock_sess_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_sess.cli.return_value = sdev.SerialResult(
                "echo ok", "ok\n", False, 0.1)

            with unittest.mock.patch("sys.argv",
                    ["sdev", "-p", "echo ok", "-t", "0.5",
                     "-d", "/dev/ttyS0", "-b", "9600"]), \
                 unittest.mock.patch("sys.stdout", captured), \
                 unittest.mock.patch("sdev.serial.Serial", return_value=mock_ser):
                main()

            mock_sess.cli.assert_called_once_with("echo ok", timeout=0.5)

    def test_stream_mode_timeout(self):
        """Stream mode passes timeout to stream()."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"chunk\n# ", b""]

        from sdev.__main__ import main
        import io
        captured = io.StringIO()

        with unittest.mock.patch("sdev.SerialSession") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess.is_open = True
            mock_sess_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_sess.stream.return_value = ["chunk\n"]

            with unittest.mock.patch("sys.argv",
                    ["sdev", "-p", "echo ok", "--stream", "-t", "10",
                     "-d", "/dev/ttyS0", "-b", "9600"]), \
                 unittest.mock.patch("sys.stdout", captured), \
                 unittest.mock.patch("sdev.serial.Serial", return_value=mock_ser):
                main()

            mock_sess.stream.assert_called_once_with(
                "echo ok", timeout=10.0, filter_fn=None)

    def test_parse_mode_timeout(self):
        """Parse mode passes timeout to parse()."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"MemTotal: 1000\n# ", b""]

        from sdev.__main__ import main
        import io
        captured = io.StringIO()

        with unittest.mock.patch("sdev.SerialSession") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess.is_open = True
            mock_sess_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_sess.parse.return_value = sdev.ParseResult(
                lines=["MemTotal: 1000"], matched=["MemTotal: 1000"],
                raw="MemTotal: 1000\n# ")

            with unittest.mock.patch("sys.argv",
                    ["sdev", "-p", "cat /proc/meminfo", "--parse", "MemTotal",
                     "-t", "20", "-d", "/dev/ttyS0", "-b", "9600"]), \
                 unittest.mock.patch("sys.stdout", captured), \
                 unittest.mock.patch("sdev.serial.Serial", return_value=mock_ser):
                main()

            mock_sess.parse.assert_called_once_with(
                "cat /proc/meminfo", pattern="MemTotal", timeout=20.0)


if __name__ == "__main__":
    unittest.main()
