# 加载并校验 prompt YAML 文件。
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.exceptions import ConfigError


# load_prompt 函数，加载外部文件或配置并转换为内部对象。
def load_prompt(name: str, prompt_dir: str | Path = "app/prompts") -> dict[str, Any]:
    path = Path(prompt_dir) / f"{name}.yaml"
    if not path.exists():
        raise ConfigError("prompt_missing", "Prompt file is missing", {"prompt": name})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = {"version", "role", "system", "instructions", "output_schema"}
    missing = required.difference(data)
    if missing:
        raise ConfigError("prompt_invalid", "Prompt file is missing required fields", {"prompt": name, "missing": sorted(missing)})
    return data
