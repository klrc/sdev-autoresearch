"""Adversarial tests for error handling, exception propagation, and edge cases.

Tests paths that don't occur in normal operation but could be triggered
by misconfiguration, unexpected serial behavior, or concurrent misuse.
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import sdev


class TestFilterFnExceptionPropagation(unittest.TestCase):
    """Verify filter_fn exceptions propagate through stream() properly."""

    def test_filter_fn_exception_propagates(self):
        """If filter_fn raises, stream() should propagate the exception."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"hello\n", b"# "]

        def bad_filter(text):
            raise ValueError("filter broke")

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        it = sess.stream("cmd", filter_fn=bad_filter)
        with self.assertRaises(ValueError) as ctx:
            list(it)
        self.assertEqual(str(ctx.exception), "filter broke")

    def test_filter_fn_exception_releases_lock(self):
        """After filter_fn raises, the lock must be released."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"hello\n", b"# "]

        def bad_filter(text):
            raise ValueError("filter broke")

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        it = sess.stream("cmd", filter_fn=bad_filter)
        with self.assertRaises(ValueError):
            list(it)

        # Lock should be released — acquire should succeed
        acquired = sess._lock.acquire(timeout=1)
        self.assertTrue(acquired)
        sess._lock.release()


class TestSerialExceptionDuringCli(unittest.TestCase):
    """Serial error during cli() should return a clean result, not raise."""

    def test_serial_error_returns_result_with_error_message(self):
        """cli() should catch SerialException and return error output."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = sdev.serial.SerialException("device lost")

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("cmd", timeout=5)
        self.assertTrue(result.timed_out)
        self.assertIn("serial error", result.output)
        self.assertIn("device lost", result.output)


class TestStreamSerialExceptionRecovery(unittest.TestCase):
    """Serial error during stream() should stop iteration, not crash."""

    def test_stream_stops_on_serial_error(self):
        """stream() should catch SerialException and stop."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"line1\n", sdev.serial.SerialException("disconnect")]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("cmd", timeout=5))
        # Should have gotten line1 before the error
        self.assertIn("line1", "".join(chunks))

    def test_stream_releases_lock_on_error(self):
        """Lock must be released even when stream() hits an error."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = sdev.serial.SerialException("disconnect")

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        list(sess.stream("cmd", timeout=5))

        acquired = sess._lock.acquire(timeout=1)
        self.assertTrue(acquired)
        sess._lock.release()


class TestEnsureOpenRaisesWhenNotConnected(unittest.TestCase):
    """_ensure_open() should raise with clear message when not connected."""

    def test_ensure_open_raises_with_device_info(self):
        """Error message should include device/baud for debugging."""
        sess = sdev.SerialSession("/dev/ttyS99", 9600)
        with self.assertRaises(RuntimeError) as ctx:
            sess._ensure_open()
        self.assertIn("/dev/ttyS99", str(ctx.exception))
        self.assertIn("9600", str(ctx.exception))


class TestConnectSerialException(unittest.TestCase):
    """connect() should wrap SerialException in RuntimeError."""

    def test_connect_wraps_exception(self):
        """connect() should raise RuntimeError with device info."""
        with patch("sdev.serial.Serial") as mock_cls:
            mock_cls.side_effect = sdev.serial.SerialException(
                "[Errno 2] No such file")
            sess = sdev.SerialSession("/dev/ttyNOPE", 115200)
            with self.assertRaises(RuntimeError) as ctx:
                sess.connect()
            self.assertIn("/dev/ttyNOPE", str(ctx.exception))
            self.assertIsNone(sess._connection)


class TestCloseIsSafeWhenAlreadyClosed(unittest.TestCase):
    """close() should be safe to call multiple times."""

    def test_close_when_not_connected(self):
        """close() on an unconnected session should not raise."""
        sess = sdev.SerialSession()
        sess.close()  # should not raise
        sess.close()  # twice either

    def test_close_when_connection_already_closed(self):
        """close() should handle already-closed serial port."""
        mock_ser = MagicMock()
        mock_ser.is_open = False
        mock_ser.close.side_effect = sdev.serial.SerialException("already closed")

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        sess.close()  # should not raise
        self.assertIsNone(sess._connection)


class TestLockConcurrency(unittest.TestCase):
    """Lock behavior under concurrent access."""

    def test_two_sessions_have_independent_locks(self):
        """Two SerialSession instances should have independent locks."""
        s1 = sdev.SerialSession()
        s2 = sdev.SerialSession()
        self.assertIsNot(s1._lock, s2._lock)

    def test_lock_acquire_timeout_returns_false_when_held(self):
        """Lock should return False when held for longer than timeout."""
        sess = sdev.SerialSession()
        sess._lock.acquire()

        # Second acquire should fail with short timeout
        import threading
        result = [None]

        def try_lock():
            result[0] = sess._lock.acquire(timeout=0.1)

        t = threading.Thread(target=try_lock)
        t.start()
        t.join(timeout=2)
        self.assertFalse(result[0])
        sess._lock.release()


