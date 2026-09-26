# 初始化结构化日志输出，统一携带 trace、task、paper、request 等追踪字段。
# 字段值来自 app.core.log_context 的 contextvar（LogContextFilter 注入），
# 文件输出用 RotatingFileHandler 防止长跑无限增长。
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging import LogRecord
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.log_context import LogContextFilter

# 默认轮转参数：单文件 10MB，保留 5 个历史（约 60MB 上限）。
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


# JsonFormatter 类，把日志记录序列化为一行 JSON（追踪字段缺失时为 "-"）。
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
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# configure_logging 函数，初始化并配置运行时组件（控制台 + 轮转文件，均挂追踪字段过滤器）。
def configure_logging(
    level: str = "INFO",
    log_path: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        )

    formatter = JsonFormatter()
    context_filter = LogContextFilter()
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)

    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), handlers=handlers, force=True)
