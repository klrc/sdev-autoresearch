"""Adversarial edge-case tests for the sdev public API surface.

Owned by the test role — covers parse(), module-level API contracts,
timeout propagation, and SerialSession re-connect behavior that dev's
own tests don't exercise.
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import sdev


class TestParseResult(unittest.TestCase):
    def test_parse_result_defaults(self):
        r = sdev.ParseResult()
        self.assertEqual(r.lines, [])
        self.assertEqual(r.matched, [])
        self.assertEqual(r.raw, "")


class TestSerialSessionConnectReconnect(unittest.TestCase):
    def test_connect_reconnect_reuses_session(self):
        session = sdev.SerialSession()
        call_count = [0]
        def make_serial(*a, **kw):
            call_count[0] += 1
            m = MagicMock()
            m.is_open = True
            return m
        with patch("sdev.serial.Serial", side_effect=make_serial):
            session.connect()
            first = session._connection
            # Second connect should close the first and open a new one
            session.connect()
            second = session._connection
            self.assertIsNot(first, second)
            first.close.assert_called_once()

    def test_connect_after_close_can_reopen(self):
        session = sdev.SerialSession()
        with patch("sdev.serial.Serial") as MockSerial:
            MockSerial.return_value.is_open = True
            session.connect()
            self.assertTrue(session.is_open)
            session.close()
            self.assertFalse(session.is_open)
            session.connect()
            self.assertTrue(session.is_open)


class TestModuleLevelAPIDelegation(unittest.TestCase):
    def test_module_cli_delegates_to_default_session(self):
        mock_result = sdev.SerialResult("echo hi", "hi\n", False, 0.1)
        with patch.object(sdev, "_default_session") as mock_sess:
            mock_sess.cli.return_value = mock_result
            result = sdev.cli("echo hi")
            mock_sess.cli.assert_called_once_with("echo hi", None, None)
            self.assertEqual(result.output, "hi\n")

    def test_module_stream_delegates(self):
        with patch.object(sdev, "_default_session") as mock_sess:
            mock_sess.stream.return_value = iter(["a", "b"])
            chunks = list(sdev.stream("echo ab"))
            mock_sess.stream.assert_called_once_with("echo ab", None, 256, None, False, None)
            self.assertEqual(chunks, ["a", "b"])

    def test_module_interrupt_delegates(self):
        with patch.object(sdev, "_default_session") as mock_sess:
            sdev.interrupt()
            mock_sess.interrupt.assert_called_once()


class TestCLITimeoutPropagation(unittest.TestCase):
    def test_cli_passes_timeout_to_session(self):
        session = sdev.SerialSession()
        with patch.object(session, "_ensure_open") as mock_ensure, \
             patch("sdev.time.monotonic", side_effect=[0, 5.1, 5.1]):
            mock_ser = MagicMock()
            mock_ser.read.return_value = b""
            mock_ensure.return_value = mock_ser
            result = session.cli("cmd", timeout=5.0)
            self.assertTrue(result.timed_out)

    def test_stream_timeout_stops_iteration(self):
        session = sdev.SerialSession()
        with patch.object(session, "_ensure_open") as mock_ensure, \
             patch("sdev.time.monotonic", side_effect=[0, 11.0, 11.0]):
            mock_ser = MagicMock()
            mock_ser.read.return_value = b""
            mock_ensure.return_value = mock_ser
            chunks = list(session.stream("cmd", timeout=10.0))
            self.assertEqual(chunks, [])

    def test_parse_passes_timeout_through_cli(self):
        session = sdev.SerialSession()
        with patch.object(session, "cli") as mock_cli:
            mock_cli.return_value = sdev.SerialResult("cmd", "line1\nline2\n", False, 0.1)
            session.parse("cmd", timeout=42.0)
            mock_cli.assert_called_once_with("cmd", 42.0)


class TestAllExportsAccessible(unittest.TestCase):
    def test_all_names_exist_on_module(self):
        for name in sdev.__all__:
            self.assertTrue(hasattr(sdev, name), f"{name!r} in __all__ but not on module")


if __name__ == "__main__":
    unittest.main()
