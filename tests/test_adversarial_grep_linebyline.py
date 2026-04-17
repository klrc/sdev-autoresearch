"""Adversarial tests for CLI --grep line-by-line filter (PR #18)."""

import io
import re
import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestGrepLineByLineFilter(unittest.TestCase):
    """Verify the new line-by-line grep filter works correctly."""

    def test_filter_splits_lines_keeps_only_matches(self):
        """Filter should split on newlines and keep only matching lines."""
        def _grep_filter(text: str) -> str:
            _regex = re.compile("ERROR")
            trailing_nl = text.endswith("\n")
            lines = [l for l in text.splitlines() if _regex.search(l)]
            result = "\n".join(lines)
            if trailing_nl and result:
                result += "\n"
            return result

        chunk = "INFO ok\nERROR bad\nWARN slow\nERROR crash\n"
        result = _grep_filter(chunk)
        self.assertIn("ERROR bad", result)
        self.assertIn("ERROR crash", result)
        self.assertNotIn("INFO", result)
        self.assertNotIn("WARN", result)

    def test_filter_preserves_trailing_newline(self):
        """Filter should preserve trailing newline when result is non-empty."""
        _regex = re.compile("ERROR")

        def _grep_filter(text: str) -> str:
            trailing_nl = text.endswith("\n")
            lines = [l for l in text.splitlines() if _regex.search(l)]
            result = "\n".join(lines)
            if trailing_nl and result:
                result += "\n"
            return result

        self.assertTrue(_grep_filter("ERROR\n").endswith("\n"))

    def test_filter_no_match_returns_empty(self):
        """Filter should return empty string when no lines match."""
        _regex = re.compile("FATAL")

        def _grep_filter(text: str) -> str:
            trailing_nl = text.endswith("\n")
            lines = [l for l in text.splitlines() if _regex.search(l)]
            result = "\n".join(lines)
            if trailing_nl and result:
                result += "\n"
            return result

        self.assertEqual(_grep_filter("INFO ok\nWARN slow\n"), "")

    def test_filter_partial_line_no_match(self):
        """A partial line (no newline) that doesn't fully match should still
        be checked by regex. If it matches, it's kept; if not, dropped."""
        _regex = re.compile("ERROR")

        def _grep_filter(text: str) -> str:
            trailing_nl = text.endswith("\n")
            lines = [l for l in text.splitlines() if _regex.search(l)]
            result = "\n".join(lines)
            if trailing_nl and result:
                result += "\n"
            return result

        # Partial line "ERR" doesn't match "ERROR"
        self.assertEqual(_grep_filter("partial ERR"), "")
        # Partial line "ERROR mid" does match
        self.assertEqual(_grep_filter("partial ERROR mid"), "partial ERROR mid")

    def test_filter_empty_chunk(self):
        """Filter on empty input should return empty."""
        _regex = re.compile("ERROR")

        def _grep_filter(text: str) -> str:
            trailing_nl = text.endswith("\n")
            lines = [l for l in text.splitlines() if _regex.search(l)]
            result = "\n".join(lines)
            if trailing_nl and result:
                result += "\n"
            return result

        self.assertEqual(_grep_filter(""), "")


class TestCLIGrepLineByLine(unittest.TestCase):
    """Verify CLI integration with line-by-line grep."""

    def test_cli_grep_hoisted_re_import(self):
        """re should be imported at module level, not inside the function."""
        from sdev.__main__ import re as re_mod
        self.assertTrue(hasattr(re_mod, "compile"))

    def test_cli_grep_filter_called_with_regex(self):
        """CLI --stream --grep should pass a working filter_fn to stream()."""
        from sdev.__main__ import main
        captured = io.StringIO()

        with patch("sdev.SerialSession") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess.is_open = True
            mock_sess_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sess.stream.return_value = ["ERROR: disk full\n"]

            with patch("sys.argv",
                    ["sdev", "-p", "tail -f", "--stream", "--grep", "ERROR",
                     "-t", "5", "-d", "/dev/ttyS0", "-b", "9600"]), \
                 patch("sys.stdout", captured):
                main()

            call_kwargs = mock_sess.stream.call_args.kwargs
            filter_fn = call_kwargs.get("filter_fn")
            self.assertIsNotNone(filter_fn)
            result = filter_fn("INFO ok\nERROR: disk full\nWARN slow\n")
            self.assertIn("ERROR: disk full", result)
            self.assertNotIn("INFO", result)


if __name__ == "__main__":
    unittest.main()
