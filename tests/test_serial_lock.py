"""Tests for serial session thread safety (issue #29)."""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestSerialLock(unittest.TestCase):
    def test_lock_exists_on_session(self):
        sess = sdev.SerialSession()
        self.assertIsInstance(sess._lock, type(threading.Lock()))

    def test_concurrent_cli_blocks_second_caller(self):
        """Second cli() should raise RuntimeError if first is still holding lock."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        # Return empty bytes but sleep long enough to hold the lock
        def slow_read(*a):
            time.sleep(10)
            return b""
        mock_ser.read.side_effect = slow_read

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        results = {"error": None}

        def first_call():
            try:
                sess.cli("cmd1", timeout=5)
            except Exception as e:
                results["first_error"] = str(e)

        def second_call():
            try:
                sess.cli("cmd2", timeout=1)
            except RuntimeError as e:
                results["error"] = str(e)

        t1 = threading.Thread(target=first_call)
        t1.start()
        time.sleep(0.5)  # let t1 acquire the lock and enter the loop

        t2 = threading.Thread(target=second_call)
        t2.start()
        t2.join(timeout=12)

        # t2 should have failed with RuntimeError (lock timeout after 10s)
        self.assertIn("busy", (results.get("error") or "").lower())
        # t1 will finish after its 5s timeout
        t1.join(timeout=8)

    def test_lock_released_after_cli_returns(self):
        """After cli() returns, lock should be available again."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"ok\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        sess.cli("cmd", timeout=1)

        acquired = sess._lock.acquire(timeout=0.5)
        self.assertTrue(acquired)
        sess._lock.release()

    def test_lock_released_after_stream_exhausted(self):
        """After stream() generator is fully consumed, lock should be released."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"chunk\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        chunks = list(sess.stream("cmd", timeout=1))
        self.assertTrue(chunks)

        acquired = sess._lock.acquire(timeout=0.5)
        self.assertTrue(acquired)
        sess._lock.release()

    def test_interrupt_does_not_require_lock(self):
        """interrupt() must work even when cli() holds the lock."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"", b"# "]

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        sess._lock.acquire()  # simulate held lock

        result = sess.interrupt(timeout=0.5)
        self.assertIsInstance(result, bool)
        sess._lock.release()

    def test_sequential_cli_works(self):
        """Sequential cli() calls should work normally."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"one\n# ", b"two\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        r1 = sess.cli("cmd1", timeout=1)
        r2 = sess.cli("cmd2", timeout=1)
        self.assertIn("one", r1.output)
        self.assertIn("two", r2.output)


if __name__ == "__main__":
    unittest.main()
