"""
Evaluation harness: runs the agent against every bug in eval_bugs.py,
and independently verifies success by re-running pytest itself --
never trusting the agent's self-reported "DONE:" as ground truth.

This distinction matters: an agent can claim success incorrectly (saw
a partial pass, misread output, hit an edge case in its own reasoning).
Measuring "claimed success" vs "actually passed" separately is what
turns this from a demo into a real evaluation.

Usage:
    cd agent
    python -m eval.eval_harness
    (or: python eval_harness.py if run from inside eval/)
"""

import os
import sys
import json
import time
import shutil
import subprocess
import datetime

# Make agent/ importable regardless of where this is run from
AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "agent")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

from eval_bugs import BUGS
from agent_loop import run_agent

SANDBOX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sandbox_repo"))
RESULTS_DIR = os.path.abspath(os.path.dirname(__file__))
RESULTS_JSONL = os.path.join(RESULTS_DIR, "results.jsonl")
RESULTS_SUMMARY_MD = os.path.join(RESULTS_DIR, "results_summary.md")

# Pause between bugs to stay well under free-tier rate limits even though
# agent_loop already retries on 429 -- this cuts down on wasted retry time.
PAUSE_BETWEEN_BUGS_SECONDS = 5


def reset_sandbox(bug: dict):
    """Wipe sandbox_repo/ and write exactly this bug's files into it."""
    if os.path.isdir(SANDBOX_ROOT):
        shutil.rmtree(SANDBOX_ROOT)
    os.makedirs(SANDBOX_ROOT, exist_ok=True)
    for relpath, content in bug["files"].items():
        full = os.path.join(SANDBOX_ROOT, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)


def verify_ground_truth() -> tuple[bool, str]:
    """Independently run pytest against the current sandbox state.
    Returns (all_passed, raw_output). This is the actual source of truth
    for whether a bug was fixed -- not the agent's own claim."""
    result = subprocess.run(
        ["python", "-m", "pytest", "-q"],
        cwd=SANDBOX_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    passed = result.returncode == 0 and "failed" not in output.lower()
    return passed, output[-1500:]


def run_single_eval(bug: dict) -> dict:
    print(f"\n{'='*70}")
    print(f"BUG: {bug['id']}  (difficulty: {bug['difficulty']})")
    print(f"{'='*70}")

    reset_sandbox(bug)

    log_path = os.path.join(RESULTS_DIR, f"log_{bug['id']}.jsonl")
    if os.path.exists(log_path):
        os.remove(log_path)

    start = time.time()
    agent_result = run_agent(bug["task"], log_path=log_path, verbose=True)
    elapsed = time.time() - start

    actual_pass, test_output = verify_ground_truth()

    result = {
        "bug_id": bug["id"],
        "difficulty": bug["difficulty"],
        "declared_done": agent_result["declared_done"],
        "actual_pass": actual_pass,
        "correct_self_assessment": agent_result["declared_done"] == actual_pass,
        "iterations_used": agent_result["iterations_used"],
        "elapsed_seconds": round(elapsed, 1),
        "error": agent_result.get("error"),
        "timestamp": datetime.datetime.now().isoformat(),
    }

    status = "PASS" if actual_pass else "FAIL"
    print(f"\n>>> Ground truth: {status}  |  Agent claimed done: {agent_result['declared_done']}  |  Iterations: {agent_result['iterations_used']}")
    if not result["correct_self_assessment"]:
        print("!!! MISMATCH: agent's self-report did not match actual test outcome !!!")

    return result


def print_summary_table(results: list[dict]):
    print(f"\n{'='*70}")
    print("EVALUATION SUMMARY")
    print(f"{'='*70}")
    header = f"{'Bug ID':<32} {'Difficulty':<10} {'Passed':<8} {'Claimed':<9} {'Iters':<6} {'Time(s)':<8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['bug_id']:<32} {r['difficulty']:<10} {str(r['actual_pass']):<8} {str(r['declared_done']):<9} {r['iterations_used']:<6} {r['elapsed_seconds']:<8}")

    total = len(results)
    passed = sum(1 for r in results if r["actual_pass"])
    correct_self_assess = sum(1 for r in results if r["correct_self_assessment"])
    avg_iters = sum(r["iterations_used"] for r in results) / total if total else 0
    avg_time = sum(r["elapsed_seconds"] for r in results) / total if total else 0

    print("-" * len(header))
    print(f"Success rate:              {passed}/{total} ({100*passed/total:.0f}%)")
    print(f"Self-assessment accuracy:  {correct_self_assess}/{total} ({100*correct_self_assess/total:.0f}%)")
    print(f"Avg iterations used:       {avg_iters:.1f}")
    print(f"Avg wall-clock time:       {avg_time:.1f}s")

    return {
        "total": total,
        "passed": passed,
        "success_rate": round(100 * passed / total, 1) if total else 0,
        "self_assessment_accuracy": round(100 * correct_self_assess / total, 1) if total else 0,
        "avg_iterations": round(avg_iters, 1),
        "avg_seconds": round(avg_time, 1),
    }


def write_markdown_summary(results: list[dict], stats: dict):
    lines = [
        "# Evaluation Results",
        "",
        f"Run at {datetime.datetime.now().isoformat()}",
        "",
        f"**Success rate: {stats['passed']}/{stats['total']} ({stats['success_rate']}%)**",
        f"**Self-assessment accuracy: {stats['self_assessment_accuracy']}%** "
        "(how often the agent's own \"DONE\" claim matched the real test outcome)",
        f"Average iterations used: {stats['avg_iterations']}",
        f"Average wall-clock time: {stats['avg_seconds']}s",
        "",
        "| Bug ID | Difficulty | Passed | Claimed Done | Iterations | Time (s) |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['bug_id']} | {r['difficulty']} | {'✅' if r['actual_pass'] else '❌'} "
            f"| {'✅' if r['declared_done'] else '❌'} | {r['iterations_used']} | {r['elapsed_seconds']} |"
        )
    lines.append("")
    with open(RESULTS_SUMMARY_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    results = []
    if os.path.exists(RESULTS_JSONL):
        os.remove(RESULTS_JSONL)

    for i, bug in enumerate(BUGS):
        result = run_single_eval(bug)
        results.append(result)

        with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")

        if i < len(BUGS) - 1:
            print(f"\n[pausing {PAUSE_BETWEEN_BUGS_SECONDS}s before next bug to stay under rate limits...]")
            time.sleep(PAUSE_BETWEEN_BUGS_SECONDS)

    stats = print_summary_table(results)
    write_markdown_summary(results, stats)
    print(f"\nFull results: {RESULTS_JSONL}")
    print(f"Markdown summary: {RESULTS_SUMMARY_MD}")


if __name__ == "__main__":
    main()
