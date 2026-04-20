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

# Stream with complete-line output only
sdev -p "dmesg" --stream --line-mode

# Parse output with regex
sdev -p "cat /proc/meminfo" --parse "Mem.*"

# Wait for a specific output marker instead of shell prompt
sdev -p "./mnn_perf -m model.mnn" --end-flag "Frame rate:"

# Clear stray processes before running a command
sdev -p "uptime" --doctor

# Save defaults so you can omit -d and -b
sdev set-default /dev/ttyUSB0 115200
sdev -p "ls /proc/meminfo"

# Send Ctrl+C to interrupt a running command (without -p)
sdev --interrupt -d /dev/ttyUSB0 -b 115200

# Detect serial boards on this system
sdev --probe
sdev --probe --probe-baud 9600 --probe-baud 38400

# Custom prompt patterns for non-standard shells
sdev -p "ls" --prompt "[root@board]# " --prompt "admin@box> "
```

### CLI options

| Flag | Description |
|------|-------------|
| `-p, --command` | Command to execute |
| `-d, --device` | Serial device path |
| `-b, --baud` | Baud rate |
| `-t, --timeout` | Timeout in seconds (default: 300) |
| `--stream` | Incremental output instead of buffered |
| `--grep REGEX` | Filter `--stream` lines by regex |
| `--line-mode` | Only yield complete lines in `--stream` |
| `--parse REGEX` | Show only matching lines |
| `--end-flag STR` | Stop when this string appears in output |
| `--doctor` | Clear foreground processes before command |
| `--prompt PATTERN` | Custom shell prompt pattern (repeatable) |
| `--interrupt` | Send Ctrl+C and wait for prompt |
| `--probe` | Detect serial boards and print info |
| `--probe-baud BAUD` | Baud rates to try during `--probe` (repeatable) |
| `set-default` | Persist device/baud as defaults |

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

# Streaming with server-side filter
for chunk in session.stream("tail -f /var/log/syslog", filter_fn=lambda t: t.upper()):
    print(chunk, end="")

# Parsing with regex filtering
parsed = session.parse("cat /proc/meminfo", pattern=r"Mem.*")
print(parsed.matched)

# Wait for a specific output marker instead of shell prompt
# Useful for benchmarks that print results then keep running
result = session.cli("./mnn_perf -m model.mnn", end_flag="Frame rate:")

# Interrupt a running command (sends Ctrl+C and waits for prompt)
session.interrupt(timeout=5)

# Clear stray foreground processes and get a clean prompt
session.doctor()

# Wait until no data arrives for N seconds (boot completion)
session.wait_for_silence(timeout=1.5)

# Recover from device reboot without creating a new session
session.reconnect()

# Monitor CPU/memory during long operations
usage = sdev.resource_usage()
print(f"RSS: {usage['memory_mb']} MB, CPU: {usage['cpu_percent']}%")

# Detect serial boards and get OS/arch info
for device in sdev.probe():
    print(f"{device['device']} @ {device['baud']}: {device['info']['os_name']}")

# Send raw bytes over serial (control sequences, custom protocols)
sdev.connect("/dev/ttyUSB0", 115200)
n = sdev.write(b"reboot\n")
print(f"Wrote {n} bytes")

# Clear stray foreground processes on the default connection
sdev.doctor()

# Wait for boot completion (no serial data for N seconds)
sdev.wait_for_silence(timeout=2.0)
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
