# Sandbox environment for the coding agent.
#
# Why this exists: agent/tools.py scopes file paths to sandbox_repo/, but
# that alone does not stop an LLM-generated shell command from doing things
# like `pip install`, hitting the network, or consuming unbounded CPU/memory.
# Running the whole tool-execution step inside this container gives you a
# real isolation boundary: no host filesystem access, no network by default,
# and resource limits enforced by Docker itself.
#
# Build:  docker build -t coding-agent-sandbox -f docker/Dockerfile .
# Run:    docker run --rm -it --network none \
#            --memory=512m --cpus=1 \
#            -v $(pwd)/sandbox_repo:/workspace \
#            coding-agent-sandbox

FROM python:3.11-slim

WORKDIR /workspace

RUN pip install --no-cache-dir pytest

# Non-root user: if the agent's shell commands ever go wrong, they run
# with minimal privileges, not root inside the container.
RUN useradd -m agent
USER agent

CMD ["bash"]
