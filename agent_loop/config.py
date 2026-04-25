from __future__ import annotations

from pathlib import Path


DEFAULT_CONFIG = {
    "agents": {"default_agent_id": "worker-1", "max_parallel": 2},
    "validation": {"default_commands": []},
    "risk": {"low_files": 3, "low_lines": 150, "medium_files": 8, "medium_lines": 500},
    "git": {"branch_prefix": "codex/", "require_clean_worktree": True},
    "github": {"draft_pr": True, "require_ci_success": True},
    "privacy": {"enabled": True},
}


def load_config(root: Path) -> dict:
    config = copy_config(DEFAULT_CONFIG)
    path = root / ".agent-loop" / "config.yaml"
    if not path.exists():
        return config
    parsed = parse_simple_yaml(path.read_text(encoding="utf-8"))
    merge_dict(config, parsed)
    return config


def copy_config(value):
    if isinstance(value, dict):
        return {key: copy_config(item) for key, item in value.items()}
    if isinstance(value, list):
        return list(value)
    return value


def merge_dict(base: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge_dict(base[key], value)
        else:
            base[key] = value


def parse_simple_yaml(text: str) -> dict:
    data: dict = {}
    current_section: str | None = None
    current_list_key: str | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" ") and ":" in raw:
            key, value = raw.split(":", 1)
            current_section = key.strip()
            if value.strip():
                data[current_section] = parse_scalar(value.strip())
                current_section = None
            else:
                data[current_section] = {}
            current_list_key = None
            continue
        if current_section and raw.startswith("  ") and not raw.startswith("    ") and ":" in raw:
            key, value = raw.strip().split(":", 1)
            value = value.strip()
            if value:
                data[current_section][key] = parse_scalar(value)
                current_list_key = None
            else:
                data[current_section][key] = []
                current_list_key = key
            continue
        if current_section and current_list_key and raw.strip().startswith("- "):
            data[current_section][current_list_key].append(raw.strip()[2:].strip())
            continue
        raise ValueError(f"unsupported config line: {raw}")
    return data


def parse_scalar(value: str):
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.isdigit():
        return int(value)
    return value.strip('"\'')
