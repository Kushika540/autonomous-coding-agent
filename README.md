# Autonomous Coding Agent

**An LLM agent that reads a bug report, explores a real codebase, writes a fix, and verifies it by running the actual test suite — no human writes the fix.**

🎯 **100% success rate** across 10 independently-verified bugs (easy → hard tiers, 3 separate runs)
🔧 **Real GitHub integration** — reads live issues, opens real pull requests
🛠️ **Built from scratch** — no agent framework, own tool-use loop, own eval harness
💰 **Zero-cost stack** — runs entirely on free-tier infrastructure (Groq)
🐛 **8+ documented production-grade bugs found and fixed** along the way (rate limits, malformed model output, file corruption, encoding issues) — see the full debugging log below

An agent that reads a bug report, explores a codebase, writes a fix, and
verifies its own work by running the test suite — looping until tests pass.

Built as a learning + portfolio project to understand agentic AI systems
from first principles (no framework abstracting away the loop).

## Problem Statement

Debugging follows a well-defined loop: read the failure, explore the
codebase, form a hypothesis, write a fix, verify it against tests. It's
mechanical enough to describe precisely, but a single LLM prompt can't
replicate it — real debugging is iterative, and a model that can't
explore code or check its own work will confidently produce fixes that
are subtly wrong.

This project asks a scoped question: can an LLM, given tools to
explore, edit, and test a real codebase, iterate on its own until it
*verifiably* fixes a bug — without a human checking each step? That's
the same mechanism (plan → act → verify) underlying production tools
like GitHub Copilot Workspace, Devin, and Claude Code. The goal here
isn't to replace an engineer — it's to build and honestly evaluate a
system that handles the mechanical part of debugging so a human's time
goes to review and judgment, not typing.

## Tech Stack

| Component | Choice | Why |
|---|---|---|
| Language | Python | Standard for agent tooling, fast to iterate in |
| LLM inference | Groq (`openai/gpt-oss-20b`) | Free, no card required, built for reliable tool use |
| LLM client | `openai` SDK | Free providers (Groq, Google AI Studio, Ollama) all speak the OpenAI-compatible API — one client, swap `base_url` to change provider |
| File sandboxing | Path-scoped Python functions | Cheap, sufficient isolation for local file access |
| Shell sandboxing (upgrade path) | Docker | Real isolation boundary — network/resource limits enforced by the container, not app code |
| Testing | `pytest` | Gives the agent unambiguous pass/fail signal |
| Logging | JSONL to disk | Simple, greppable, feeds directly into an eval harness |

Planned next: a small evaluation harness (10-20 bugs, measured success
rate), GitHub API integration for real issues/PRs, and semantic code
search for repos too large to read file-by-file.

## Architecture

```
 Task description
        |
        v
  +-----------+      tool calls       +------------------------+
  |    LLM    | --------------------> |  Tools (agent/tools.py) |
  | (planner  |                       |  read_file               |
  |  + coder) | <-------------------- |  write_file               |
  +-----------+     tool results      |  list_dir                 |
        |                             |  run_shell_command         |
        | "DONE: ..."                 +------------------------+
        v                                        |
   Success, loop ends               scoped to sandbox_repo/
                                     (Docker isolation optional, see docker/)
```

The loop lives in `agent/agent_loop.py`:
**plan → call tools → observe results → repeat**, capped at `MAX_ITERATIONS`
so a confused agent can't run forever.

## Why these design choices

- **Diffs over full rewrites for feedback, but full-file writes under the
  hood** — `write_file` takes complete new content (simpler and more
  reliable for a v1 than patch/diff application) but returns a unified
  diff so you can see exactly what changed in the logs.
- **Path-scoped tools** — every file tool refuses to read/write outside
  `sandbox_repo/`. This is a deliberate safety boundary, not an
  afterthought.
- **Docker sandbox for shell commands** (`docker/Dockerfile`) — the real
  isolation boundary for arbitrary shell execution. Path-scoping stops
  file *access*, but only a container stops network calls, resource
  exhaustion, or `pip install`-ing something unexpected.
