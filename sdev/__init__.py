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

import os
import time
import re
import serial
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Iterator, Callable


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

PROMPTS = [b"# ", b"$ ", b"> ", b"~# ", b"~$ "]


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

    def __init__(self, device: str = DEFAULT_DEVICE, baud: int = DEFAULT_BAUD):
        self._connection: Optional[serial.Serial] = None
        self.device = device
        self.baud = baud

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

        self._connection = serial.Serial(self.device, self.baud, timeout=0.1)
        time.sleep(0.5)
        self._connection.reset_input_buffer()
        self._connection.reset_output_buffer()

    def _ensure_open(self) -> serial.Serial:
        if not self.is_open:
            raise RuntimeError(
                f"Not connected. Call connect('{self.device}', {self.baud}) first."
            )
        return self._connection  # type: ignore

    def close(self) -> None:
        """Close the serial connection if open."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def cli(self, command: str, timeout: Optional[float] = None) -> SerialResult:
        """Send *command* over serial and return its output.

        Waits until a shell prompt reappears or *timeout* seconds elapse.
        """
        ser = self._ensure_open()
        deadline = timeout or DEFAULT_TIMEOUT
        start = time.monotonic()

        ser.reset_input_buffer()
        ser.write((command + "\n").encode())
        ser.flush()

        buf = bytearray()
        timed_out = False

        while True:
            remaining = deadline - (time.monotonic() - start)
            if remaining <= 0:
                timed_out = True
                break

            chunk = ser.read(4096)
            if chunk:
                buf.extend(chunk)
                if _prompt_detected(bytes(buf)):
                    break
            else:
                time.sleep(min(0.1, remaining))

        elapsed = time.monotonic() - start
        return SerialResult(
            command=command,
            output=bytes(buf).decode(errors="replace"),
            timed_out=timed_out,
            elapsed=round(elapsed, 2),
        )

    def stream(
        self,
        command: str,
        timeout: Optional[float] = None,
        chunk_size: int = 256,
        filter_fn: Optional[Callable[[str], str]] = None,
    ) -> Iterator[str]:
        """Yield output incrementally as it arrives.

        Suitable for long-running commands or large output where buffering
        the entire transcript in memory is impractical.

        Yields decoded string chunks.  Stops when *timeout* elapses.

        *filter_fn*: optional callable applied to each chunk before yielding.
        """
        ser = self._ensure_open()
        deadline = timeout or DEFAULT_TIMEOUT
        start = time.monotonic()

        ser.reset_input_buffer()
        ser.write((command + "\n").encode())
        ser.flush()

        while True:
            remaining = deadline - (time.monotonic() - start)
            if remaining <= 0:
                break

            chunk = ser.read(chunk_size)
            if chunk:
                text = chunk.decode(errors="replace")
                if filter_fn:
                    text = filter_fn(text)
                yield text
                if _prompt_detected(chunk):
                    break
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


def ensure_connection() -> serial.Serial:
    """Return the open default connection or raise if not connected."""
    return _default_session._ensure_open()


def cli(command: str, timeout: Optional[float] = None) -> SerialResult:
    """Send *command* over the default connection and return output."""
    return _default_session.cli(command, timeout)


def run(device: str, baud: int, command: str, timeout: Optional[float] = None) -> SerialResult:
    """Open connection, run *command*, close. One-shot helper."""
    session = SerialSession(device, baud)
    session.connect()
    try:
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
