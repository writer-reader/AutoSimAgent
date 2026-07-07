# 初始化结构化日志输出，统一携带 trace、task 和 paper 等追踪字段。
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging import LogRecord
from pathlib import Path
from typing import Any


# JsonFormatter 类，封装该模块中的相关状态与行为。
class JsonFormatter(logging.Formatter):
    # format 函数，封装该模块的一段可复用业务逻辑。
    def format(self, record: LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "event": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
            "paper_id": getattr(record, "paper_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# configure_logging 函数，初始化并配置运行时组件。
def configure_logging(level: str = "INFO", log_path: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    formatter = JsonFormatter()
    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), handlers=handlers, force=True)
