# 任务事件上下文：用 contextvar 把「当前任务的事件出口」挂到执行线程上，
# 让无 task_id 的深层组件（如 LLMClient）也能发透明化事件。
# 编排层在任务线程入口 set，线程内所有同步调用共享（LangGraph 节点 / 知识抽取均在同一线程）。
from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Callable

logger = logging.getLogger(__name__)

# 发射器签名：(event_type, payload_dict)
Emitter = Callable[[str, dict], None]

_emitter: ContextVar[Emitter | None] = ContextVar("task_event_emitter", default=None)


# set_event_emitter 函数，在当前执行线程挂上事件出口，返回 token 供 finally 复位。
def set_event_emitter(fn: Emitter) -> Token:
    return _emitter.set(fn)


# reset_event_emitter 函数，线程收尾时复位（配合 set 返回的 token）。
def reset_event_emitter(token: Token) -> None:
    _emitter.reset(token)


# emit_event 函数，向当前任务发一条事件；无上下文（如 CLI/测试直调）时静默跳过。
def emit_event(event_type: str, **payload) -> None:
    fn = _emitter.get()
    if fn is None:
        return
    try:
        fn(event_type, payload)
    except Exception:  # 事件发射失败绝不影响主流程
        logger.debug("emit_event failed for %s", event_type, exc_info=True)