- **Iteration cap + structured logging** — every reasoning step and tool
  call is logged to `logs/run.jsonl`. This is what lets you build the
  evaluation harness next (see Roadmap).

## Known issues encountered and fixed

Building and running this against a real free-tier API surfaced several
concrete failure modes, each fixed at the code level (not just worked
around by hand). Full story in **Debugging Session Log** below; short
version:

- **Malformed tool calls** — Groq's Llama-family models occasionally
  emit invalid structured output (`tool_use_failed` / `output_parse_failed`).
  Fixed with model choice (`openai/gpt-oss-20b`, built for reliable tool
  use) plus automatic retry at temperature 0.
- **Hallucinated tool parameters** — the model sometimes guesses
  plausible-but-nonexistent arguments (`depth`, `line_start`). Tools now
  accept and ignore unexpected kwargs instead of crashing; useful ones
  (`line_start`/`line_end`) were implemented for real.
- **File corruption from copied formatting** — the model once copied
  `read_file`'s line-number display formatting directly into
  `write_file`, corrupting the file. `write_file` now detects and
  strips that pattern automatically as a safety net, on top of a
  clearer system prompt.
- **Free-tier rate limiting** — 429 errors now parse Groq's suggested
  wait time and retry automatically instead of failing the run.
- **Iteration budget exhausted right after success** — the agent once
  re-verified a passing test suite instead of stopping, burning its
  last iteration before it could report `DONE:`. Fixed by raising the
  cap and instructing the model to stop immediately on one clean pass.

This is also genuinely good interview material: production LLM systems
have to handle imperfect model output gracefully, and being able to
describe *how* you detected and fixed each of these is a real
engineering story, not a toy one.

## Setup (100% free, no credit card required)

This project uses **Groq** by default — a free LLM API with fast inference
and full tool-calling support, no credit card ever required.

```bash
cd coding-agent
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Get a free Groq API key:
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up with email or Google (no card needed)
3. Create an API key under API Keys

```bash
export GROQ_API_KEY=gsk_your-key-here     # Windows PowerShell: $env:GROQ_API_KEY = "gsk_..."
```

### Alternative free providers (no code changes needed, just env vars)

If Groq's free-tier limits ever get tight, swap providers by setting
different environment variables — the code itself doesn't change, since
it talks to any OpenAI-compatible endpoint:

**Google AI Studio** (free, no card, huge 1M-token context):
```bash
export LLM_API_KEY=your-google-ai-studio-key
export AGENT_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export AGENT_MODEL=gemini-2.0-flash
```
Get a key at [aistudio.google.com](https://aistudio.google.com) — no card required.

**Local Ollama** (completely free forever, runs on your own machine, no
internet needed after setup — good if you want zero dependency on any
provider's rate limits):
```bash
# Install Ollama from ollama.com, then:
ollama pull llama3.1
ollama serve

