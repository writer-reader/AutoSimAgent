# 日志追踪上下文：用 contextvar 保存当前任务/请求的追踪字段，
# 由 LogContextFilter 注入到每条日志记录上（与 events/context.py 的事件出口同一模式）。
# 编排层在任务线程入口 set，线程内所有日志自动携带 task_id/paper_id/trace_id；
# HTTP 中间件在请求入口 set request_id，端点内日志自动携带。
from __future__ import annotations

import logging
from contextvars import ContextVar, Token

_log_context: ContextVar[dict[str, str]] = ContextVar("log_context", default={})

# 可注入字段白名单：与 logging_config.JsonFormatter 的输出字段对齐。
TRACKED_FIELDS = ("trace_id", "task_id", "paper_id", "request_id")


# set_log_context 函数，合并写入当前上下文的追踪字段，返回 token 供 finally 复位。
# 值为 None 的字段忽略（便于调用方直接透传可能缺省的 paper_id）。
def set_log_context(**fields: str | None) -> Token:
    merged = {**_log_context.get(), **{k: v for k, v in fields.items() if v}}
    return _log_context.set(merged)


# reset_log_context 函数，恢复 set_log_context 之前的上下文。
def reset_log_context(token: Token) -> None:
    _log_context.reset(token)


# get_log_context 函数，读取当前追踪字段快照（测试/调试用）。
def get_log_context() -> dict[str, str]:
    return dict(_log_context.get())


# LogContextFilter 类，把 contextvar 里的追踪字段补到每条 LogRecord 上。
# 记录上已有值的字段（调用方显式 extra）不覆盖；没有的补 "-"，保证 JsonFormatter 输出稳定。
class LogContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _log_context.get()
        for field in TRACKED_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, ctx.get(field, "-"))
        return True
