"""Adversarial tests for ANSI escape sequence stripping — test-owned coverage."""

import unittest
from unittest.mock import MagicMock

import sdev


class TestStripANSI(unittest.TestCase):
    """Verify _strip_ansi removes terminal escape sequences."""

    def test_strips_color_codes(self):
        """Should strip basic ANSI color codes."""
        result = sdev._strip_ansi(b"\x1b[31mred\x1b[0m")
        self.assertEqual(result, b"red")

    def test_strips_cursor_movement(self):
        """Should strip cursor movement codes."""
        result = sdev._strip_ansi(b"hello\x1b[10;5Hworld")
        self.assertEqual(result, b"helloworld")

    def test_strips_clear_screen(self):
        """Should strip clear-screen code."""
        result = sdev._strip_ansi(b"text\x1b[2Jmore")
        self.assertEqual(result, b"textmore")

    def test_no_ansi_passes_through(self):
        """Plain text without ANSI should be unchanged."""
        result = sdev._strip_ansi(b"plain text 123")
        self.assertEqual(result, b"plain text 123")

    def test_empty_buffer(self):
        """Empty buffer should remain empty."""
        self.assertEqual(sdev._strip_ansi(b""), b"")

    def test_multiple_codes_in_sequence(self):
        """Multiple ANSI codes should all be stripped."""
        result = sdev._strip_ansi(b"\x1b[1;32mOK\x1b[0m\n")
        self.assertEqual(result, b"OK\n")

    def test_ansi_in_command_output_integration(self):
        """cli() should return output with ANSI stripped."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.side_effect = [b"echo colored\n\x1b[32mresult\x1b[0m\n# ", b""]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        result = sess.cli("echo colored")
        self.assertNotIn("\x1b", result.output)
        self.assertIn("result", result.output)


if __name__ == "__main__":
    unittest.main()
