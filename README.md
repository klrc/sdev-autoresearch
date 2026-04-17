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

# Parsing with regex filtering
parsed = session.parse("cat /proc/meminfo", pattern=r"Mem.*")
print(parsed.matched)

# Interrupt a running command (sends Ctrl+C and waits for prompt)
session.interrupt(timeout=5)

# Recover from device reboot without creating a new session
session.reconnect()

# Module-level convenience API
sdev.connect("/dev/ttyUSB0", 115200)
result = sdev.cli("ls /proc/meminfo")
sdev.disconnect()
```

## License

MIT