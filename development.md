# sdev-autoresearch — Dev agent guide

This experiment runs **two Claude Code CLI agents in adversarial collaboration**: a **dev** agent (this guide) and a **test** agent (`test.md`). Work should happen in **separate git worktrees** so the two agents do not clobber the same working tree.

---

## Before you start (every development session)

1. **Read outstanding test feedback (GitHub Issues)**  
   Before writing or changing code, review **open GitHub Issues** created by the test workflow for this repository. Use the GitHub CLI, e.g. `gh issue list --state open` (and the filters or labels described in `test.md`). **Do not** rely on a local markdown handoff file for test feedback. Triage each relevant issue: fix, comment with evidence, or close with `gh issue close <number>` when resolved. Do not ignore open issues from the test agent.

2. **Respect the serial-port time window (shared device)**  
   Use **minute-of-hour modulo 10**: let `m` be the current minute within the hour (`0–59`). **Dev** may use the serial only when **`m % 10` is 0–4** (e.g. `…:00`–`…:04`, `…:10`–`…:14`, `…:50`–`…:54`). **Test** uses **`m % 10` 5–9** (e.g. `…:05`–`…:09`, `…:15`–`…:19`, `…:55`–`…:59`). Same **5-minute dev / 5-minute test** pattern repeats every ten minutes all hour.  
   **Do not** open or use `/dev/ttyUSB0` (or the configured device) when `m % 10` is **5–9**. If a serial operation would cross from **`m % 10 ≤ 4`** into **`m % 10 ≥ 5`**, **stop or yield before** that boundary (e.g. finish by `…:04` if you are in a dev slice ending at `…:04`).

3. **Sync `main` before you implement**  
   At the start of a dev stint (and before cutting a **new** feature branch), run:  
   `git fetch origin && git checkout main && git pull origin main`  
   so you have the latest `development.md` / `test.md`, merged fixes, and any updates landed on `main`. Then `git checkout <your-feature-branch>` and **merge `main` into it** (or **rebase** onto `main` if the human asked for a linear history).  
   You generally **do not** “pull a rejected branch” as if it were canonical: if a PR was **closed without merge**, treat **`main` as source of truth**—read the **PR thread and linked GitHub Issues** (`gh pr view`, `gh issue list`) for why, then re-sync your work from up-to-date `main` (new branch from `main` or rebase) unless the human says otherwise.

4. **Silence from test is not permission to idle**  
   After triaging GitHub Issues: if the test agent has **not** opened any relevant **`[test]` / `test-feedback`** items (or the list is empty), **do not treat that as a break**. On your own initiative, ask whether the project can be **improved** against this guide and **`README.md`**: robustness, API/CLI clarity, missing coverage, docs drift, error messages, timeout behavior, or small refactors that reduce complexity. Pick the **next most valuable** slice of work, implement it with the usual self-test and PR discipline, and explain the rationale in the PR body. **Waiting for test to file an issue is not an excuse to stop making progress.**

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

### Execution, parsing, and streaming

Real usage is not only **executing** shell commands over serial but also **receiving, reading, and parsing** command output; automation scripts almost always pair execution with parsing (structured lines, regex, state machines, etc.).

**Streaming** (incremental read / async consumption) should be a first-class design consideration for **very long output** or **long-running commands**, so callers are not forced to buffer entire transcripts in memory and can react progressively.

> **Human-directed documentation update**  
> A GitHub issue was opened by the human operator to record this scope: see [GitHub issue #2](https://github.com/klrc/sdev-autoresearch/issues/2). Agents must **not** treat this expansion as erroneous feedback from the test agent or revert it as a "mistake".

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
