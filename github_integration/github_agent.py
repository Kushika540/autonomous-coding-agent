"""
Pulls a real GitHub issue, clones the repo, points the existing coding
agent at it, and -- only if the agent actually reports success -- commits,
pushes a branch, and opens a real pull request.

This reuses agent_loop.py and tools.py completely unchanged. The only
new mechanism is repointing tools.py's SANDBOX_ROOT at a real git clone
via the AGENT_WORKDIR environment variable (see tools.py), plus the
git/GitHub plumbing around it.

SAFETY: run this against a repo you own or control, not against
someone else's open-source project, until you've tested the flow and
trust the fix quality. Use --dry-run first -- it does everything except
push and open the PR, so you can inspect the diff safely.

Usage:
    export GITHUB_TOKEN=ghp_...
    python github_agent.py --repo yourname/your-repo --issue 3
    python github_agent.py --repo yourname/your-repo --issue 3 --dry-run
    python github_agent.py --repo yourname/your-repo --issue 3 --base develop
"""

import os
import sys
import argparse
import subprocess

# Make agent/ importable
AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "agent")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

WORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "clones"))


def run_git(args, cwd, check=True):
    """Run a git command and return (returncode, stdout+stderr)."""
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{output}")
    return result.returncode, output


def clone_or_sync_repo(repo_full_name: str, token: str, base_branch: str) -> str:
    """Clone the repo if not already present locally, or fetch + reset if it is.
    Returns the local working directory path."""
    repo_name = repo_full_name.split("/")[-1]
    workdir = os.path.join(WORK_ROOT, repo_name)
    clone_url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"

    if not os.path.isdir(os.path.join(workdir, ".git")):
        os.makedirs(WORK_ROOT, exist_ok=True)
        print(f"[git] cloning {repo_full_name} into {workdir} ...")
        run_git(["clone", clone_url, workdir], cwd=WORK_ROOT)
    else:
        print(f"[git] repo already cloned at {workdir}, syncing ...")
        run_git(["remote", "set-url", "origin", clone_url], cwd=workdir)
        run_git(["fetch", "origin"], cwd=workdir)
        run_git(["checkout", base_branch], cwd=workdir)
        run_git(["reset", "--hard", f"origin/{base_branch}"], cwd=workdir)

    return workdir


def create_branch(workdir: str, branch_name: str, base_branch: str):
    run_git(["checkout", base_branch], cwd=workdir)
    run_git(["pull", "origin", base_branch], cwd=workdir, check=False)
    # -B creates or resets the branch, so re-runs against the same issue don't fail
    run_git(["checkout", "-B", branch_name], cwd=workdir)


def has_uncommitted_changes(workdir: str) -> bool:
    _, output = run_git(["status", "--porcelain"], cwd=workdir)
    return bool(output.strip())


def commit_and_push(workdir: str, branch_name: str, message: str):
    run_git(["add", "-A"], cwd=workdir)
    run_git(["commit", "-m", message], cwd=workdir)
    run_git(["push", "-u", "origin", branch_name, "--force"], cwd=workdir)


def main():
    parser = argparse.ArgumentParser(description="Run the coding agent against a real GitHub issue.")
    parser.add_argument("--repo", required=True, help="owner/repo, e.g. yourname/your-project")
    parser.add_argument("--issue", required=True, type=int, help="Issue number to fix")
    parser.add_argument("--base", default="main", help="Base branch to branch from and PR into (default: main)")
    parser.add_argument("--dry-run", action="store_true", help="Do everything except push and open a PR")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: set GITHUB_TOKEN (a GitHub personal access token with 'repo' scope).")
        print("Create one at https://github.com/settings/tokens")
        sys.exit(1)

    try:
        from github import Github, Auth
    except ImportError:
        print("ERROR: PyGithub is not installed. Run: pip install PyGithub")
        sys.exit(1)

    gh = Github(auth=Auth.Token(token))
    repo = gh.get_repo(args.repo)
    issue = repo.get_issue(args.issue)

    print(f"\n=== Issue #{args.issue}: {issue.title} ===")
    print(issue.body or "(no description)")

    task = (
        f"Fix the following GitHub issue.\n\n"
        f"Title: {issue.title}\n\n"
        f"Description:\n{issue.body or '(no description provided)'}\n\n"
        f"Explore the repository to understand the codebase and locate the "
        f"relevant code, make a minimal fix, and verify it with the "
        f"project's existing tests if a test suite is present."
    )

    workdir = clone_or_sync_repo(args.repo, token, args.base)
    branch_name = f"agent-fix-issue-{args.issue}"
    create_branch(workdir, branch_name, args.base)

    # Point the existing tools/agent loop at this real repo instead of the
    # local demo sandbox. Must happen before importing agent_loop, since
    # tools.py resolves AGENT_WORKDIR once at import time.
    os.environ["AGENT_WORKDIR"] = workdir
    from agent_loop import run_agent  # noqa: E402  (deliberately deferred import)

    log_path = os.path.join(
        os.path.dirname(__file__), "..", "logs", f"github_issue_{args.issue}.jsonl"
    )
    result = run_agent(task, log_path=log_path)

    if not result["declared_done"]:
        print(f"\n[stopped] agent did not report success (error: {result.get('error')}). Not opening a PR.")
        print(f"Local changes (if any) are left in {workdir} on branch {branch_name} for inspection.")
        sys.exit(1)

    if not has_uncommitted_changes(workdir):
        print("\n[stopped] agent reported DONE but made no file changes. Not opening a PR.")
        sys.exit(1)

    commit_message = f"Fix: {issue.title} (resolves #{args.issue})\n\nAutomated fix by coding agent."
    pr_title = f"Fix: {issue.title}"
    pr_body = (
        f"Automated fix for #{args.issue}, generated by an autonomous coding agent.\n\n"
        f"**Agent's summary:**\n{result['final_message']}\n\n"
        f"**Please review carefully before merging** -- this PR was opened "
        f"by an LLM-based agent without human review of the fix itself.\n\n"
        f"Closes #{args.issue}"
    )

    if args.dry_run:
        print(f"\n[dry run] would commit with message:\n  {commit_message}")
        print(f"[dry run] would push branch '{branch_name}' and open a PR:")
        print(f"  Title: {pr_title}")
        print(f"  Body:\n{pr_body}")
        print(f"\nLocal changes are in {workdir} on branch {branch_name} -- inspect with 'git diff' there.")
        return

    commit_and_push(workdir, branch_name, commit_message)
    pr = repo.create_pull(title=pr_title, body=pr_body, head=branch_name, base=args.base)
    print(f"\n=== PR opened: {pr.html_url} ===")


if __name__ == "__main__":
    main()
