"""Driver agent — reads evaluation feedback and proposes changes to the work product."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from autoforge.config import ProgramConfig, resolve_model


def _build_mcp_servers(raw: dict[str, dict]) -> dict[str, Any]:
    """Convert raw MCP server dicts from YAML into SDK-compatible configs."""
    from claude_code_sdk.types import McpStdioServerConfig, McpHttpServerConfig

    servers: dict[str, Any] = {}
    for name, conf in raw.items():
        server_type = conf.get("type", "stdio")
        if server_type == "stdio":
            servers[name] = McpStdioServerConfig(
                command=conf["command"],
                args=conf.get("args", []),
                env=conf.get("env", {}),
            )
        elif server_type in ("http", "sse"):
            servers[name] = McpHttpServerConfig(
                type="http",
                url=conf["url"],
                headers=conf.get("headers", {}),
            )
    return servers


async def run_driver_sdk(
    workspace: Path,
    prompt: str,
    model: str = "sonnet",
    allowed_tools: list[str] | None = None,
    mcp_servers: dict[str, dict] | None = None,
    skill_dirs: list[str] | None = None,
    max_turns: int | None = None,
) -> str:
    """Run the driver agent using the Claude Code SDK.

    Full agentic session — the agent can take multiple turns,
    use tools (Read, Edit, Bash, etc.), call MCPs, invoke skills, etc.
    Returns a description of what was changed.
    """
    from claude_code_sdk import Claude, ClaudeCodeOptions

    if allowed_tools is None:
        allowed_tools = ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]

    if skill_dirs and "Skill" not in allowed_tools:
        allowed_tools.append("Skill")

    options = ClaudeCodeOptions(
        model=resolve_model(model),
        cwd=str(workspace),
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
    )

    if max_turns is not None:
        options.max_turns = max_turns

    if mcp_servers:
        options.mcp_servers = _build_mcp_servers(mcp_servers)

    if skill_dirs:
        from autoforge.skills import resolve_skill_dirs
        resolved = resolve_skill_dirs(skill_dirs)
        if resolved:
            options.add_dirs = [str(d) for d in resolved]

    result_text = ""
    async for message in Claude.query(prompt=prompt, options=options):
        if hasattr(message, "content") and isinstance(message.content, str):
            result_text = message.content

    return result_text.strip() if result_text else "No description provided"


async def run_driver_api(
    workspace: Path,
    prompt: str,
    program: ProgramConfig,
    model: str = "sonnet",
    client: AsyncAnthropic | None = None,
) -> str:
    """Run the driver agent using the raw Anthropic API (single-turn).

    Simpler approach: send file contents in prompt, get back modified contents.
    Best for content optimization where edits are text-only.
    Returns a description of what was changed.
    """
    if client is None:
        client = AsyncAnthropic()

    system = (
        "You are a driver agent for an optimization loop. You will be given "
        "content to improve and feedback from evaluators. Make ONE focused "
        "change based on the feedback. Respond with:\n"
        "1. DESCRIPTION: A one-line description of your change\n"
        "2. For each file you modified, output:\n"
        "   FILE: <filename>\n"
        "   ```\n"
        "   <complete new file contents>\n"
        "   ```\n"
    )

    response = await client.messages.create(
        model=resolve_model(model),
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    result = response.content[0].text
    description = _extract_description(result)

    _apply_file_outputs(result, workspace, program)

    return description


def _extract_description(text: str) -> str:
    """Extract the DESCRIPTION line from driver output."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("DESCRIPTION:"):
            return line[len("DESCRIPTION:"):].strip()
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:100]
    return "No description"


def _apply_file_outputs(text: str, workspace: Path, program: ProgramConfig) -> None:
    """Parse FILE: blocks and write them to the workspace."""
    import re

    pattern = r"FILE:\s*(\S+)\s*\n```[^\n]*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    allowed_patterns = set(program.editable_files)

    for filename, content in matches:
        filepath = workspace / filename
        rel = str(filepath.relative_to(workspace))
        is_allowed = any(
            filepath.match(pat) or rel == pat
            for pat in allowed_patterns
        )
        if is_allowed:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