export AGENT_BASE_URL=http://localhost:11434/v1
export AGENT_MODEL=llama3.1
export LLM_API_KEY=ollama   # any non-empty placeholder works locally
```
Note: local models are slower and less capable than Groq's hosted Llama
3.3 70B, especially on a laptop without a GPU — expect more retries
before the agent succeeds. Fine for learning, worth knowing about for
the "I understand my dependencies" interview answer.

## Run it

```bash
cd agent
python agent_loop.py
```

This runs the default task against `sandbox_repo/`, which has a
deliberately planted bug in `stringutils.py`
(`is_palindrome` compares a string to itself instead of its reverse).
Watch the agent explore the repo, find the failing test, diagnose the
bug, fix it, and re-run tests to confirm.

You can also give it a custom task:

```bash
python agent_loop.py "There's a bug in the vowel counting logic, find and fix it"
```

Check `logs/run.jsonl` afterward to see the full trace of reasoning and
tool calls — this is your raw material for a demo write-up.

## Evaluation harness

Beyond the single-bug demo above, `eval/` runs the agent against ten
varied, pre-verified bugs (different modules, different bug types,
across easy/medium/hard difficulty) and reports a measured success
rate — not just a demo, an actual number.

```bash
cd eval
python eval_harness.py
```

For each bug, the harness:
1. Resets `sandbox_repo/` to that bug's exact buggy files
2. Runs the full agent loop against it
3. **Independently re-runs pytest itself** to check the real outcome —
   it does not trust the agent's own `DONE:` claim as ground truth

That last point matters: the harness separately tracks *declared done*
(what the agent claims) versus *actual pass* (what really happened),
and reports a **self-assessment accuracy** — how often those two agree.
An agent that's usually right but occasionally claims success on a
test it misread is a different (and more realistic) result than one
that's simply always right or always wrong, and this is the kind of
distinction a real eval should surface.

Results land in:
- `eval/results.jsonl` — one line per bug, full detail
- `eval/results_summary.md` — a readable table + aggregate stats, ready to paste into a README or resume bullet

Bug set (`eval/eval_bugs.py`) — 10 bugs across three tiers:

**Easy/medium (6):** a self-comparison logic bug, an off-by-one
divisor, a vowel-counting edge case, an order-losing dedupe, an
off-by-one slice boundary, and a multi-file bug where the root cause
lives in a different file than the one the failing test imports
directly.

**Hard (4, added after the first two clean 100% runs on the easier
set):** each targets a distinct category of reasoning, not just a
harder version of the same off-by-one pattern —
- `mutable_default_argument` — the classic Python gotcha where a
  mutable default argument (`def f(x, cart=[])`) persists across calls;
  requires recognizing a language-level footgun, not just a typo
- `inverted_priority_sort` — the code runs without error and looks
  plausible, but the sort direction contradicts the docstring's stated
  semantics; requires reading and trusting the spec over the code
- `duplicated_config_constant` — a shared constant already exists in
  `config.py`, but a different file hardcodes its own stale copy;
  requires noticing an unused import context and connecting two files
  rather than just patching the number that's wrong
- `missing_right_subtree_recursion` — a recursive tree-sum function is
  missing its right-branch recursive call entirely; requires reasoning
  about code that's structurally incomplete, not just numerically wrong


## Evaluation Results (measured, not projected)

**Full 10-bug set, run against the live Groq API:**

| Bug ID | Difficulty | Passed | Claimed Done | Iterations | Time (s) |
|---|---|---|---|---|---|
| palindrome_self_compare | easy | ✅ | ✅ | 6 | 64.8 |
| vowel_count_off_by_missing_y | easy | ✅ | ✅ | 10 | 44.0 |
| average_wrong_divisor | medium | ✅ | ✅ | 7 | 34.1 |
| dedupe_loses_order | medium | ✅ | ✅ | 5 | 20.8 |
| multi_file_helper_bug | hard | ✅ | ✅ | 8 | 50.3 |
| chunk_wrong_boundary | medium | ✅ | ✅ | 6 | 20.3 |
| mutable_default_argument | hard | ✅ | ✅ | 6 | 11.3 |
| inverted_priority_sort | hard | ✅ | ✅ | 7 | 28.4 |
| duplicated_config_constant | hard | ✅ | ✅ | 8 | 43.2 |
| missing_right_subtree_recursion | hard | ✅ | ✅ | 7 | 43.0 |

**Success rate: 10/10 (100%). Self-assessment accuracy: 10/10 (100%).**
Avg iterations: 7.0. Avg time/bug: 36.0s.

This is the notable result: **the four hard-tier bugs — a classic
Python mutable-default-argument gotcha, a sort whose logic silently
contradicted its own docstring, a bug requiring the agent to notice and
reuse an existing cross-file constant instead of hardcoding a new
value, and a recursive function missing an entire branch — were solved
just as reliably as the easy ones**, each in roughly the same iteration
budget (6-8). These were deliberately designed to require different
*kinds* of reasoning, not just harder arithmetic, specifically because
the original six-bug set hadn't produced a single failure and a 100%
result against only easy/medium bugs wouldn't have meant much.

(Prior to adding the hard tier, the original 6-bug set was also run
twice independently — 6/6 (100%) both times — establishing that the
100% result was consistent before scaling up the eval, not a one-off.)

**Observed pattern across all runs:** the agent occasionally continues
re-reading and re-verifying a file after the bug is already fixed,
before finally running the test suite and declaring success — iteration
counts ranged from 5 to 10 across otherwise-comparable bugs, with no
clear correlation to actual difficulty (the hardest bug,
`mutable_default_argument`, took only 6 iterations and 11 seconds,
while the easy `vowel_count_off_by_missing_y` took 10). This looks like
the model losing track of whether it had already confirmed its own
work — an efficiency issue, not an accuracy one, but worth investigating
if iteration budget (== API cost) becomes a concern at scale.

## Project status / roadmap

This is a **working, measured system**: tool use + core loop end-to-end,
several robustness fixes in place (malformed tool call retries,
rate-limit handling, hallucinated parameter tolerance, file-corruption
safety net), and a 100% success rate across 10 varied bugs — including
four specifically designed to be hard — confirmed against a live API.

The eval set has effectively **saturated**: the agent hasn't failed a
single bug across three independent runs and 22 total bug-attempts. That's
a genuinely strong result, but it also means the current bug set no
longer discriminates — the next version of the eval needs to be harder
in kind, not just in the individual-bug sense.

Next steps to build on top of this:

1. **Push toward genuinely harder eval scenarios** — the current bugs
   are all single, well-isolated fixes. To find where this agent
   actually breaks, try: bugs requiring coordinated edits across 2+
   files simultaneously (not just reading one extra file for context),
   ambiguous bug reports that don't name the failing test file, or
   tasks that require adding new functionality rather than fixing
   existing logic. A 100% success rate on "well-specified single-file
   fixes" is a real result — the next question is where it stops being
   true.
2. **Investigate the redundant-reverification pattern** — see observed
   pattern above. Could be a system prompt fix, or worth measuring
   whether it's model-specific by testing an eval run against a
   different free model (Gemini via Google AI Studio, or a different
   Groq model) for comparison.
3. ~~**Docker execution**~~ — done, see below.
4. ~~**Real GitHub issues**~~ — done, see below.

## Docker sandboxing: real isolation for shell execution

By default, `run_shell_command` in `tools.py` runs commands in a local
subprocess scoped to the sandbox's working directory. That stops the
agent from reading or writing files outside the sandbox via the other
tools, but it does **not** stop an LLM-generated shell command from
hitting the network, spawning unbounded processes, or touching
anything reachable from an absolute path — `cwd` scoping is a
convenience, not a security boundary.

Setting `AGENT_USE_DOCKER=1` switches `run_shell_command` to run every
command inside a fresh, ephemeral container instead:

```bash
docker run --rm --network none --memory 512m --cpus 1 \
  -v <sandbox>:/workspace -w /workspace \
  coding-agent-sandbox bash -c "<command>"
