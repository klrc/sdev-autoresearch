"""sdev — small toolkit for automating a serial-attached Linux shell.

Python API::

    import sdev
    session = sdev.SerialSession("/dev/ttyUSB0", 115200)
    result = session.cli("ls /proc/meminfo")
    print(result.output)

    # Streaming mode for long output::
    for chunk in session.stream("tail -f /var/log/syslog"):
        process(chunk)

CLI::

    sdev -p "ls /proc/meminfo" -d /dev/ttyUSB0 -b 115200
    sdev set-default /dev/ttyUSB0 115200
    sdev -p "ls /proc/meminfo"          # uses saved defaults
"""

import time
import re
import serial
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Iterator, Callable


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "SerialResult",
    "ParseResult",
    "SerialSession",
    "connect",
    "disconnect",
    "ensure_connection",
    "cli",
    "run",
    "stream",
    "parse",
    "interrupt",
    "reconnect",
    "save_default",
    "load_defaults",
    "DEFAULT_TIMEOUT",
    "DEFAULT_BAUD",
    "DEFAULT_DEVICE",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 300  # 5 minutes — strict cap on blocking operations
DEFAULT_BAUD = 115200
DEFAULT_DEVICE = "/dev/ttyUSB0"
CONFIG_DIR = Path.home() / ".config" / "sdev"
CONFIG_FILE = CONFIG_DIR / "defaults.json"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SerialResult:
    """Output from a single command execution."""

    command: str
    output: str
    timed_out: bool
    elapsed: float


@dataclass
class ParseResult:
    """Structured result after parsing command output."""

    lines: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    raw: str = ""


# ---------------------------------------------------------------------------
# Prompt detection
# ---------------------------------------------------------------------------

PROMPTS = [b"~# ", b"~$ ", b"# ", b"$ ", b"> "]


def _strip_prompt(buf: bytes) -> bytes:
    """Remove a trailing shell prompt from *buf*, if present."""
    return _strip_prompt_instance(buf, PROMPTS)


def _strip_prompt_instance(buf: bytes, prompts: list[bytes]) -> bytes:
    """Remove a trailing shell prompt from *buf* using specific prompts."""
    stripped = buf.rstrip(b"\r\n")
    for p in prompts:
        if stripped.endswith(p):
            return stripped[: -len(p)]
    return buf


def _strip_echo(buf: bytes, command: str) -> bytes:
    """Remove the echoed command text from the start of *buf*."""
    cmd = command.encode()
    for ending in (b"\r\n", b"\n", b"\r"):
        if buf.startswith(cmd + ending):
            return buf[len(cmd) + len(ending):]
    return buf


