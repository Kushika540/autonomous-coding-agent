"""
Tool implementations for the coding agent.

Every tool is scoped to operate only within SANDBOX_ROOT. This is a
deliberate safety boundary: never let an LLM read or write arbitrary
paths on the host machine. In production you'd run this whole process
inside a Docker container too (see docker/Dockerfile) — path-scoping
here is defense-in-depth, not a replacement for that.

SANDBOX_ROOT defaults to the local demo repo (sandbox_repo/), but can
be pointed at any directory via the AGENT_WORKDIR environment variable
-- this is how github_agent.py repoints the same tools at a real cloned
repository without any code duplication. Set AGENT_WORKDIR *before*
importing this module (or agent_loop, which imports it), since the
path is resolved once at import time.
"""

import os
import re
import subprocess
import difflib

_workdir_override = os.environ.get("AGENT_WORKDIR")
SANDBOX_ROOT = os.path.abspath(
    _workdir_override if _workdir_override
    else os.path.join(os.path.dirname(__file__), "..", "sandbox_repo")
)


def _resolve(path: str) -> str:
    """Resolve a path relative to SANDBOX_ROOT and refuse to leave it."""
    full = os.path.abspath(os.path.join(SANDBOX_ROOT, path))
    if not full.startswith(SANDBOX_ROOT):
        raise ValueError(f"Path '{path}' escapes the sandbox root. Refusing.")
    return full


def read_file(path: str, line_start: int = None, line_end: int = None, **_ignored) -> str:
    """Read and return the contents of a file, with line numbers.
    Optionally pass line_start/line_end (1-indexed, inclusive) to read a slice."""
    full = _resolve(path)
    if not os.path.isfile(full):
        return f"ERROR: file not found: {path}"
    with open(full, "r", encoding="utf-8") as f:
        lines = f.readlines()
    start = (line_start - 1) if line_start else 0
    end = line_end if line_end else len(lines)
    numbered = "".join(
        f"{i+1:4d}\t{line}" for i, line in enumerate(lines) if start <= i < end
    )
    return numbered


def list_dir(path: str = ".", **_ignored) -> str:
    """List files and directories at the given path (relative to sandbox root).
    Any extra keyword arguments (e.g. a guessed 'depth' param) are accepted
    and ignored rather than causing an error -- always lists recursively."""
    full = _resolve(path)
    if not os.path.isdir(full):
        return f"ERROR: directory not found: {path}"
    entries = []
    for root, dirs, files in os.walk(full):
        # skip noisy dirs
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".pytest_cache")]
        rel_root = os.path.relpath(root, SANDBOX_ROOT)
        for f in files:
            entries.append(os.path.normpath(os.path.join(rel_root, f)))
    return "\n".join(sorted(entries))


_LINE_NUM_PREFIX = re.compile(r"^\s*\d+\t")


def write_file(path: str, content: str, **_ignored) -> str:
    """Overwrite a file with new content. Returns a diff of what changed.

    Defensive check: if every non-empty line starts with a "N\\t" prefix
    (the format read_file uses for line numbers), the model has almost
    certainly copied read_file's display output back in verbatim instead
    of writing real file content. Strip those prefixes automatically
    rather than corrupting the file, and note it in the returned diff.
    """
    lines = content.split("\n")
    non_empty = [l for l in lines if l.strip()]
    stripped_note = ""
    if non_empty and all(_LINE_NUM_PREFIX.match(l) for l in non_empty):
        content = "\n".join(_LINE_NUM_PREFIX.sub("", l) for l in lines)
        stripped_note = (
            "\n[NOTE: detected and stripped line-number prefixes that were "
            "accidentally copied from read_file's output -- these are not "
            "part of real file content. Double-check the diff below.]\n"
        )

    full = _resolve(path)
    old_content = ""
    if os.path.isfile(full):
        with open(full, "r", encoding="utf-8") as f:
            old_content = f.read()

    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

    diff = "\n".join(
        difflib.unified_diff(
            old_content.splitlines(),
            content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    return stripped_note + (diff if diff else "No changes (file identical).")


DOCKER_IMAGE = os.environ.get("AGENT_DOCKER_IMAGE", "coding-agent-sandbox")
USE_DOCKER_SANDBOX = os.environ.get("AGENT_USE_DOCKER", "").lower() in ("1", "true", "yes")


def run_shell_command(command: str, timeout: int = 30, **_ignored) -> str:
    """
    Run a shell command inside the sandbox root and return combined
    stdout/stderr. Has a timeout so a runaway command can't hang the loop.

    By default this uses a local subprocess with cwd scoping, which is
    fine for local development but does NOT stop an LLM-written command
    from touching the network or the rest of your filesystem via
    absolute paths or shell tricks.

    Set AGENT_USE_DOCKER=1 to run commands inside the container defined
    in docker/Dockerfile instead: no network access, no host filesystem
    access outside the mounted sandbox, and CPU/memory limits enforced
    by Docker itself rather than trusted to application-level code.
    Requires the image to be built first:
        docker build -t coding-agent-sandbox -f docker/Dockerfile .
    """
    if USE_DOCKER_SANDBOX:
        return _run_shell_command_docker(command, timeout)
    return _run_shell_command_local(command, timeout)


def _run_shell_command_local(command: str, timeout: int) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=SANDBOX_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return output[-4000:] if len(output) > 4000 else output
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {timeout}s"


def _run_shell_command_docker(command: str, timeout: int) -> str:
    """Run the command inside an ephemeral, isolated Docker container.
    A fresh container per call (rather than a long-lived one) keeps
    lifecycle management simple: nothing to clean up if the process
    crashes mid-run, and no shared state leaking between commands
    beyond the mounted sandbox directory itself."""
    docker_args = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", "512m",
        "--cpus", "1",
        "-v", f"{SANDBOX_ROOT}:/workspace",
        "-w", "/workspace",
        DOCKER_IMAGE,
        "bash", "-c", command,
    ]
    try:
        result = subprocess.run(
            docker_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return output[-4000:] if len(output) > 4000 else output
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {timeout}s"
    except FileNotFoundError:
        return (
            "ERROR: 'docker' command not found. Is Docker installed and on "
            "your PATH? Falling back is not automatic -- unset AGENT_USE_DOCKER "
            "to use local subprocess execution instead."
        )


# Tool schema in OpenAI function-calling format. Groq, Google AI Studio's
# OpenAI-compat endpoint, and most free-tier providers all speak this
# format, which is why the agent loop uses the `openai` SDK pointed at a
# different base_url rather than a provider-specific SDK.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file (with line numbers) inside the sandbox repo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the repo root, e.g. 'stringutils.py'"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List all files in a directory (recursively) inside the sandbox repo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path relative to repo root. Use '.' for root."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Overwrite a file with new full content. Always read the file first. Returns a diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to repo root"},
                    "content": {"type": "string", "description": "The complete new file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Run a shell command (e.g. 'pytest tests/ -v') inside the sandbox repo root and get the output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"}
                },
                "required": ["command"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_dir": list_dir,
    "write_file": write_file,
    "run_shell_command": run_shell_command,
}
