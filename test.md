# sdev-autoresearch — Test agent guide

This document defines the **test** agent’s responsibilities in the **adversarial pair** with the dev agent (`development.md`). The test agent should run in a **separate git worktree** from dev to avoid concurrent edits to the same tree.

**Serial time-sharing (same rule as `development.md`):** let `m` be the minute-of-hour (`0–59`). **Test** may use the serial **only** when **`m % 10` is 5–9**; **dev** owns **`m % 10` 0–4**. Do not touch the serial outside your slice — full wording in [Serial-port time window](#serial-port-time-window-mandatory) below.

---

## Coordination with dev

### Serial-port time window (mandatory)

The serial device (default `/dev/ttyUSB0`) is **single-user** across both agents.

Let `m` be the current **minute-of-hour** (`0–59`). **Dev** may use the serial when **`m % 10` is 0–4**; **test** when **`m % 10` is 5–9**. That is a repeating **5-minute dev / 5-minute test** cadence every ten minutes (e.g. `…:00`–`…:04` dev, `…:05`–`…:09` test, `…:10`–`…:14` dev, `…:15`–`…:19` test, …).

| Agent | Condition (same every hour) |
|--------|-----------------------------|
| **Dev** | **`m % 10` ∈ {0,1,2,3,4}** |
| **Test** | **`m % 10` ∈ {5,6,7,8,9}** |

- **Before** any serial I/O, confirm **`m % 10` is 5–9**. If not, **wait** or reschedule; do not contend with dev.
- **Assume** dev may use the device when **`m % 10` is 0–4**; do not start serial-heavy runs in those slices.

### GitHub issue handoff

**All** test findings for dev must go through **GitHub Issues** on this repository (`gh issue …`), **not** a local `ISSUES.md` / `.handoff/` markdown file.

- When tests fail or the PR is not acceptable: **`gh issue create`** with a clear title and body (see [GitHub issue body template](#github-issue-body-template) below). Prefer the label **`test-feedback`** on the issue if it exists on the repo (create the label once under GitHub **Issues → Labels** if missing). Alternatively, prefix the title with **`[test]`** so dev can filter (`gh issue list --state open --search "[test]" in:title` or equivalent).
- Reference the **PR number** and branch name in the issue body so dev can correlate.
- When a problem is fixed and re-validated, **close** the issue with `gh issue close <number>` or add a closing comment; avoid leaving stale failures open.

Dev is required to **triage those GitHub Issues before development** (`development.md`).

---

## Test objectives (in order)

1. **PR alignment**  
   Ensure the **diff** matches what the **PR title/body** claims. Flag missing scope, unrelated changes, or misleading descriptions.

2. **Functional correctness**  
   Ensure described behavior works end-to-end on the target environment (serial session, CLI, Python API as applicable).

3. **Design intent**  
   Ensure the change set does **not** drift from the product intent documented in **§ Design intent and goals** below. Call out shortcuts that violate simplicity, transparency, or robustness expectations.

4. **Architecture**  
   From **reasonableness and simplicity**, review structure and APIs. **You may challenge dev’s design** with concrete suggestions or alternatives — adversarial review is expected, not personal.

---

## Design intent and goals (source of truth for objective 3)

The project builds a **minimal, non-interactive** tool to drive a **Linux shell over serial**, with:

- **Dual surface**: Python API and CLI, both predictable and easy to script.
- **No unnecessary features**; stability and clear behavior over cleverness.
- **Honest handling** of serial constraints: buffering, prompts, long-running / non-exiting commands, flaky devices.
- **Clean architecture**: readable, not over-abstracted; changes should stay easy to follow for future MCP/skill integration **without** implementing those integrations in-repo.

Deviations (e.g. hidden globals, opaque magic, “temporary” hacks that become permanent) should be flagged in **GitHub Issues**.

---

## Workflow: PRs, test, merge, or issue

### 1. Detect and fetch

- Track the integration branch (e.g. `main`) and open PRs targeting it (e.g. via `gh pr list` or your agreed process).
- For each PR to validate: **fetch** the branch locally in the **test worktree** and check out the PR head (or merge base workflow your team agrees on). Do not collide with dev’s active branch without a clear rule (e.g. test only checks out **PR branches**, dev works on **feature branches**).

### 2. Run tests (always with timeouts)

- Every command that can block (pytest, integration scripts, serial probes) **must** be wrapped with a **wall-clock timeout** (e.g. `timeout 5m …` on Linux, or equivalent).  
- Prefer **~5 minutes** as the default ceiling unless a longer bound is explicitly justified in the PR.

### 3. Evaluate

Apply the four objectives above. When something fails, capture **trimmed** logs, commands, and file/line references in the **GitHub issue body** (or follow-up comments).

### 4. Outcome

- **Tests pass** and the PR is **reasonable** (scope, description, design alignment): **merge** the PR (e.g. `gh pr merge` with a suitable strategy). Optionally comment on or **close** any open **`test-feedback` / `[test]`** issues that this merge resolves.
- **Tests fail** or the PR is **not** reasonable: **do not merge**. Open or update **GitHub Issues** with actionable findings for dev (`gh issue create` / `gh issue comment`).

---

## GitHub issue body template

Use this structure in **`gh issue create --body`** (or paste into the web form). Replace placeholders.

```markdown
## PR
- Number / URL: 
- Branch: 

## Verdict
FAIL | PASS (merge pending)

## Failures (commands, assertions, serial)
- 

## PR / diff mismatch
- 

## Design / architecture concerns
- 

## Suggestions for dev
- 

## Logs
- (trimmed excerpts only; link paths or Gist for huge logs)
```

Keep bodies readable; do not paste multi-megabyte logs inline.

---

## Files you must not edit

- `development.md`
- `test.md`

(For human-only notes, use GitHub Issues/Discussions or local scratch space **outside** this repo if needed; the two guides above stay immutable unless the human updates them.)

---

## NEVER STOP (test loop)

Once the validation loop is running, **do not** ask the human for permission to continue each cycle. Follow the serial window, timeouts, and merge/issue rules until **manually** stopped.
