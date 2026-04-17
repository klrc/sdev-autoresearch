# sdev-autoresearch — Dev agent guide

This experiment runs **two Claude Code CLI agents in adversarial collaboration**: a **dev** agent (this guide) and a **test** agent (`test.md`). Work should happen in **separate git worktrees** so the two agents do not clobber the same working tree.

---

## Before you start (every development session)

1. **Read outstanding test feedback**  
   Before writing or changing code, check the latest issues from the test agent (see paths and format in `test.md`). Resolve or acknowledge each item before moving on.

2. **Respect the serial-port time window (shared device)**  
   **Dev may use the serial device only during minutes 0–29 of each clock hour** (e.g. `10:00`–`10:29`). **Do not** open or use `/dev/ttyUSB0` (or the configured device) during minutes 30–59 — that window is reserved for the test agent.  
   If you are inside a long run that would cross into the test window, **stop using the serial** before `:30` or schedule work accordingly.

---

## Setup (new experiment)

Work with the user when bootstrapping:

1. **Branch**  
   Create a branch from current `main` (or agreed default):  
   `git checkout -b autoresearch/<branch-name>`.

2. **Serial**  
   Verify `/dev/ttyUSB0` is available. If not:
   - Check for duplicate holders / conflicting processes.
   - If the device behaves oddly, consider sending multiple **Ctrl+C** on the serial line, then a **reboot** command and waiting ~30s for the board to reset.

3. **Confirm**  
   Once setup looks good and the user confirms, start development.

---

## Development goal

Build a **small, obvious, intuitive, transparent, non-interactive** toolkit to automate a **serial-attached Linux shell**, with both **Python** and **CLI** entry points — suitable for quick board demos and later MCP/skill wiring (you do **not** implement MCP/skills; design with that use case in mind).

**Illustrative API** (you may refine names and shape; document changes in commits/PRs):

```python
import sdev

sdev.connect("/dev/ttyUSB0", 115200)
sdev.cli("ls /proc/meminfo")
```

```bash
sdev -p "ls /proc/meminfo" -d /dev/ttyUSB0 -b 115200

sdev set-default /dev/ttyUSB0 115200
sdev -p "ls /proc/meminfo"
```

Keep interfaces as simple and honest as possible; avoid flashy features. Priorities: **stability**, **simplicity**, **predictability**, and **robust handling of weird real-world serial behavior**.

While building, stay aware of serial realities: limited buffers (read promptly / buffer?), prompt detection, programs that never exit on their own (e.g. `top`), etc. These are examples — expect more edge cases in practice.

Internally, aim for **robust code**, **no over-engineering**, **readability**, and **sound architecture**. Prefer structural fixes over one-off hacks. Think from the whole design, not only the symptom in front of you.

---

## Files you must not edit

- `development.md`
- `test.md`

---

## Timeouts

All debugging and self-tests that could hang **must** use a **strict timeout** on the order of **~5 minutes**, so a stuck board or command cannot block the dev loop indefinitely.

---

## Commit and PR workflow

- Maintain a sensible `.gitignore`; do not commit secrets, huge logs, or local venv artifacts.
- Self-test before commit where applicable.
- Open a **PR toward `main`** (or the agreed integration branch). Describe what changed on this branch in the PR body.

---

## NEVER STOP

Once the experiment loop has started (after initial setup), **do not** pause to ask the human whether to continue. **Do not** ask “should I keep going?” or “is this a good stopping point?” The human may be away and expects work to continue until **manually** stopped.
