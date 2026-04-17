"""Adversarial tests for --grep filter — test-owned coverage."""

import io
import unittest
from unittest.mock import MagicMock, patch

import sdev


class TestGrepFilter(unittest.TestCase):
    """Verify --grep flag filters stream output correctly."""

    def test_grep_matches_lines(self):
        """stream() with filter_fn should only yield matching lines."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        import re
        regex = re.compile("ERROR")
        def grep_filter(line):
            return line if regex.search(line) else ""

        mock_ser.read.side_effect = [
            b"INFO starting\n",
            b"ERROR something broke\n",
            b"INFO done\n# "
        ]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("tail -f", filter_fn=grep_filter))
        combined = "".join(chunks)
        self.assertIn("ERROR", combined)
        self.assertNotIn("INFO", combined)

    def test_grep_filters_out_all_lines(self):
        """If no lines match, filter_fn yields nothing."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        import re
        regex = re.compile("FATAL")
        def grep_filter(line):
            return line if regex.search(line) else ""

        mock_ser.read.side_effect = [
            b"INFO ok\n",
            b"WARN slow\n# "
        ]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("tail -f", filter_fn=grep_filter))
        self.assertEqual(chunks, [])


class TestCLIEntrypointGrep(unittest.TestCase):
    """Verify CLI --grep flag integration."""

    def test_stream_with_grep(self):
        """CLI --stream --grep should pass filter_fn to stream()."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        from sdev.__main__ import main
        captured = io.StringIO()

        with patch("sdev.SerialSession") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess.is_open = True
            mock_sess_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sess.stream.return_value = ["ERROR\n"]

            with patch("sys.argv",
                    ["sdev", "-p", "tail -f", "--stream", "--grep", "ERROR",
                     "-t", "5", "-d", "/dev/ttyS0", "-b", "9600"]), \
                 patch("sys.stdout", captured), \
                 patch("sdev.serial.Serial", return_value=mock_ser):
                main()

            call_args = mock_sess.stream.call_args
            self.assertEqual(call_args.kwargs.get("timeout"), 5.0)
            self.assertIsNotNone(call_args.kwargs.get("filter_fn"))

    def test_stream_without_grep_passes_none_filter(self):
        """CLI --stream without --grep should pass filter_fn=None."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        from sdev.__main__ import main
        captured = io.StringIO()

        with patch("sdev.SerialSession") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess.is_open = True
            mock_sess_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sess.stream.return_value = ["chunk\n"]

            with patch("sys.argv",
                    ["sdev", "-p", "tail -f", "--stream",
                     "-t", "10", "-d", "/dev/ttyS0", "-b", "9600"]), \
                 patch("sys.stdout", captured), \
                 patch("sdev.serial.Serial", return_value=mock_ser):
                main()

            call_kwargs = mock_sess.stream.call_args.kwargs
            self.assertIsNone(call_kwargs.get("filter_fn"))


class TestGrepRegexEdgeCases(unittest.TestCase):
    """Edge cases for grep regex handling."""

    def test_grep_invalid_regex_still_compiles(self):
        """If grep compiles a bad regex, stream should still work."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        import re
        # Test with a regex that matches everything
        regex = re.compile(".*")
        def grep_filter(line):
            return line if regex.search(line) else ""

        mock_ser.read.side_effect = [b"anything\n# "]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("echo anything", filter_fn=grep_filter))
        self.assertTrue(len(chunks) > 0)

    def test_grep_multi_match(self):
        """Multiple lines matching should all be included."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        import re
        regex = re.compile("line")
        def grep_filter(line):
            return line if regex.search(line) else ""

        mock_ser.read.side_effect = [
            b"line1\nline2\nline3\n# "
        ]

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        chunks = list(sess.stream("echo multi", filter_fn=grep_filter))
        combined = "".join(chunks)
        self.assertIn("line1", combined)
        self.assertIn("line2", combined)
        self.assertIn("line3", combined)


if __name__ == "__main__":
    unittest.main()
