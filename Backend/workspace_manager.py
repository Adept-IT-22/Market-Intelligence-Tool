"""
Workspace Manager — Persistent project memory for Precision Scout v2.

Manages projects, artifacts, and PROJECT.md files that track
knowledge accumulation across multiple query sessions.

Storage layout:
  Backend/workspace/projects/{slug}/
    PROJECT.md          — frontmatter truth file
    artifacts/          — saved analysis outputs
    uploaded/           — project-specific uploads
"""

import os
import re
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace", "projects")


def _slugify(text):
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower().strip())
    slug = re.sub(r'[\s_]+', '-', slug)
    return slug[:60]


def _ensure_workspace():
    """Create the workspace directory structure if it doesn't exist."""
    os.makedirs(WORKSPACE_DIR, exist_ok=True)


# ============== PROJECT CRUD ==============

def create_project(name, description="", user_id=None):
    """
    Create a new workspace project with PROJECT.md and directory structure.
    Returns the project slug (used as project_id).
    """
    _ensure_workspace()
    slug = _slugify(name)
    project_dir = os.path.join(WORKSPACE_DIR, slug)

    if os.path.exists(project_dir):
        logger.warning(f"Project '{slug}' already exists, returning existing.")
        return slug

    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(os.path.join(project_dir, "artifacts"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "uploaded"), exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    project_md = f"""---
title: {name}
status: active
created: {now}
last_updated: {now}
created_by: {user_id or 'system'}
description: {description}
---

## Data Sources
_No data sources linked yet._

## Insights Generated
_No artifacts generated yet._

## Next Steps
- [ ] Define research objectives
- [ ] Upload or link relevant documents

## Query History
_No queries yet._
"""
    with open(os.path.join(project_dir, "PROJECT.md"), "w", encoding="utf-8") as f:
        f.write(project_md)

    logger.info(f"Workspace: Created project '{slug}' at {project_dir}")
    return slug


def list_projects():
    """List all projects with their metadata from PROJECT.md frontmatter."""
    _ensure_workspace()
    projects = []

    for entry in sorted(os.listdir(WORKSPACE_DIR)):
        project_dir = os.path.join(WORKSPACE_DIR, entry)
        if not os.path.isdir(project_dir):
            continue

        project_md_path = os.path.join(project_dir, "PROJECT.md")
        metadata = _parse_frontmatter(project_md_path)

        # Count artifacts
        artifacts_dir = os.path.join(project_dir, "artifacts")
        artifact_count = len(os.listdir(artifacts_dir)) if os.path.exists(artifacts_dir) else 0

        projects.append({
            "id": entry,
            "title": metadata.get("title", entry),
            "status": metadata.get("status", "unknown"),
            "created": metadata.get("created", ""),
            "last_updated": metadata.get("last_updated", ""),
            "description": metadata.get("description", ""),
            "artifact_count": artifact_count
        })

    return projects


def get_project(project_id):
    """Get full project details including PROJECT.md content and artifact list."""
    project_dir = os.path.join(WORKSPACE_DIR, project_id)
    if not os.path.isdir(project_dir):
        return None

    project_md_path = os.path.join(project_dir, "PROJECT.md")
    metadata = _parse_frontmatter(project_md_path)

    # Read full PROJECT.md
    content = ""
    if os.path.exists(project_md_path):
        with open(project_md_path, "r", encoding="utf-8") as f:
            content = f.read()

    # List artifacts
    artifacts = list_artifacts(project_id)

    return {
        "id": project_id,
        "metadata": metadata,
        "content": content,
        "artifacts": artifacts,
        "path": project_dir
    }


def delete_project(project_id):
    """Delete a project and all its contents."""
    import shutil
    project_dir = os.path.join(WORKSPACE_DIR, project_id)
    if not os.path.isdir(project_dir):
        return False
    shutil.rmtree(project_dir)
    logger.info(f"Workspace: Deleted project '{project_id}'")
    return True


# ============== ARTIFACT CRUD ==============

def save_artifact(project_id, content, title, artifact_type="analysis", query=None):
    """
    Save a query result or analysis as a persistent artifact.
    Returns the artifact filename.
    """
    project_dir = os.path.join(WORKSPACE_DIR, project_id)
    artifacts_dir = os.path.join(project_dir, "artifacts")

    if not os.path.isdir(project_dir):
        logger.error(f"Project '{project_id}' not found")
        return None

    os.makedirs(artifacts_dir, exist_ok=True)

    slug = _slugify(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{timestamp}_{slug}.md"
    filepath = os.path.join(artifacts_dir, filename)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    artifact_content = f"""---
title: {title}
type: {artifact_type}
created: {now}
query: {query or 'N/A'}
project: {project_id}
---

{content}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(artifact_content)

    # Update PROJECT.md with new artifact
    _append_to_project_md(project_id, "Insights Generated",
                          f"- [{title}](artifacts/{filename}) — {artifact_type} ({now})")

    # Log query if provided
    if query:
        _append_to_project_md(project_id, "Query History",
                              f"- \"{query}\" ({now})")

    logger.info(f"Workspace: Saved artifact '{filename}' to '{project_id}'")
    return filename


def list_artifacts(project_id):
    """List all artifacts for a project."""
    artifacts_dir = os.path.join(WORKSPACE_DIR, project_id, "artifacts")
    if not os.path.isdir(artifacts_dir):
        return []

    artifacts = []
    for f in sorted(os.listdir(artifacts_dir), reverse=True):
        if not f.endswith(".md"):
            continue
        filepath = os.path.join(artifacts_dir, f)
        metadata = _parse_frontmatter(filepath)
        stat = os.stat(filepath)
        artifacts.append({
            "filename": f,
            "title": metadata.get("title", f),
            "type": metadata.get("type", "unknown"),
            "created": metadata.get("created", ""),
            "query": metadata.get("query", ""),
            "size_kb": round(stat.st_size / 1024, 1)
        })

    return artifacts


def get_artifact(project_id, filename):
    """Read a specific artifact's full content."""
    filepath = os.path.join(WORKSPACE_DIR, project_id, "artifacts", filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


# ============== PROJECT CONTEXT FOR AGENT ==============

def get_project_context(project_id):
    """
    Build a context string from the project's state for injection into prompts.
    This gives the agent memory of past work on this project.
    """
    project = get_project(project_id)
    if not project:
        return ""

    context_parts = [
        f"=== ACTIVE PROJECT: {project['metadata'].get('title', project_id)} ===",
        f"Status: {project['metadata'].get('status', 'active')}",
        f"Description: {project['metadata'].get('description', 'N/A')}",
    ]

    # Add recent artifacts as context
    artifacts = project.get("artifacts", [])
    if artifacts:
        context_parts.append(f"\nPrevious Work ({len(artifacts)} artifacts):")
        for art in artifacts[:5]:  # Last 5 artifacts
            context_parts.append(f"  - {art['title']} ({art['type']}, {art['created']})")
            # Read first 500 chars of each artifact for context
            art_content = get_artifact(project_id, art["filename"])
            if art_content:
                # Strip frontmatter
                body = re.sub(r'^---.*?---\s*', '', art_content, flags=re.DOTALL).strip()
                if body:
                    context_parts.append(f"    Preview: {body[:500]}...")

    return "\n".join(context_parts)


# ============== HELPERS ==============

def _parse_frontmatter(filepath):
    """Parse YAML-like frontmatter from a markdown file."""
    if not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return {}

        metadata = {}
        for line in match.group(1).split("\n"):
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                metadata[key.strip()] = val.strip()

        return metadata
    except Exception as e:
        logger.warning(f"Failed to parse frontmatter from {filepath}: {e}")
        return {}


def _append_to_project_md(project_id, section_header, new_line):
    """Append a line under a specific section in PROJECT.md."""
    project_md_path = os.path.join(WORKSPACE_DIR, project_id, "PROJECT.md")
    if not os.path.exists(project_md_path):
        return

    try:
        with open(project_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find the section and append after it
        pattern = rf'(## {re.escape(section_header)}\n)(.*?)(?=\n## |\Z)'
        match = re.search(pattern, content, re.DOTALL)

        if match:
            section_content = match.group(2)
            # Remove placeholder text if present
            section_content = re.sub(r'_No .+?_\n?', '', section_content)
            updated_section = section_content.rstrip() + "\n" + new_line + "\n"
            content = content[:match.start(2)] + updated_section + content[match.end(2):]
        else:
            # Section not found, append at end
            content += f"\n## {section_header}\n{new_line}\n"

        # Update last_updated in frontmatter
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        content = re.sub(r'last_updated: .+', f'last_updated: {now}', content)

        with open(project_md_path, "w", encoding="utf-8") as f:
            f.write(content)

    except Exception as e:
        logger.warning(f"Failed to update PROJECT.md for '{project_id}': {e}")
