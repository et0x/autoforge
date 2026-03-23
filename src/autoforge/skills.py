"""Skill loading utilities.

Skills are Claude Code's mechanism for giving agents packaged expertise.
They live in directories with a structure like:

    some-dir/
      .claude/skills/my-skill/SKILL.md
      docs/...

Or as plugins:

    some-dir/
      plugins/my-plugin/skills/my-skill/SKILL.md
      docs/...

This module handles two use cases:
  1. SDK mode: resolve skill_dirs to absolute paths for add_dirs so the
     Claude Code subprocess discovers and can invoke skills.
  2. API mode: discover SKILL.md files and referenced docs, return their
     content as a string to inject into the system prompt as knowledge.
"""

from __future__ import annotations

from pathlib import Path


def resolve_skill_dirs(raw_dirs: list[str]) -> list[Path]:
    """Expand ~ and resolve skill directories to absolute paths."""
    resolved = []
    for d in raw_dirs:
        p = Path(d).expanduser().resolve()
        if p.is_dir():
            resolved.append(p)
    return resolved


def discover_skill_files(
    skill_dirs: list[str],
    filter_names: list[str] | None = None,
) -> list[Path]:
    """Find SKILL.md files in the given directories.

    Args:
        skill_dirs: Directories to search.
        filter_names: If provided, only return skills whose directory name
                      matches one of these names. e.g. ["netrise-knowledge-base"]
    """
    found: list[Path] = []
    for d in resolve_skill_dirs(skill_dirs):
        # Pattern 1: .claude/skills/<name>/SKILL.md
        for skill_md in sorted(d.glob(".claude/skills/*/SKILL.md")):
            if filter_names is None or skill_md.parent.name in filter_names:
                found.append(skill_md)
        # Pattern 2: plugins/<plugin>/skills/<name>/SKILL.md
        for skill_md in sorted(d.glob("plugins/*/skills/*/SKILL.md")):
            if filter_names is None or skill_md.parent.name in filter_names:
                found.append(skill_md)
    return found


def load_skill_content(
    skill_dirs: list[str],
    filter_names: list[str] | None = None,
    max_total_chars: int = 100_000,
) -> str:
    """Load skill knowledge for injection into API-mode agent prompts.

    For agents that can't invoke skills as tools (API mode), we read the
    SKILL.md files and any docs they reference, returning everything as a
    context string for the system prompt.

    Args:
        skill_dirs: Directories containing skills.
        filter_names: Only load skills matching these names.
        max_total_chars: Hard cap on total content to avoid blowing up context.
    """
    skill_files = discover_skill_files(skill_dirs, filter_names)
    if not skill_files:
        return ""

    parts: list[str] = []
    total_chars = 0

    for skill_md in skill_files:
        if total_chars >= max_total_chars:
            break

        skill_dir = skill_md.parent
        skill_name = skill_dir.name
        content = skill_md.read_text()

        parts.append(f"# Skill: {skill_name}\n\n{content}")
        total_chars += len(content)

        # Load reference files adjacent to SKILL.md
        refs_dir = skill_dir / "references"
        if refs_dir.is_dir():
            for ref in sorted(refs_dir.glob("*.md")):
                if total_chars >= max_total_chars:
                    break
                ref_content = ref.read_text()
                if len(ref_content) > 8000:
                    ref_content = ref_content[:8000] + "\n\n[... truncated ...]"
                parts.append(f"### {ref.name} (reference)\n\n{ref_content}\n")
                total_chars += len(ref_content)

        # Look for docs/ at the repo root
        repo_root = _find_repo_root(skill_md)
        if repo_root:
            docs_dir = repo_root / "docs"
            if docs_dir.is_dir():
                parts.append(f"\n## Reference Documents ({skill_name})\n")
                for doc in sorted(docs_dir.glob("*.md")):
                    if total_chars >= max_total_chars:
                        parts.append(f"\n[... {max_total_chars} char limit reached, remaining docs omitted ...]")
                        break
                    doc_content = doc.read_text()
                    if len(doc_content) > 8000:
                        doc_content = doc_content[:8000] + "\n\n[... truncated ...]"
                    parts.append(f"### {doc.name}\n\n{doc_content}\n")
                    total_chars += len(doc_content)

    return "\n\n".join(parts)


def _find_repo_root(path: Path) -> Path | None:
    """Walk up from a skill file to find the repo root."""
    current = path.parent
    for _ in range(10):
        if (current / "CLAUDE.md").exists():
            return current
        if (current / ".git").exists():
            return current
        if (current / "plugins").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
