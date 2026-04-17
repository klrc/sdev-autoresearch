# sdev

Small toolkit for automating a serial-attached Linux shell.

## Installation

```bash
pip install -e .
```

## CLI

```bash
# Run a command
sdev -p "ls /proc/meminfo" -d /dev/ttyUSB0 -b 115200

# Stream output incrementally
sdev -p "tail -f /var/log/syslog" --stream

# Stream with server-side regex filter
sdev -p "tail -f /var/log/syslog" --stream --grep "ERROR"

# Parse output with regex
sdev -p "cat /proc/meminfo" --parse "Mem.*"

# Save defaults so you can omit -d and -b
sdev set-default /dev/ttyUSB0 115200
sdev -p "ls /proc/meminfo"

# Send Ctrl+C to interrupt a running command (without -p)
sdev --interrupt -d /dev/ttyUSB0 -b 115200
```

## Design Goals

- **Stability**: strict 5-minute timeout on all blocking operations
- **Simplicity**: small surface area, obvious API
- **Predictability**: prompt detection to determine command completion
- **Streaming**: incremental output for long-running commands
- **Parsing**: structured output with optional regex filtering

## Python API

```python
import sdev

# Session-based (recommended)
with sdev.SerialSession("/dev/ttyUSB0", 115200) as session:
    result = session.cli("ls /proc/meminfo")
    print(result.output)

# Custom prompt detection for non-standard shells
session = sdev.SerialSession("/dev/ttyUSB0", 115200, prompts=[b"[root@board]# "])
session.connect()

# Streaming for long-running commands
for chunk in session.stream("tail -f /var/log/syslog"):
    print(chunk, end="")

# Streaming with line mode — only yields complete lines
for line in session.stream("tail -f /var/log/syslog", line_mode=True):
    process(line)

# Parsing with regex filtering
parsed = session.parse("cat /proc/meminfo", pattern=r"Mem.*")
print(parsed.matched)

# Wait for a specific output marker instead of shell prompt
# Useful for benchmarks that print results then keep running
result = session.cli("./mnn_perf -m model.mnn", end_flag="Frame rate:")

# Interrupt a running command (sends Ctrl+C and waits for prompt)
session.interrupt(timeout=5)

# Recover from device reboot without creating a new session
session.reconnect()
```

### Thread safety

Each `SerialSession` has an internal `threading.Lock`.  Only one `cli()`
or `stream()` call can run at a time per session.  Concurrent callers
will raise `RuntimeError` after 10s if the lock is held.  `interrupt()`
does not acquire the lock — it remains the emergency escape hatch.

### Module-level convenience API

```python
sdev.connect("/dev/ttyUSB0", 115200)
result = sdev.cli("ls /proc/meminfo")
sdev.disconnect()
```

## License

MIT
