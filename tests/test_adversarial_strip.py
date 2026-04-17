"""Adversarial tests for echo/prompt stripping — test-owned coverage."""

import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestStripPromptEdgeCases(unittest.TestCase):
    """Edge cases for _strip_prompt not covered by dev's tests."""

    def test_removes_crlf_before_prompt(self):
        """Prompt preceded by \\r\\n should strip cleanly."""
        self.assertEqual(
            sdev._strip_prompt(b"output\r\n$ "),
            b"output\r\n"
        )

    def test_text_ending_like_prompt_is_stripped(self):
        """Text ending with a known prompt pattern gets stripped — this is by design.
        If real device output legitimately ends with '# ', it will be removed.
        This is acceptable since '# ' is a real shell prompt indicator.
        """
        result = sdev._strip_prompt(b"output# ")
        self.assertEqual(result, b"output")

    def test_compound_prompt_stripped_whole(self):
        """Compound prompts like ~# should be stripped as a whole.

        FIXED in commit fa61e54: PROMPTS reordered to check compound prompts first.
        """
        result = sdev._strip_prompt(b"out~# ")
        self.assertEqual(result, b"out")

    def test_all_prompt_variants_stripped(self):
        """Every prompt in PROMPTS should be fully stripped."""
        for p in sdev.PROMPTS:
            result = sdev._strip_prompt(b"out" + p)
            self.assertEqual(result, b"out", f"Failed for prompt {p!r}")


class TestStripEchoEdgeCases(unittest.TestCase):
    """Edge cases for _strip_echo not covered by dev's tests."""

    def test_partial_command_not_stripped(self):
        """Command that is a prefix of the buffer should not be stripped."""
        self.assertEqual(
            sdev._strip_echo(b"echo high\nresult\n# ", "echo hi"),
            b"echo high\nresult\n# "
        )

    def test_empty_command_no_crash(self):
        """Empty command should not strip anything."""
        self.assertEqual(
            sdev._strip_echo(b"some output\n# ", ""),
            b"some output\n# "
        )

    def test_command_appears_mid_buffer(self):
        """Command text appearing mid-buffer should not be stripped."""
        self.assertEqual(
            sdev._strip_echo(b"prefix: echo hi\nresult\n# ", "echo hi"),
            b"prefix: echo hi\nresult\n# "
        )


class TestStreamPromptSpanningChunkBoundary(unittest.TestCase):
    """Guard: prompt that spans two chunks should still be stripped."""

    def test_prompt_spanning_chunks_not_in_output(self):
        """If prompt ' # ' is split across chunks, final yield should not include it."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"hello worl", b"d\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("echo hello world"))
        combined = "".join(chunks)
        self.assertNotIn("# ", combined, "Prompt leaked into stream output")


class TestCLIOutputCleansing(unittest.TestCase):
    """Verify cli() output does not contain echo or prompt."""

    def test_cli_strips_echo_and_prompt(self):
        """cli() result should not contain the echoed command or trailing prompt."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"echo test\nhello world\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("echo test")
        self.assertNotIn("echo test", result.output)
        self.assertNotIn("# ", result.output)
        self.assertIn("hello world", result.output)

    def test_cli_strips_echo_with_crlf(self):
        """Some devices echo with \\r\\n instead of \\n."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"cmd\r\nok\r\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("cmd")
        self.assertNotIn("cmd", result.output)
        self.assertIn("ok", result.output)


if __name__ == "__main__":
    unittest.main()
