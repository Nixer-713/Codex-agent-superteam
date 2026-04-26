from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def import_pr_comments(root: Path, run_dir: Path, from_file: Path | None = None) -> tuple[Path, Path]:
    data = load_comment_data(root, from_file)
    comments = normalize_comments(data)
    yaml_path = run_dir / "github-review-comments.yaml"
    md_path = run_dir / "github-review-comments.md"
    write_comments_yaml(yaml_path, comments)
    write_comments_md(md_path, comments)
    legacy = run_dir / "pr-comments.md"
    legacy.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return yaml_path, md_path


def load_comment_data(root: Path, from_file: Path | None) -> Any:
    if from_file:
        if not from_file.exists():
            return {"comments": []}
        return json.loads(from_file.read_text(encoding="utf-8"))
    result = subprocess.run(
        ["gh", "pr", "view", "--json", "comments,reviews,reviewThreads"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh pr view failed")
    return json.loads(result.stdout or "{}")


def normalize_comments(data: Any) -> list[dict[str, str]]:
    raw_items: list[Any] = []
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        if isinstance(data.get("comments"), list):
            raw_items.extend(data["comments"])
        if isinstance(data.get("reviews"), list):
            raw_items.extend(data["reviews"])
        for thread in data.get("reviewThreads", []) if isinstance(data.get("reviewThreads"), list) else []:
            raw_items.extend(thread.get("comments", []) if isinstance(thread, dict) else [])
    comments: list[dict[str, str]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        author = item.get("author") or item.get("user") or {}
        comments.append(
            {
                "id": str(item.get("id") or item.get("databaseId") or f"comment-{index}"),
                "author": str(author.get("login") if isinstance(author, dict) else author or "unknown"),
                "path": str(item.get("path") or item.get("file") or ""),
                "line": str(item.get("line") or item.get("originalLine") or ""),
                "body": body,
                "url": str(item.get("url") or ""),
                "created_at": str(item.get("createdAt") or item.get("created_at") or ""),
                "source": "github_pr_review",
            }
        )
    return comments


def write_comments_yaml(path: Path, comments: list[dict[str, str]]) -> None:
    lines = [f"status: {'ok' if comments else 'empty'}", f"count: {len(comments)}", "comments:"]
    if not comments:
        lines[-1] = "comments: []"
    else:
        for comment in comments:
            lines.append(f"  - id: {comment['id']}")
            lines.append(f"    author: {comment['author']}")
            lines.append(f"    path: {comment['path']}")
            lines.append(f"    line: {comment['line']}")
            lines.append(f"    url: {comment['url']}")
            lines.append(f"    created_at: {comment['created_at']}")
            lines.append(f"    source: {comment['source']}")
            lines.append("    body: |")
            for body_line in comment["body"].splitlines() or [""]:
                lines.append(f"      {body_line}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_comments_md(path: Path, comments: list[dict[str, str]]) -> None:
    lines = ["# GitHub Review Comments", ""]
    if not comments:
        lines.append("No PR review comments imported.")
    for comment in comments:
        location = comment["path"] + (f":{comment['line']}" if comment["line"] else "")
        lines.extend(
            [
                f"## {comment['id']}",
                "",
                f"- author: {comment['author']}",
                f"- location: {location}",
                f"- line: {comment['line']}",
                f"- url: {comment['url']}",
                "",
                comment["body"],
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def has_review_comments(run_dir: Path) -> bool:
    path = run_dir / "github-review-comments.yaml"
    return path.exists() and "count: 0" not in path.read_text(encoding="utf-8") and "status: empty" not in path.read_text(encoding="utf-8")


def write_github_revise_decision(run_dir: Path) -> Path:
    if not has_review_comments(run_dir):
        raise RuntimeError("no GitHub review comments to convert into revise decision")
    path = run_dir / "review-decision.yaml"
    path.write_text(
        "decision: revise\n"
        "reason: GitHub review comments require revision.\n"
        "evidence:\n"
        "  - github-review-comments.yaml\n"
        f"decided_at: {datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8",
    )
    return path
