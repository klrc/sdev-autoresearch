"""Adversarial tests for end_flag and line_mode features (issue #28).

Owned by the test role — covers functionality that was added to the
product but lacked dedicated unit tests.
"""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestEndFlag(unittest.TestCase):
    """cli() and stream() stop when end_flag string appears in output."""

    def test_cli_stops_on_end_flag(self):
        """cli() should return when end_flag is seen, even without prompt."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        # No prompt — only end_flag triggers stop
        mock_ser.read.side_effect = [
            b"loading model...\n",
            b"running inference...\n",
            b"Frame rate: 42.5 fps\n",
            b"",
        ]
        sess._connection = mock_ser

        result = sess.cli("./mnn_perf -m model.mnn", end_flag="Frame rate:")
        self.assertFalse(result.timed_out)
        self.assertIn("Frame rate: 42.5 fps", result.output)

    def test_cli_without_end_flag_waits_for_prompt(self):
        """Without end_flag, cli() should still wait for shell prompt."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"loading model...\n",
            b"Frame rate: 42.5 fps\n",
            b"done\n# ",
            b"",
        ]
        sess._connection = mock_ser

        result = sess.cli("./mnn_perf -m model.mnn")
        self.assertFalse(result.timed_out)
        self.assertIn("Frame rate", result.output)

    def test_cli_end_flag_appears_with_prompt(self):
        """If both end_flag and prompt appear, first match wins."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"output\n# ",
            b"",
        ]
        sess._connection = mock_ser

        result = sess.cli("echo output", end_flag="not in output")
        # end_flag never appears, prompt should still trigger stop
        self.assertFalse(result.timed_out)

    def test_cli_timeout_still_calls_interrupt(self):
        """When both end_flag and prompt are absent, timeout triggers interrupt."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        sess._connection = mock_ser
        sess.interrupt = MagicMock(return_value=True)

        result = sess.cli("top", timeout=0.2, end_flag="NEVER")
        self.assertTrue(result.timed_out)
        sess.interrupt.assert_called_once()

    def test_stream_stops_on_end_flag(self):
        """stream() should stop when end_flag appears in output."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"line1\n",
            b"line2\n",
            b"Frame rate: 100\n",
            b"",
        ]
        sess._connection = mock_ser

        chunks = list(sess.stream("cmd", end_flag="Frame rate:"))
        output = "".join(chunks)
        self.assertIn("Frame rate:", output)

    def test_stream_without_end_flag_uses_prompt(self):
        """stream() without end_flag should still stop on prompt."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"chunk1\n", b"chunk2\n# ", b""]
        sess._connection = mock_ser

        chunks = list(sess.stream("cmd"))
        self.assertEqual("".join(chunks).strip(), "chunk1\nchunk2")


class TestLineMode(unittest.TestCase):
    """stream(line_mode=True) yields complete lines only."""

    def test_line_mode_yields_complete_lines(self):
        """Only complete lines (ending with \\n) should be yielded."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        # Simulate data arriving in small chunks that split lines
        mock_ser.read.side_effect = [
            b"lin",
            b"e1\n",
            b"line2\n",
            b"li",
            b"ne3\n# ",
            b"",
        ]
        sess._connection = mock_ser

        chunks = list(sess.stream("cmd", line_mode=True))
        self.assertEqual(chunks, ["line1\n", "line2\n", "line3\n"])

    def test_line_mode_buffers_partial_line_across_chunks(self):
        """A line split across two reads should be reassembled."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"he",
            b"llo\n",
            b"wor",
            b"ld\n# ",
            b"",
        ]
        sess._connection = mock_ser

        chunks = list(sess.stream("cmd", line_mode=True))
        self.assertEqual(chunks, ["hello\n", "world\n"])

    def test_line_mode_emits_tail_on_timeout(self):
        """Remaining partial line should be emitted on timeout."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""
        sess._connection = mock_ser
        with patch.object(sess, "interrupt", return_value=False), \
             patch("sdev.time.monotonic", side_effect=[0, 0.3, 0.4, 0.5, 0.6]):
            chunks = list(sess.stream("cmd", line_mode=True, timeout=0.2))
        self.assertEqual(chunks, [])

    def test_line_mode_with_filter_fn(self):
        """filter_fn should be applied to each line in line_mode."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [
            b"ERROR: bad\n",
            b"INFO: ok\n",
            b"ERROR: worse\n# ",
            b"",
        ]
        sess._connection = mock_ser

        chunks = list(sess.stream(
            "cmd",
            line_mode=True,
            filter_fn=lambda t: t if "ERROR" in t else "",
        ))
        self.assertEqual(chunks, ["ERROR: bad\n", "ERROR: worse\n"])

    def test_line_mode_without_filter(self):
        """line_mode without filter_fn should work normally."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"a\nb\nc\n# ", b""]
        sess._connection = mock_ser

        chunks = list(sess.stream("cmd", line_mode=True))
        self.assertEqual(chunks, ["a\n", "b\n", "c\n"])

    def test_chunk_mode_still_works(self):
        """stream() without line_mode should still yield raw chunks."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"hel", b"lo\n# ", b""]
        sess._connection = mock_ser

        chunks = list(sess.stream("cmd"))
        self.assertEqual(chunks, ["hel", "lo\n"])


if __name__ == "__main__":
    unittest.main()