class TestInterruptDoesNotAcquireLock(unittest.TestCase):
    """interrupt() must not acquire the lock — it's the emergency escape."""

    def test_interrupt_does_not_acquire_lock(self):
        """interrupt() should work even when lock is held."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"# "]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        # Hold the lock
        sess._lock.acquire()
        try:
            # interrupt should still work (doesn't acquire lock)
            ok = sess.interrupt(timeout=0.1)
            # It may or may not detect prompt depending on mock data
            # The key is it didn't hang
        finally:
            sess._lock.release()


class TestCliImplTimeoutInterruptCalled(unittest.TestCase):
    """cli() should call interrupt() on timeout to clean up."""

    def test_cli_calls_interrupt_on_timeout(self):
        """cli() should attempt interrupt when timeout elapses."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        with patch.object(sess, "interrupt", return_value=False) as mock_int:
            result = sess.cli("long_cmd", timeout=0.001)
            self.assertTrue(result.timed_out)
            mock_int.assert_called_once_with(timeout=0.5)


class TestStreamEndFlagStopsOutput(unittest.TestCase):
    """end_flag in stream() should stop iteration when marker appears."""

    def test_stream_stops_at_end_flag(self):
        """stream() should stop yielding after end_flag appears."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"running...\n",
            b"Frame rate: 60fps\n",
            b"still running...\n",  # should not be reached
            b"# ",
        ]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("./bench", end_flag="Frame rate:"))
        combined = "".join(chunks)
        self.assertIn("Frame rate: 60fps", combined)
        self.assertNotIn("still running", combined)


class TestCLILargeOutputNoMemoryLeak(unittest.TestCase):
    """cli() with large output should not grow buffer unboundedly."""

    def test_cli_trims_buffer(self):
        """cli() should trim buffer if it exceeds MAX_BUFFER_SIZE."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        # Send a response larger than MAX_BUFFER_SIZE (64KB)
        big = b"A" * (65536 + 100)
        chunks = [big[i:i+4096] for i in range(0, len(big), 4096)]
        chunks.append(b"# ")  # prompt at end
        mock_ser.read.side_effect = chunks

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("big_output", timeout=30)
        self.assertFalse(result.timed_out)
        # Buffer should have been trimmed — output should not contain
        # all 65636 bytes of A's
        self.assertLess(len(result.output), sdev.MAX_BUFFER_SIZE)


class TestParseWithNoPattern(unittest.TestCase):
    """parse() without pattern should return all lines."""

    def test_parse_without_pattern(self):
        """parse() should return all non-empty lines when no pattern."""
        mock_sess = MagicMock()
        mock_sess.cli.return_value = sdev.SerialResult(
            "cmd", "line1\nline2\n\nline3\n", False, 0.1)

        sess = sdev.SerialSession()
        with patch.object(sess, "cli", mock_sess.cli):
            result = sess.parse("cmd")

        self.assertEqual(result.lines, ["line1", "line2", "line3"])
        self.assertEqual(result.matched, [])


class TestPromptDetectionEdgeCases(unittest.TestCase):
    """Prompt detection should handle tricky buffer states."""

    def test_prompt_in_middle_of_buffer(self):
        """Prompt detection should work even when prompt isn't at very end."""
        sess = sdev.SerialSession()
        # Prompt not at end — should not match
        self.assertFalse(sess._check_prompt(b"output # \nmore"))
        # Prompt at end after newline strip — should match
        self.assertTrue(sess._check_prompt(b"output # \n"))

    def test_empty_buffer_no_prompt(self):
        """_check_prompt on empty buffer should return False."""
        sess = sdev.SerialSession()
        self.assertFalse(sess._check_prompt(b""))

    def test_ansi_stripped_from_output(self):
        """ANSI sequences should be stripped from cli() output."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        # Response with ANSI color code, followed by plain prompt
        response = b"\x1b[01;32mhello\x1b[0m\r\n# "
        mock_ser.read.side_effect = [response]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("cmd", timeout=1)
        self.assertFalse(result.timed_out)
        # The ANSI should be stripped from output
        self.assertNotIn("\x1b[", result.output)
        self.assertIn("hello", result.output)


class TestModuleLevelRunWithEndFlag(unittest.TestCase):
    """sdev.run() should support end_flag parameter."""

    def test_run_has_end_flag(self):
        """run() should accept end_flag parameter."""
        import inspect
        sig = inspect.signature(sdev.run)
        params = list(sig.parameters.keys())
        self.assertIn("end_flag", params)

    def test_run_passes_end_flag(self):
        """run() should pass end_flag to session.cli()."""
        with patch.object(sdev, "SerialSession") as mock_cls:
            mock_sess = MagicMock()
            mock_sess.cli.return_value = sdev.SerialResult(
                "bench", "Frame rate: 60\n", False, 1.0)
            mock_cls.return_value = mock_sess

            result = sdev.run("/dev/ttyUSB0", 115200, "bench",
                              end_flag="Frame rate:")

            mock_sess.cli.assert_called_once_with(
                "bench", None, "Frame rate:")
            self.assertFalse(result.timed_out)


if __name__ == "__main__":
    unittest.main()