```

- **`--network none`** — no network access at all, so a compromised or
  simply badly-written command can't exfiltrate anything or hit an
  external service
- **`--memory 512m --cpus 1`** — resource limits enforced by Docker
  itself, not trusted to application code
- **Fresh container per call, not a long-lived one** — simpler
  lifecycle: nothing to clean up if the script crashes mid-run, and no
  state leaks between commands beyond the mounted sandbox directory

### Setup

```bash
docker build -t coding-agent-sandbox -f docker/Dockerfile .
```

Then set the environment variable before running the agent, eval
harness, or GitHub integration — all three use the same `tools.py`, so
this one variable covers all of them:

```bash
export AGENT_USE_DOCKER=1   # Windows PowerShell: $env:AGENT_USE_DOCKER = "1"
python agent_loop.py
```

Unset it (or leave it unset) to fall back to local subprocess
execution — useful for fast local iteration when you don't need the
extra isolation, e.g. while developing new eval bugs.

### Verified without a live Docker daemon

I don't have Docker available in the environment I built this in, so I
verified what's testable without it: local-mode execution is unchanged
(regression tested), the Docker code path fails with a clear, actionable
error if `docker` isn't installed rather than a raw stack trace, and the
constructed `docker run` command was verified argument-by-argument (via
mocking `subprocess.run`) to include the correct isolation flags, the
correct volume mount, and to respect the configured timeout. The actual
container build and live execution is the one piece that needs a real
Docker installation to confirm end-to-end.

## GitHub integration: real issues, real PRs

`github_integration/github_agent.py` points the exact same agent loop
and tools at a real cloned git repository instead of the local demo
sandbox, pulls a real GitHub issue as the task, and — only if the agent
reports success — commits, pushes a branch, and opens a real pull
request.

No new agent logic was needed for this: `tools.py`'s `SANDBOX_ROOT` is
now controlled by an `AGENT_WORKDIR` environment variable (defaulting
to the local `sandbox_repo/` for the demo and eval harness), so
pointing the same read/write/list/run tools at a real repo is just a
matter of setting that variable before import. The agent itself has no
idea whether it's editing a planted bug or a real codebase.

**Safety note:** run this against a repo you own or control first, not
someone else's open-source project — until you've verified the fix
quality yourself, an agent-authored PR on a repo you don't maintain is
a good way to waste a maintainer's time. Use `--dry-run` to do
everything except push and open the PR, so you can inspect the diff
locally first.

### Setup

```bash
pip install -r requirements.txt   # now includes PyGithub
```

Create a GitHub personal access token with `repo` scope at
[github.com/settings/tokens](https://github.com/settings/tokens), then:

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### Usage

```bash
cd github_integration

