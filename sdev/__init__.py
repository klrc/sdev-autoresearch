"""sdev — small toolkit for automating a serial-attached Linux shell.

Python API::

    import sdev
    sdev.connect("/dev/ttyUSB0", 115200)
    result = sdev.cli("ls /proc/meminfo")
    print(result.output)

CLI::

    sdev -p "ls /proc/meminfo" -d /dev/ttyUSB0 -b 115200
    sdev set-default /dev/ttyUSB0 115200
    sdev -p "ls /proc/meminfo"          # uses saved defaults
"""

import os
import time
import serial
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 300  # 5 minutes — strict cap on blocking operations
DEFAULT_BAUD = 115200
DEFAULT_DEVICE = "/dev/ttyUSB0"
CONFIG_DIR = Path.home() / ".config" / "sdev"
CONFIG_FILE = CONFIG_DIR / "defaults.json"


@dataclass
class SerialResult:
    """Output from a single command execution."""

    command: str
    output: str
    timed_out: bool
    elapsed: float


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_connection: Optional[serial.Serial] = None
_baud: int = DEFAULT_BAUD
_device: str = DEFAULT_DEVICE


def connect(device: Optional[str] = None, baud: int = DEFAULT_BAUD) -> None:
    """Open (or reopen) the serial connection.

    If a connection is already open it is closed first so callers can
    reconnect to a device that may have reset.
    """
    global _connection, _baud, _device

    _device = device or _device
    _baud = baud

    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None

    _connection = serial.Serial(_device, _baud, timeout=0.1)
    # Drain any leftover noise from the buffer
    time.sleep(0.5)
    _connection.reset_input_buffer()
    _connection.reset_output_buffer()


def ensure_connection() -> serial.Serial:
    """Return the open connection or raise if not connected."""
    if _connection is None or not _connection.is_open:
        raise RuntimeError(
            f"Not connected. Call sdev.connect('{_device}', {_baud}) first."
        )
    return _connection


# ---------------------------------------------------------------------------
# Prompt detection
# ---------------------------------------------------------------------------

# Common shell prompts — we consider output "done" when we see one of these
# at the end of the buffer.  Callers can also rely on a timeout.
PROMPTS = [b"# ", b"$ ", b"> ", b"~# ", b"~$ "]


def _prompt_detected(buf: bytes) -> bool:
    """Return True if a known shell prompt appears at the tail of *buf*."""
    stripped = buf.rstrip(b"\r\n")
    for p in PROMPTS:
        if stripped.endswith(p):
            return True
    return False


# ---------------------------------------------------------------------------
# Core command execution
# ---------------------------------------------------------------------------

def cli(command: str, timeout: Optional[float] = None) -> SerialResult:
    """Send *command* over serial and return its output.

    Waits until a shell prompt reappears or *timeout* seconds elapse
    (default: :data:`DEFAULT_TIMEOUT` — 5 minutes).

    Returns a :class:`SerialResult` with ``output``, ``timed_out``, and
    ``elapsed``.
    """
    ser = ensure_connection()
    deadline = (timeout or DEFAULT_TIMEOUT)
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

        # Read whatever is available (non-blocking, timeout=0.1 on the port)
        chunk = ser.read(4096)
        if chunk:
            buf.extend(chunk)
            if _prompt_detected(bytes(buf)):
                break
        else:
            # Nothing to read — sleep briefly to avoid a tight loop
            time.sleep(min(0.1, remaining))

    elapsed = time.monotonic() - start
    return SerialResult(
        command=command,
        output=bytes(buf).decode(errors="replace"),
        timed_out=timed_out,
        elapsed=round(elapsed, 2),
    )


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


# ---------------------------------------------------------------------------
# Convenience: connect + one-shot command
# ---------------------------------------------------------------------------

def run(device: str, baud: int, command: str, timeout: Optional[float] = None) -> SerialResult:
    """Open connection, run *command*, close connection. One-shot helper."""
    connect(device, baud)
    try:
        return cli(command, timeout)
    finally:
        if _connection is not None:
            _connection.close()