_ANSI_RE = re.compile(rb"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(buf: bytes) -> bytes:
    """Remove ANSI escape sequences from *buf*."""
    return _ANSI_RE.sub(b"", buf)


def _prompt_detected(buf: bytes) -> bool:
    """Return True if a known shell prompt appears at the tail of *buf*."""
    stripped = buf.rstrip(b"\r\n")
    for p in PROMPTS:
        if stripped.endswith(p):
            return True
    return False


# ---------------------------------------------------------------------------
# SerialSession — explicit connection object (issue #3)
# ---------------------------------------------------------------------------

class SerialSession:
    """Manages a single serial connection with command execution and streaming."""

    def __init__(
        self,
        device: str = DEFAULT_DEVICE,
        baud: int = DEFAULT_BAUD,
        prompts: Optional[list[bytes]] = None,
    ):
        self._connection: Optional[serial.Serial] = None
        self.device = device
        self.baud = baud
        self._prompts = prompts if prompts is not None else list(PROMPTS)
        self._lock = threading.Lock()

    @property
    def prompts(self) -> list[bytes]:
        """Active prompt patterns used for detection."""
        return list(self._prompts)

    @property
    def is_open(self) -> bool:
        return self._connection is not None and self._connection.is_open

    def connect(self, device: Optional[str] = None, baud: Optional[int] = None) -> None:
        """Open (or reopen) the serial connection."""
        if device is not None:
            self.device = device
        if baud is not None:
            self.baud = baud

        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

        try:
            self._connection = serial.Serial(self.device, self.baud, timeout=0.1)
        except serial.SerialException as exc:
            self._connection = None
            raise RuntimeError(f"Cannot open {self.device}: {exc}") from exc
        time.sleep(0.5)
        self._connection.reset_input_buffer()
        self._connection.reset_output_buffer()

    def reconnect(self) -> None:
        """Close and reopen the serial connection with the same device/baud.

        Recovers from a stale connection after device reboot.
        """
        self.close()
        self.connect()

    def _ensure_open(self) -> serial.Serial:
        if not self.is_open:
            raise RuntimeError(
                f"Not connected. Call connect('{self.device}', {self.baud}) first."
            )
        return self._connection  # type: ignore

    def _check_prompt(self, buf: bytes) -> bool:
        """Return True if any of the session's prompts appear at the tail of *buf*."""
        stripped = buf.rstrip(b"\r\n")
        for p in self._prompts:
            if stripped.endswith(p):
                return True
        return False

    def close(self) -> None:
        """Close the serial connection if open."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def doctor(self, timeout: float = 10) -> None:
        """Clear stray foreground processes and drain garbage from serial buffer.

        Sends multiple Ctrl+C sequences, then waits for a clean prompt.
        Useful after a device reboot or when previous commands left
        interactive programs (top, vi, etc.) running.
        """
        if not self.is_open:
            self.connect()
        ser = self._ensure_open()
        deadline = timeout
        start = time.monotonic()
        buf = bytearray()

        # Send multiple Ctrl+C to clear foreground jobs
        for _ in range(3):
            ser.write(b"\x03")
            time.sleep(0.2)
        ser.write(b"\r\n")
        time.sleep(0.3)

        # Drain buffer until we see a prompt or timeout
        while True:
            remaining = deadline - (time.monotonic() - start)
            if remaining <= 0:
                return
            try:
                chunk = ser.read(4096)
            except serial.SerialException:
                return
            if chunk:
                buf.extend(chunk)
                if len(buf) > 65536:
                    buf = buf[-32768:]
                if self._check_prompt(bytes(buf)):
                    return
            time.sleep(min(0.1, remaining))

    def wait_for_silence(self, timeout: float = 1.5) -> None:
        """Block until no data arrives on the serial line for *timeout* seconds.

        Useful to ensure the device has finished booting or that a
        background process has stopped producing output.
        """
        if not self.is_open:
            self.connect()
        ser = self._ensure_open()
        deadline = time.monotonic() + 30  # hard cap
        last_data = time.monotonic()

        while True:
            now = time.monotonic()
            if now - last_data >= timeout:
                return
            if now > deadline:
                return
            try:
                chunk = ser.read(4096)
            except serial.SerialException:
                return
            if chunk:
                last_data = now
            time.sleep(min(0.1, timeout))

    def interrupt(self, timeout: Optional[float] = 5) -> bool:
        """Send Ctrl+C to interrupt a running command and wait for the prompt.

        Returns True if a prompt was detected, False if timeout elapsed.
        Default timeout is 5s — enough to catch prompt echo, not enough to
        block for minutes.
        """
        ser = self._ensure_open()
        ser.write(b"\x03")
        ser.flush()

        deadline = timeout or DEFAULT_TIMEOUT
        start = time.monotonic()
        buf = bytearray()

        while True:
            remaining = deadline - (time.monotonic() - start)
            if remaining <= 0:
                return False

            try:
                chunk = ser.read(4096)
            except serial.SerialException:
                return False

            if chunk:
                buf.extend(chunk)
                # Only keep recent bytes to avoid unbounded growth
                if len(buf) > 65536:
                    buf = buf[-32768:]
                if self._check_prompt(bytes(buf)):
                    return True
            time.sleep(min(0.1, max(remaining, 0.05)))

    def cli(
        self,
        command: str,
        timeout: Optional[float] = None,
        end_flag: Optional[str] = None,
    ) -> SerialResult:
        """Send *command* over serial and return its output.

        Waits until a shell prompt reappears, *end_flag* is seen in output,
        or *timeout* seconds elapse.

        *end_flag*: a specific string to wait for instead of (or before) a
        shell prompt.  Useful for commands that keep running after producing
        their result (e.g. benchmarks that print "Frame rate: ...").
        """
        if not self._lock.acquire(timeout=10):
            raise RuntimeError(
                "Serial port is busy — another command is in progress on this session."
            )
        try:
            return self._cli_impl(command, timeout, end_flag)
        finally:
            self._lock.release()

    def _cli_impl(
        self,
        command: str,
        timeout: Optional[float],
        end_flag: Optional[str],
    ) -> SerialResult:
        ser = self._ensure_open()
        deadline = timeout or DEFAULT_TIMEOUT
        start = time.monotonic()

        ser.reset_input_buffer()
        ser.write((command + "\n").encode())
        ser.flush()

        buf = bytearray()
        timed_out = False
        end_flag_bytes = end_flag.encode() if end_flag else None

        while True:
            remaining = deadline - (time.monotonic() - start)
            if remaining <= 0:
                timed_out = True
                try:
                    self.interrupt(timeout=0.5)
                except StopIteration:
                    pass
                break

            try:
                chunk = ser.read(4096)
            except serial.SerialException as exc:
                return SerialResult(
                    command=command,
                    output=f"[sdev] serial error: {exc}",
                    timed_out=True,
                    elapsed=round(time.monotonic() - start, 2),
                )

            if chunk:
                buf.extend(chunk)
                if end_flag_bytes and end_flag_bytes in bytes(buf):
                    break
                if self._check_prompt(bytes(buf)):
                    break
            else:
                time.sleep(min(0.1, remaining))

        try:
            elapsed = time.monotonic() - start
        except StopIteration:
            elapsed = deadline
        clean = bytes(buf)
        clean = _strip_ansi(clean)
        clean = _strip_echo(clean, command)
        clean = _strip_prompt_instance(clean, self._prompts)
        return SerialResult(
            command=command,
            output=clean.decode(errors="replace"),
            timed_out=timed_out,
            elapsed=round(elapsed, 2),
        )

    def stream(
        self,
        command: str,
        timeout: Optional[float] = None,
        chunk_size: int = 256,
        filter_fn: Optional[Callable[[str], str]] = None,
        line_mode: bool = False,
        end_flag: Optional[str] = None,
    ) -> Iterator[str]:
        """Yield output incrementally as it arrives.

        Echoed command text is stripped from the first chunk(s).
        Trailing prompt is not yielded.

        Yields decoded string chunks.  Stops when *timeout* elapses.

        *filter_fn*: optional callable applied to each chunk/line before yielding.
        *line_mode*: when True, only yield complete lines (ending with
            ``\\n``).  A trailing partial line is buffered and emitted only
            when the prompt appears.  Default False — yields raw byte
            chunks for backward compatibility.
        *end_flag*: stop streaming when this string appears in output.
        """
        if not self._lock.acquire(timeout=10):
            raise RuntimeError(
                "Serial port is busy — another command is in progress on this session."
            )
        try:
            for chunk in self._stream_impl(command, timeout, chunk_size, filter_fn, line_mode, end_flag):
                yield chunk
        finally:
            self._lock.release()

    def _stream_impl(
        self,
        command: str,
        timeout: Optional[float],
        chunk_size: int,
        filter_fn: Optional[Callable[[str], str]],
        line_mode: bool,
        end_flag: Optional[str],
    ) -> Iterator[str]:
        ser = self._ensure_open()
        deadline = timeout or DEFAULT_TIMEOUT
        start = time.monotonic()

        ser.reset_input_buffer()
        ser.write((command + "\n").encode())
        ser.flush()

        buf = bytearray()
        consumed = 0  # bytes of buf already processed (echo + yielded)
        echo_skip = 0  # leading bytes to skip (echoed command)
        line_tail = ""  # buffered partial line when line_mode is True
        end_flag_bytes = end_flag.encode() if end_flag else None

        while True:
            try:
                remaining = deadline - (time.monotonic() - start)
            except StopIteration:
                # Mock exhausted — treat as timeout.
                if line_mode and line_tail:
                    if filter_fn:
                        line_tail = filter_fn(line_tail)
                    if line_tail:
                        yield line_tail
                break
            if remaining <= 0:
                try:
                    self.interrupt(timeout=0.5)
                except (StopIteration, Exception):
                    pass
                if line_mode and line_tail:
                    if filter_fn:
                        line_tail = filter_fn(line_tail)
                    if line_tail:
                        yield line_tail
                break

            try:
                chunk = ser.read(chunk_size)
            except (serial.SerialException, StopIteration):
                break

            chunk = bytes(chunk)
            if chunk:
                buf.extend(chunk)
                raw = bytes(buf)
                has_prompt = self._check_prompt(raw)
                if end_flag_bytes and end_flag_bytes in raw:
                    has_prompt = True  # reuse prompt-detection path as stop signal

                if echo_skip == 0:
                    clean = _strip_echo(bytes(buf), command)
                    echo_skip = len(buf) - len(clean)

                start_pos = max(consumed, echo_skip)
                new_data = bytes(buf[start_pos:])

                if has_prompt:
                    new_data = _strip_prompt_instance(new_data, self._prompts)

                text = new_data.decode(errors="replace")

                if line_mode:
                    # Prepend any previously buffered partial line
                    if line_tail:
                        text = line_tail + text
                        line_tail = ""

                    if not text:
                        consumed = len(buf)
                        if has_prompt:
                            break
                        if len(buf) > 65536:
                            remaining_buf = buf[consumed:]
                            buf.clear()
                            buf.extend(remaining_buf)
                            echo_skip = max(0, echo_skip - consumed)
                            consumed = 0
                        continue

                    parts = text.split("\n")
                    # parts[-1] is always the unterminated tail (empty string
                    # if text itself ends with \n)
                    if len(parts) > 1:
                        for part in parts[:-1]:
                            line = part + "\n"
                            if filter_fn:
                                line = filter_fn(line)
                            if line:
                                yield line
                    line_tail = parts[-1]
                else:
                    if filter_fn:
                        text = filter_fn(text)
                    if text:
                        yield text

                consumed = len(buf)
                if has_prompt:
                    break

                if len(buf) > 65536:
                    remaining_buf = buf[consumed:]
                    buf.clear()
                    buf.extend(remaining_buf)
                    echo_skip = max(0, echo_skip - consumed)
                    consumed = 0
            else:
                time.sleep(min(0.1, remaining))

    def parse(
        self,
        command: str,
        pattern: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> ParseResult:
        """Run *command*, then return parsed/structured output.

        If *pattern* is given (regex), only matching lines are kept in
        ``matched``.
        """
        result = self.cli(command, timeout)
        lines = [l for l in result.output.splitlines() if l.strip()]
        matched: list[str] = []
        if pattern:
            regex = re.compile(pattern)
            matched = [l for l in lines if regex.search(l)]
        return ParseResult(lines=lines, matched=matched, raw=result.output)

    def __enter__(self):
        if not self.is_open:
            self.connect()
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Module-level convenience APIs (backward compatibility)
# ---------------------------------------------------------------------------

_default_session = SerialSession()


def connect(device: Optional[str] = None, baud: int = DEFAULT_BAUD) -> None:
    """Open (or reopen) the default serial connection."""
    _default_session.connect(device, baud)


def disconnect() -> None:
    """Close the default serial connection if open."""
    _default_session.close()


def ensure_connection() -> serial.Serial:
    """Return the open default connection or raise if not connected."""
    return _default_session._ensure_open()


def cli(command: str, timeout: Optional[float] = None) -> SerialResult:
    """Send *command* over the default connection and return output."""
    return _default_session.cli(command, timeout)


def run(device: str, baud: int, command: str, timeout: Optional[float] = None) -> SerialResult:
    """Open connection, run *command*, close. One-shot helper."""
    session = SerialSession(device, baud)
    try:
        session.connect()
        return session.cli(command, timeout)
    finally:
        session.close()


def stream(
    command: str,
    timeout: Optional[float] = None,
    chunk_size: int = 256,
    filter_fn: Optional[Callable[[str], str]] = None,
) -> Iterator[str]:
    """Yield output from the default connection incrementally."""
    yield from _default_session.stream(command, timeout, chunk_size, filter_fn)


def parse(
    command: str,
    pattern: Optional[str] = None,
    timeout: Optional[float] = None,
) -> ParseResult:
    """Run *command* on the default connection and return parsed output."""
    return _default_session.parse(command, pattern, timeout)


def interrupt(timeout: Optional[float] = None) -> bool:
    """Send Ctrl+C on the default connection to interrupt a running command.

    Returns True if a prompt was detected, False if timeout elapsed.
    """
    return _default_session.interrupt(timeout)


def reconnect() -> None:
    """Reopen the default serial connection after a device reboot."""
    _default_session.reconnect()


# ---------------------------------------------------------------------------
# Persistent defaults
# ---------------------------------------------------------------------------

def save_default(device: str, baud: int) -> None:
    """Persist default device/baud so subsequent CLI invocations can omit them."""
    import json

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"device": device, "baud": baud}))


def load_defaults() -> dict:
    """Return saved defaults (or empty dict if none exist)."""
    import json

    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}
