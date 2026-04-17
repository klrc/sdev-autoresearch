"""Adversarial tests for custom prompts, reconnect, and timeout interrupt — test-owned coverage."""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestCustomPrompts(unittest.TestCase):
    """Verify SerialSession accepts and uses custom prompts."""

    def test_custom_prompts_in_init(self):
        """SerialSession should accept custom prompts list."""
        custom = [b"[root@board]# ", b"# "]
        sess = sdev.SerialSession(prompts=custom)
        self.assertEqual(sess.prompts, custom)

    def test_default_prompts_fallback(self):
        """SerialSession should use PROMPTS when no custom list given."""
        sess = sdev.SerialSession()
        self.assertEqual(sess.prompts, list(sdev.PROMPTS))

    def test_custom_prompt_detected(self):
        """_check_prompt should match custom prompts."""
        custom = [b"[root@board]# ", b"(env) $ "]
        sess = sdev.SerialSession(prompts=custom)
        self.assertTrue(sess._check_prompt(b"some output [root@board]# "))
        self.assertTrue(sess._check_prompt(b"(env) $ "))
        self.assertFalse(sess._check_prompt(b"$ "))

    def test_prompts_property_returns_copy(self):
        """prompts property should return a copy, not the internal list."""
        custom = [b"# "]
        sess = sdev.SerialSession(prompts=custom)
        result = sess.prompts
        result.append(b"$ ")
        self.assertNotIn(b"$ ", sess.prompts)

    def test_cli_uses_custom_prompts(self):
        """cli() should stop when custom prompt appears."""
        sess = sdev.SerialSession(prompts=[b"custom# "])
        mock_ser = MagicMock()
        sess._connection = mock_ser
        mock_ser.read.side_effect = [b"output\r\ncustom# "]

        result = sess.cli("test", timeout=1)
        self.assertFalse(result.timed_out)
        self.assertIn("output", result.output)

    def test_stream_uses_custom_prompts(self):
        """stream() should detect custom prompts and stop."""
        sess = sdev.SerialSession(prompts=[b"[custom]$ "])
        mock_ser = MagicMock()
        sess._connection = mock_ser
        mock_ser.read.side_effect = [b"line1\r\nline2\r\n[custom]$ "]

        chunks = list(sess.stream("test", timeout=1))
        self.assertEqual("".join(chunks).strip(), "line1\r\nline2")


class TestReconnect(unittest.TestCase):
    """Verify SerialSession.reconnect() recovers from stale connections."""

    def test_reconnect_when_not_connected(self):
        """reconnect() should work even without prior connection."""
        with patch.object(sdev.serial, "Serial") as mock_cls:
            mock_ser = MagicMock()
            mock_cls.return_value = mock_ser
            sess = sdev.SerialSession("/dev/ttyUSB0", 115200)
            sess.reconnect()
            mock_cls.assert_called_once()

    def test_reconnect_closes_stale_first(self):
        """reconnect() should close existing connection before reopening."""
        with patch.object(sdev.serial, "Serial") as mock_cls:
            mock_ser1 = MagicMock()
            mock_ser2 = MagicMock()
            mock_cls.side_effect = [mock_ser1, mock_ser2]
            sess = sdev.SerialSession()
            sess.connect()
            mock_ser1.close.reset_mock()
            sess.reconnect()
            mock_ser1.close.assert_called_once()

    def test_module_level_reconnect(self):
        """sdev.reconnect() should delegate to default session."""
        mock_sess = MagicMock()
        with patch.object(sdev, "_default_session", mock_sess):
            sdev.reconnect()
        mock_sess.reconnect.assert_called_once()

    def test_reconnect_in_all(self):
        """reconnect should be listed in __all__."""
        self.assertIn("reconnect", sdev.__all__)


class TestTimeoutInterrupt(unittest.TestCase):
    """Verify cli() and stream() interrupt on timeout."""

    def test_cli_interrupts_on_timeout(self):
        """cli() should call interrupt() when timeout elapses."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        sess.interrupt = MagicMock(return_value=True)

        result = sess.cli("test", timeout=0.001)

        self.assertTrue(result.timed_out)
        sess.interrupt.assert_called_once()

    def test_stream_interrupts_on_timeout(self):
        """stream() should call interrupt() when timeout elapses."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess = sdev.SerialSession()
        sess._connection = mock_ser
        sess.interrupt = MagicMock(return_value=True)

        list(sess.stream("test", timeout=0.001))

        sess.interrupt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
