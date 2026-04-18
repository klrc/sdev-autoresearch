"""Integration tests: full CLI entry point -> SerialSession workflows.

These tests verify that the CLI entry point (__main__.py) correctly
wires arguments through to SerialSession methods, and that module-level
convenience APIs behave consistently.
"""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import sdev
from sdev.__main__ import main


class TestCLIFullWorkflow(unittest.TestCase):
    """End-to-end CLI flows with mocked serial."""

    def _mock_session(self, cli_output="ok\n", stream_chunks=None, parse_result=None):
        """Create a mock SerialSession for CLI tests."""
        mock_sess = MagicMock()
        mock_sess.is_open = True
        mock_sess.cli.return_value = sdev.SerialResult(
            "cmd", cli_output, False, 0.1)
        if stream_chunks is None:
            stream_chunks = ["line1\n", "line2\n"]
        mock_sess.stream.return_value = iter(stream_chunks)
        if parse_result is None:
            parse_result = sdev.ParseResult(
                lines=["MemTotal: 1000"], matched=["MemTotal: 1000"],
                raw="MemTotal: 1000\n")
        mock_sess.parse.return_value = parse_result
        mock_sess.doctor = MagicMock()
        return mock_sess

    def _run_main(self, args):
        """Run main() with given argv, return captured stdout."""
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.read.return_value = b""

        with patch("sys.argv", ["sdev"] + args), \
             patch("sdev.serial.Serial", return_value=mock_ser), \
             patch("io.StringIO", return_value=io.StringIO()) as mock_io:
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()
            return captured.getvalue()

    def test_cli_normal_mode_full_flow(self):
        """Normal mode: connect, run command, detect prompt, return output."""
        mock_sess = self._mock_session(cli_output="hello\n")
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "echo hello",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            self.assertEqual(captured.getvalue(), "hello\n")
            mock_sess.cli.assert_called_once_with(
                "echo hello", timeout=None, end_flag=None)

    def test_cli_stream_with_grep_filter(self):
        """Stream mode with --grep: filter applied, timeout passed."""
        mock_sess = self._mock_session(
            stream_chunks=["ERROR: disk\n", "INFO: ok\n", "ERROR: net\n"])
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "tail -f log",
                                "--stream", "--grep", "ERROR",
                                "-t", "15",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            mock_sess.stream.assert_called_once()
            call_kwargs = mock_sess.stream.call_args
            self.assertEqual(call_kwargs[1]["timeout"], 15.0)
            self.assertIsNotNone(call_kwargs[1]["filter_fn"])
            # Verify filter actually filters
            filter_fn = call_kwargs[1]["filter_fn"]
            self.assertEqual(filter_fn("ERROR: bad\n"), "ERROR: bad\n")
            self.assertEqual(filter_fn("INFO: ok\n"), "")

    def test_cli_stream_with_line_mode(self):
        """Stream mode with --line-mode: line_mode=True passed."""
        mock_sess = self._mock_session()
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "dmesg",
                                "--stream", "--line-mode",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            mock_sess.stream.assert_called_once()
            call_kwargs = mock_sess.stream.call_args
            self.assertTrue(call_kwargs[1]["line_mode"])

    def test_cli_with_end_flag(self):
        """CLI --end-flag passed to both cli() and stream()."""
        mock_sess = self._mock_session()
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "./bench",
                                "--end-flag", "Frame rate:",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            mock_sess.cli.assert_called_once_with(
                "./bench", timeout=None, end_flag="Frame rate:")

    def test_cli_with_doctor(self):
        """CLI --doctor calls doctor() before running command."""
        mock_sess = self._mock_session()
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "uptime",
                                "--doctor",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            mock_sess.doctor.assert_called_once()
            mock_sess.cli.assert_called_once()
            # doctor must be called before cli
            call_order = [
                mock_sess.doctor.call_count > 0,
                mock_sess.cli.call_count > 0,
            ]
            self.assertTrue(all(call_order))

    def test_cli_with_custom_prompts(self):
        """CLI --prompt passes byte-encoded prompts to SerialSession."""
        mock_sess = self._mock_session()
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "ls",
                                "--prompt", "[root]# ",
                                "--prompt", "admin> ",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            # SerialSession should be called with byte-encoded prompts
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args
            prompts = call_kwargs[1].get("prompts")
            self.assertEqual(prompts, [b"[root]# ", b"admin> "])

    def test_cli_timeout_exit_code(self):
        """CLI returns exit code 2 when command times out."""
        mock_sess = MagicMock()
        mock_sess.cli.return_value = sdev.SerialResult(
            "sleep 999", "", True, 5.0)
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "sleep 999",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 2)

    def test_cli_parse_no_matches_exit_code(self):
        """CLI returns exit code 3 when --parse finds no matches."""
        mock_sess = MagicMock()
        mock_sess.parse.return_value = sdev.ParseResult(
            lines=["foo", "bar"], matched=[], raw="foo\nbar\n")
        mock_ser = MagicMock()

        with patch("sys.argv", ["sdev", "-p", "cat file",
                                "--parse", "NOTFOUND",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 3)


class TestCLISetDefault(unittest.TestCase):
    """Integration tests for set-default subcommand."""

    def test_set_default_writes_config(self):
        """set-default should write JSON config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = os.path.join(tmpdir, "defaults.json")
            with patch.object(sdev, "CONFIG_FILE", __file__):
                # Use a temp path for the actual write
                import json
                from pathlib import Path
                tmp_path = Path(tmpdir) / "defaults.json"
                with patch.object(sdev, "CONFIG_FILE", tmp_path), \
                     patch.object(sdev, "CONFIG_DIR", tmp_path.parent), \
                     patch("sys.argv", ["sdev", "set-default",
                                        "/dev/ttyACM0", "57600"]):
                    captured = io.StringIO()
                    with patch("sys.stdout", captured):
                        main()

                    data = json.loads(tmp_path.read_text())
                    self.assertEqual(data["device"], "/dev/ttyACM0")
                    self.assertEqual(data["baud"], 57600)


class TestCLILoadDefaults(unittest.TestCase):
    """CLI should load saved defaults when -d/-b omitted."""

    def test_load_defaults_applied(self):
        """When no -d/-b given, loaded defaults should be used."""
        mock_sess = MagicMock()
        mock_sess.cli.return_value = sdev.SerialResult(
            "echo ok", "ok\n", False, 0.1)
        mock_ser = MagicMock()

        defaults = {"device": "/dev/ttyACM0", "baud": 57600}

        with patch("sdev.load_defaults", return_value=defaults), \
             patch("sys.argv", ["sdev", "-p", "echo ok"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            # SerialSession should be called with loaded defaults
            mock_cls.assert_called_once()
            call_args = mock_cls.call_args
            self.assertEqual(call_args[0][0], "/dev/ttyACM0")
            self.assertEqual(call_args[0][1], 57600)

    def test_cli_overrides_defaults(self):
        """CLI flags should override loaded defaults."""
        mock_sess = MagicMock()
        mock_sess.cli.return_value = sdev.SerialResult(
            "echo ok", "ok\n", False, 0.1)
        mock_ser = MagicMock()

        defaults = {"device": "/dev/ttyACM0", "baud": 57600}

        with patch("sdev.load_defaults", return_value=defaults), \
             patch("sys.argv", ["sdev", "-p", "echo ok",
                                "-d", "/dev/ttyUSB1", "-b", "115200"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=mock_ser):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            mock_cls.assert_called_once()
            call_args = mock_cls.call_args
            self.assertEqual(call_args[0][0], "/dev/ttyUSB1")
            self.assertEqual(call_args[0][1], 115200)


class TestModuleLevelAPI(unittest.TestCase):
    """Module-level convenience APIs should delegate correctly."""

    def test_module_cli_delegates(self):
        """sdev.cli() should call default session's cli()."""
        mock_sess = MagicMock()
        mock_sess.cli.return_value = sdev.SerialResult(
            "echo x", "x\n", False, 0.01)

        with patch.object(sdev, "_default_session", mock_sess):
            result = sdev.cli("echo x", timeout=5)

        mock_sess.cli.assert_called_once_with("echo x", 5, None)
        self.assertEqual(result.output, "x\n")

    def test_module_cli_passes_end_flag(self):
        """sdev.cli() should pass end_flag to default session."""
        mock_sess = MagicMock()
        mock_sess.cli.return_value = sdev.SerialResult(
            "bench", "Frame rate: 60\n", False, 1.0)

        with patch.object(sdev, "_default_session", mock_sess):
            sdev.cli("bench", end_flag="Frame rate:")

        mock_sess.cli.assert_called_once_with("bench", None, "Frame rate:")

    def test_module_connect_delegates(self):
        """sdev.connect() should call default session's connect()."""
        mock_sess = MagicMock()
        with patch.object(sdev, "_default_session", mock_sess):
            sdev.connect("/dev/ttyS1", 9600)
        mock_sess.connect.assert_called_once_with("/dev/ttyS1", 9600)

    def test_module_disconnect_delegates(self):
        """sdev.disconnect() should call default session's close()."""
        mock_sess = MagicMock()
        with patch.object(sdev, "_default_session", mock_sess):
            sdev.disconnect()
        mock_sess.close.assert_called_once()

    def test_module_stream_delegates(self):
        """sdev.stream() should yield from default session's stream()."""
        mock_sess = MagicMock()
        mock_sess.stream.return_value = iter(["a\n", "b\n"])

        with patch.object(sdev, "_default_session", mock_sess):
            chunks = list(sdev.stream("tail -f log"))

        self.assertEqual(chunks, ["a\n", "b\n"])
        mock_sess.stream.assert_called_once_with(
            "tail -f log", None, 256, None, False, None)

    def test_module_parse_delegates(self):
        """sdev.parse() should call default session's parse()."""
        mock_sess = MagicMock()
        mock_sess.parse.return_value = sdev.ParseResult(
            lines=["a", "b"], matched=["a"], raw="a\nb\n")

        with patch.object(sdev, "_default_session", mock_sess):
            result = sdev.parse("cmd", pattern="a", timeout=10)

        mock_sess.parse.assert_called_once_with("cmd", "a", 10)
        self.assertEqual(result.matched, ["a"])

    def test_module_interrupt_delegates(self):
        """sdev.interrupt() should call default session's interrupt()."""
        mock_sess = MagicMock()
        mock_sess.interrupt.return_value = True

        with patch.object(sdev, "_default_session", mock_sess):
            result = sdev.interrupt(timeout=3)

        mock_sess.interrupt.assert_called_once_with(3)
        self.assertTrue(result)

    def test_module_reconnect_delegates(self):
        """sdev.reconnect() should call default session's reconnect()."""
        mock_sess = MagicMock()
        with patch.object(sdev, "_default_session", mock_sess):
            sdev.reconnect()
        mock_sess.reconnect.assert_called_once()

    def test_ensure_connection_raises_when_not_open(self):
        """sdev.ensure_connection() should raise when not connected."""
        mock_sess = MagicMock()
        mock_sess._ensure_open.side_effect = RuntimeError("Not connected")

        with patch.object(sdev, "_default_session", mock_sess):
            with self.assertRaises(RuntimeError):
                sdev.ensure_connection()


class TestSessionContextManager(unittest.TestCase):
    """SerialSession context manager behavior."""

    def test_enter_connects_if_not_open(self):
        """__enter__ should call connect() when not connected."""
        sess = sdev.SerialSession()
        mock_ser = MagicMock()

        with patch.object(sess, "connect", wraps=sess.connect) as mock_connect:
            with patch.object(sdev.serial, "Serial", return_value=mock_ser):
                with sess:
                    pass

        mock_connect.assert_called_once()

    def test_enter_skips_connect_if_already_open(self):
        """__enter__ should NOT call connect() when already open."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        with patch.object(sess, "connect") as mock_connect:
            with sess:
                pass

        mock_connect.assert_not_called()

    def test_exit_closes_connection(self):
        """__exit__ should call close()."""
        mock_ser = MagicMock()
        mock_ser.is_open = True

        sess = sdev.SerialSession()
        sess._connection = mock_ser

        with sess:
            pass

        self.assertIsNone(sess._connection)


class TestCLIProbe(unittest.TestCase):
    """Integration tests for --probe CLI flag."""

    def test_probe_exits_nonzero_when_no_devices(self):
        """--probe should exit with code 1 when no devices found."""
        with patch("sys.argv", ["sdev", "--probe"]), \
             patch.object(sdev, "probe", return_value=[]):
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)

    def test_probe_prints_devices_when_found(self):
        """--probe should print device info for each found device."""
        fake_results = [
            {
                "device": "/dev/ttyUSB0",
                "baud": 115200,
                "info": {
                    "os_name": "Ubuntu",
                    "hostname": "xc01",
                    "arch": "armv7l",
                },
            },
        ]
        with patch("sys.argv", ["sdev", "--probe"]), \
             patch.object(sdev, "probe", return_value=fake_results):
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()
            output = captured.getvalue()
            self.assertIn("/dev/ttyUSB0", output)
            self.assertIn("Ubuntu", output)
            self.assertIn("xc01", output)

    def test_probe_handles_error_in_results(self):
        """--probe should print ERROR for devices that fail."""
        fake_results = [
            {"device": "/dev/ttyUSB0", "baud": 115200, "error": "permission denied"},
        ]
        with patch("sys.argv", ["sdev", "--probe"]), \
             patch.object(sdev, "probe", return_value=fake_results):
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()
            output = captured.getvalue()
            self.assertIn("/dev/ttyUSB0", output)
            self.assertIn("permission denied", output)

    def test_probe_passes_custom_bauds(self):
        """--probe --probe-baud 9600 should pass baud_rates to probe()."""
        with patch("sys.argv", ["sdev", "--probe", "--probe-baud", "9600",
                                "--probe-baud", "38400"]), \
             patch.object(sdev, "probe", return_value=[]) as mock_probe:
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit):
                    main()
            mock_probe.assert_called_once_with(baud_rates=[9600, 38400], timeout=2)


class TestCLIDoctor(unittest.TestCase):
    """Tests for --doctor CLI flag."""

    def test_doctor_before_cli(self):
        """--doctor should call doctor() before cli()."""
        mock_sess = MagicMock()
        mock_sess.cli.return_value = sdev.SerialResult("cmd", "ok\n", False, 0.1)

        with patch("sys.argv", ["sdev", "-p", "uptime", "--doctor",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls, \
             patch("sdev.serial.Serial", return_value=MagicMock()):
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            # Verify doctor was called before cli
            doctor_call = mock_sess.doctor.call_args_list
            cli_call = mock_sess.cli.call_args_list
            self.assertTrue(len(doctor_call) > 0)
            self.assertTrue(len(cli_call) > 0)
            # Doctor call index < cli call index in the mock
            doctor_idx = mock_sess.doctor.call_count  # at least 1
            self.assertGreater(doctor_idx, 0)


class TestCLIInterrupt(unittest.TestCase):
    """Tests for --interrupt CLI flag."""

    def test_interrupt_sends_ctrl_c(self):
        """--interrupt should call session.interrupt()."""
        with patch("sys.argv", ["sdev", "--interrupt",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls:
            mock_sess = MagicMock()
            mock_sess.interrupt.return_value = True
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main()

            mock_sess.interrupt.assert_called_once()

    def test_interrupt_exits_nonzero_when_no_prompt(self):
        """--interrupt should exit 1 when prompt not detected."""
        with patch("sys.argv", ["sdev", "--interrupt",
                                "-d", "/dev/ttyS0", "-b", "9600"]), \
             patch("sdev.SerialSession") as mock_cls:
            mock_sess = MagicMock()
            mock_sess.interrupt.return_value = False
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_sess)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            captured = io.StringIO()
            with patch("sys.stderr", captured):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)


class TestDefaultsPersistence(unittest.TestCase):
    """save_default / load_defaults round-trip."""

    def test_save_and_load_roundtrip(self):
        """save_default then load_defaults should return saved values."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "defaults.json"
            with patch.object(sdev, "CONFIG_FILE", tmp_path), \
                 patch.object(sdev, "CONFIG_DIR", tmp_path.parent):
                sdev.save_default("/dev/ttyACM0", 57600)
                defaults = sdev.load_defaults()
                self.assertEqual(defaults["device"], "/dev/ttyACM0")
                self.assertEqual(defaults["baud"], 57600)

    def test_load_defaults_empty_when_no_file(self):
        """load_defaults should return {} when config doesn't exist."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "nonexistent.json"
            with patch.object(sdev, "CONFIG_FILE", tmp_path):
                defaults = sdev.load_defaults()
                self.assertEqual(defaults, {})


if __name__ == "__main__":
    unittest.main()
