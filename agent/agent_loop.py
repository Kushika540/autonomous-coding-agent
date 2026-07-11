"""
Core agent loop: plan -> act -> observe -> repeat.

Uses the OpenAI-compatible chat completions API, which lets this run
against multiple FREE providers with zero code changes -- just swap
environment variables:

  Groq:
    export GROQ_API_KEY=gsk_...
    (base URL and model already default to Groq below)

  Google AI Studio:
    export LLM_API_KEY=AIza...
    export AGENT_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
    export AGENT_MODEL=gemini-2.0-flash

  Local Ollama:
    ollama pull llama3.1
    ollama serve
    export AGENT_BASE_URL=http://localhost:11434/v1
    export AGENT_MODEL=llama3.1
    export LLM_API_KEY=ollama   # any non-empty string works

Usage:
    python agent_loop.py "Fix the failing tests in tests/test_stringutils.py"
"""

import os
import sys
import json
import time
import re
import datetime
from openai import OpenAI

from tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS

BASE_URL = os.environ.get("AGENT_BASE_URL", "https://api.groq.com/openai/v1")

MODEL = os.environ.get("AGENT_MODEL", "openai/gpt-oss-20b")
API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY")

MAX_ITERATIONS = 12
MAX_TOOL_CALL_RETRIES = 8

SYSTEM_PROMPT = """You are an autonomous coding agent. You are given a task
describing a bug or failing test in a code repository. You have tools to
explore the repo, read files, edit files, and run shell commands (including
running the test suite).

Your process should be:
1. Explore the repo structure and read relevant files BEFORE making changes.
2. Run the test suite first to see the actual failure and understand it.
3. Form a hypothesis about the root cause. State it briefly.
4. Make a minimal, targeted fix using write_file. Always read a file before
   overwriting it, and preserve everything except what needs to change.
5. Re-run the tests to verify your fix worked.
6. If tests still fail, read the new error carefully and try again -- don't
   repeat the same failed approach.
7. The MOMENT a tool result shows the full test suite passing, respond
   immediately with "DONE: ..." in that same turn. Do not re-run the tests
   again to double check -- one clean full pass is sufficient confirmation.

Only call read_file, list_dir, write_file, and run_shell_command with the
exact parameter names they define. Do not invent extra parameters.

IMPORTANT: read_file's output includes line numbers (e.g. "   5\t") as a
reference aid only. These are NOT part of the actual file content. When
calling write_file, never include those line-number prefixes in the
content you write -- write only the real file content, exactly as it
would appear with no numbering.

When all tests pass, respond with a final message starting with "DONE:"
summarizing what was wrong and what you changed. Do not claim success
unless you have actually seen the tests pass in a tool result.
"""


def log(entry: dict, log_path: str):
    entry["timestamp"] = datetime.datetime.now().isoformat()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_agent(task: str, log_path: str = "../logs/run.jsonl", verbose: bool = True):
    """Returns a dict: {declared_done, iterations_used, final_message, error}.
    declared_done reflects only what the model claimed -- callers that need
    ground truth (e.g. the eval harness) should independently verify by
    re-running the test suite themselves."""
    def _p(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)

    if not API_KEY:
        _p(
            "ERROR: no API key found. Set GROQ_API_KEY (get a free one at "
            "console.groq.com) or LLM_API_KEY if using a different provider."
        )
        return {"declared_done": False, "iterations_used": 0, "final_message": None, "error": "no_api_key"}

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    log({"event": "task_start", "task": task, "model": MODEL, "base_url": BASE_URL}, log_path)
    _p(f"\n=== TASK ===\n{task}\n(model: {MODEL} via {BASE_URL})\n")

    for iteration in range(1, MAX_ITERATIONS + 1):
        _p(f"\n--- Iteration {iteration}/{MAX_ITERATIONS} ---")


        response = None
        last_error = None
        for attempt in range(1, MAX_TOOL_CALL_RETRIES + 1):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    max_tokens=4096,
                    temperature=0.0,
                )
                break
            except Exception as e:
                last_error = e
                err_str = str(e)

                if "rate_limit_exceeded" in err_str or "429" in err_str:
                    wait_match = re.search(r"try again in ([\d.]+)s", err_str)
                    wait_seconds = float(wait_match.group(1)) + 1.0 if wait_match else 15.0
                    _p(f"[rate limit] hit free-tier TPM cap, waiting {wait_seconds:.1f}s before retrying...")
                    log({"event": "rate_limited", "iteration": iteration, "wait_seconds": wait_seconds}, log_path)
                    time.sleep(wait_seconds)
                    continue

                if any(marker in err_str for marker in (
                    "tool_use_failed", "Failed to call a function",
                    "output_parse_failed", "Parsing failed",
                )):
                    _p(f"[warning] malformed tool call from model (attempt {attempt}/{MAX_TOOL_CALL_RETRIES}), retrying...")
                    log({"event": "tool_call_malformed_retry", "iteration": iteration, "attempt": attempt, "error": err_str[:500]}, log_path)
                    continue
                raise 

        if response is None:
            _p(f"[error] gave up after {MAX_TOOL_CALL_RETRIES} malformed tool call attempts: {last_error}")
            log({"event": "tool_call_failed_permanently", "iteration": iteration, "error": str(last_error)[:500]}, log_path)
            messages.append({
                "role": "user",
                "content": "Your last response wasn't in a valid tool-call format. "
                            "Please try again, calling exactly one tool at a time."
            })
            continue

        msg = response.choices[0].message

        if msg.content:
            _p(f"[agent] {msg.content}")
            log({"event": "reasoning", "iteration": iteration, "text": msg.content}, log_path)

            if msg.content.strip().startswith("DONE:"):
                log({"event": "task_complete", "iteration": iteration}, log_path)
                _p("\n=== AGENT REPORTS SUCCESS ===")
                return {"declared_done": True, "iterations_used": iteration, "final_message": msg.content, "error": None}

   
        assistant_entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            _p("[agent] stopped without calling a tool or declaring done.")
            messages.append({
                "role": "user",
                "content": "Please continue: use your tools to verify the "
                            "current state and either fix the issue or "
                            "confirm tests pass with 'DONE: ...'."
            })
            continue

        # Execute each requested tool call and feed results back
        for call in msg.tool_calls:
            fn = TOOL_FUNCTIONS.get(call.function.name)
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                args = {}
            _p(f"[tool call] {call.function.name}({json.dumps(args)[:200]})")

            try:
                result = fn(**args)
            except Exception as e:
                result = f"ERROR running {call.function.name}: {e}"
            _p(f"[tool result] {str(result)[:400]}")

            log({
                "event": "tool_call",
                "iteration": iteration,
                "tool": call.function.name,
                "input": args,
                "result": str(result)[:2000],
            }, log_path)

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            })

    _p("\n=== MAX ITERATIONS REACHED WITHOUT SUCCESS ===")
    log({"event": "max_iterations_reached"}, log_path)
    return {"declared_done": False, "iterations_used": MAX_ITERATIONS, "final_message": None, "error": "max_iterations"}


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else (
        "The test suite in tests/test_stringutils.py is failing. "
        "Explore the repo, find the bug, fix it, and confirm all tests pass."
    )
    run_agent(task)