# Dry run first -- clones, branches, runs the agent, shows you the diff,
# but does NOT push or open a PR
python github_agent.py --repo yourname/your-repo --issue 3 --dry-run

# The real thing -- pushes a branch and opens an actual PR if the agent succeeds
python github_agent.py --repo yourname/your-repo --issue 3
```

What it does, step by step:
1. Fetches the issue's title and body via the GitHub API, uses it as
   the task description (a real bug report, not a synthetic one)
2. Clones the repo (or syncs an existing local clone) into
   `github_integration/clones/`
3. Creates a branch named `agent-fix-issue-<N>`
4. Repoints the existing tools at that clone via `AGENT_WORKDIR` and
   runs the unmodified agent loop against it
5. Only if the agent declares `DONE:` **and** actually changed files,
   commits, pushes, and opens a PR with the agent's own summary in the
   PR body, plus an explicit note that it was AI-authored and needs
   human review before merging
6. If the agent fails or makes no changes, nothing is pushed — the
   local branch is left in place for inspection, and the script exits
   with a clear message rather than silently doing nothing

This was tested end-to-end against a local git repository (branch
creation, change detection, commit, and push all verified working) and
against `tools.py` correctly repointing at a real cloned repo via
`AGENT_WORKDIR` — the GitHub API calls themselves (issue fetch, PR
creation) require a live token and repo to test for real.

## What to say about this project in an interview

- Why you separated tool definitions (schema) from tool implementations
  (functions) — makes it easy to swap the LLM provider or add tools.
- Why you capped iterations and what happens when the cap is hit
  (fails gracefully, logs the state, doesn't hang).
- What failure modes you actually observed (see full log below) and
  how you addressed each one at the code level, not just by hand.
- Why the GitHub integration required zero changes to the agent loop
  or tools themselves — only an environment variable — and why that's
  a sign of a clean separation between "how the agent thinks" and
  "what filesystem it's operating on."
- How you'd extend this further to arbitrary real-world repos (context
  window limits, need for semantic code search instead of full-file
  reads, handling multi-file coordinated changes).

## Debugging Session Log — July 10, 2026

This documents the actual path from "doesn't run" to "clean successful
run," because the debugging process itself is evidence of the skills
this project was meant to demonstrate — none of this was anticipated in
the original design. It was discovered by running the system against a
real free-tier API and diagnosing exactly what broke and why.

**1. Environment setup friction (Windows/PowerShell).** Initial setup
used bash syntax (`&&`, `export`) that doesn't work in PowerShell 5.1.
Also hit a split-environment issue where `python` correctly resolved to
the project's venv but bare `pip` resolved to a different, global
Python — so packages weren't visible to the venv's `python`. Fixed by
always invoking `python -m pip` instead of bare `pip`.

**2. Paid API blocker.** The initial design called the Anthropic API
directly. Once a no-cost constraint was set, the project was
re-architected around the OpenAI-compatible chat completions API so it
runs against free providers (Groq by default) with zero code changes
to swap providers — only environment variables.

**3. Malformed tool calls (`tool_use_failed`).**
`llama-3.3-70b-versatile` on Groq intermittently emitted tool calls in
a non-standard pseudo-XML format that Groq's API rejects outright — a
documented, known issue with that model family on Groq, not a bug in
this code. Fixed by switching the default model to `openai/gpt-oss-20b`
(built specifically for reliable agentic tool use) and adding retry
logic with temperature forced to 0 on failure (Groq's own documented
mitigation).

**4. A second variant of the same failure (`output_parse_failed`).**
Even after the model switch, a related but differently-labeled parsing
error surfaced. The retry code only matched `tool_use_failed`, so this
variant wasn't caught. Fixed by broadening the exception match to cover
both error strings, since they're the same underlying failure mode
with different error codes.

**5. Tool calls with hallucinated parameters.** The model repeatedly
guessed at plausible-but-nonexistent parameters — `depth` on
`list_dir`, `line_start`/`line_end` on `read_file` — crashing the
corresponding functions with `TypeError`. Fixed by making every tool
function accept and silently ignore unexpected keyword arguments, and
by implementing `line_start`/`line_end` as real, working parameters
since the model clearly wanted that capability.

**6. Iteration budget exhausted right after success.** In one run, the
agent found the bug, wrote a correct fix, and confirmed all 5 tests
passed — then immediately ran the full suite a *second* time to
double-check, exhausting the iteration cap before it could emit
`DONE:`. The fix itself was correct the whole time; only the reporting
step got cut off. Fixed by raising `MAX_ITERATIONS` from 8 to 12 and
adding an explicit instruction telling the model to declare success
immediately on one clean pass, rather than re-verifying.

**7. File corruption via copied line-number formatting.** `read_file`
numbers its output for readability (e.g. `   5\tdef foo():`). In one
run, the model copied that numbered output directly into a `write_file`
call, writing literal line-number prefixes into the actual source
file — a real, silent correctness bug, not a crash. Fixed at two
layers: the system prompt now explicitly states line numbers are a
display aid only, and `write_file` itself detects the exact pattern
(every non-empty line starting with `N\t`) and strips it automatically
as a defensive backstop, since prompt instructions alone aren't a
reliable enough guarantee.

**8. Free-tier rate limiting (429).** Groq's free tier enforces a
tokens-per-minute cap (8,000 TPM on the model used here). A long-running
conversation crossed that limit mid-session. Fixed by detecting the
rate-limit error, parsing Groq's own suggested wait time out of the
error message, sleeping for that duration, and retrying automatically.

**Outcome:** after all eight fixes, a clean run completed in 5
iterations — explored the repo, read the buggy file, wrote a correct
fix on the first attempt, ran the full test suite, saw 5/5 pass, and
declared success immediately. No wasted steps, no crashes, no manual
intervention.

**Why this sequence matters more than a flawless first run would
have:** each fix above targets a distinct, real category of failure in
LLM-agent systems — environment/tooling mismatches, provider lock-in
and cost constraints, non-deterministic malformed model output, prompt
injection of the model's own guessed schema, budget exhaustion at the
worst possible moment, and rate limiting under real usage. Diagnosing
each one — is this a config issue, a model-quality issue, or a design
flaw, and which layer should the fix live in — is the actual day-to-day
work of building production LLM systems, and is the strongest part of
this project to walk through in an interview.
