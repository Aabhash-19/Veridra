import re

from app.db.models import Artifact

_BOLD_ITALIC_RE = re.compile(r"(\*\*|__|\*|_|`)")
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def format_artifact_export(artifact: Artifact, *, fmt: str) -> tuple[str, str, str]:
    """Return (content, media_type, filename) for md or txt artifact export."""
    safe_slug = (
        re.sub(r"[^a-zA-Z0-9_-]+", "-", artifact.title.lower()).strip("-")[:48] or "artifact"
    )
    if fmt == "md":
        header = (
            f"# {artifact.title}\n\n"
            if not artifact.body_markdown.lstrip().startswith("# ")
            else ""
        )
        content = f"{header}{artifact.body_markdown.strip()}\n"
        filename = f"{safe_slug}-v{artifact.version}.md"
        return content, "text/markdown; charset=utf-8", filename

    # Plain text export: strip Markdown syntax carefully while preserving links and citation markers
    body = artifact.body_markdown.strip()
    body = _LINK_RE.sub(r"\1 (\2)", body)
    body = _HEADING_RE.sub("", body)
    body = _BOLD_ITALIC_RE.sub("", body)
    content = f"{artifact.title}\n{'=' * min(len(artifact.title), 72)}\n\n{body}\n"
    filename = f"{safe_slug}-v{artifact.version}.txt"
    return content, "text/plain; charset=utf-8", filename
