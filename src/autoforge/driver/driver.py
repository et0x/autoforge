"""Driver agent — reads evaluation feedback and proposes changes to the work product."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autoforge.config import resolve_model


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
    from claude_code_sdk import query as claude_query, ClaudeCodeOptions

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
    async for message in claude_query(prompt=prompt, options=options):
        # ResultMessage has the final output
        if hasattr(message, "result") and message.result:
            result_text = message.result
        # AssistantMessage has content blocks — capture text from them
        elif hasattr(message, "content") and isinstance(message.content, list):
            for block in message.content:
                if hasattr(block, "text"):
                    result_text = block.text

    return result_text.strip() if result_text else "No description provided"
