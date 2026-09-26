# 基于 LLM 的调用封装：文本补全 + 结构化输出（Pydantic 校验失败回喂重试）+ token 用量透明化。
from __future__ import annotations

import json
import time
from typing import Any, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config_loader import ModelConfig, require_env
from app.core.exceptions import LLMError
from app.events.context import emit_event
from app.llm.schemas import Message

try:  # openai SDK 与 DeepSeek 完全兼容，未安装时给出清晰报错
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]

T = TypeVar("T", bound=BaseModel)

_MessageLike = Message | dict[str, str]


# LLMClient 类，封装对 DeepSeek 的调用与结构化输出保障。
class LLMClient:
    # __init__ 方法，初始化底层 OpenAI 兼容客户端。
    def __init__(self, config: ModelConfig, api_key: str | None = None, client: Any | None = None) -> None:
        self.config = config
        if client is not None:  # 允许注入 mock，便于测试
            self.client = client
        else:
            if OpenAI is None:
                raise LLMError("llm_sdk_missing", "openai package is not installed", {})
            key = api_key or require_env(config.api_key_env)
            # max_retries 显式配置：SDK 默认 2 次内部重试会把长超时静默放大数倍，且应用层无感知
            self.client = OpenAI(
                api_key=key, base_url=config.base_url,
                timeout=config.request_timeout_s, max_retries=config.sdk_max_retries,
            )

    # _model_for 函数，按角色选择模型（planner 用重模型，其余用默认）。
    def _model_for(self, role: str) -> str:
        if role == "planner" and self.config.planner_llm:
            return self.config.planner_llm
        return self.config.default_llm

    # _temperature_for 函数，按角色取温度，缺省 0.2。
    def _temperature_for(self, role: str) -> float:
        return self.config.temperature.get(role, 0.2)

    # _payload 函数，将消息序列规范为 OpenAI chat 格式。
    @staticmethod
    def _payload(messages: Sequence[_MessageLike]) -> list[dict[str, str]]:
        return [m.model_dump() if isinstance(m, Message) else dict(m) for m in messages]

    # _emit_llm_call 方法，向当前任务发一条「LLM 调用中」透明化事件（无任务上下文时静默跳过）。
    @staticmethod
    def _emit_llm_call(label: str | None, role: str, model_name: str) -> None:
        emit_event("llm_call", label=label or f"LLM 调用（{role}）", role=role, model=model_name)

    # _emit_usage 函数，调用结束后发 token 用量事件（resp.usage 为 OpenAI 兼容标准字段）。
    @staticmethod
    def _emit_usage(label: str | None, role: str, model_name: str, resp: Any, duration_s: float) -> None:
        usage = getattr(resp, "usage", None)
        emit_event(
            "llm_usage",
            label=label or f"LLM 调用（{role}）", role=role, model=model_name,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            duration_s=round(duration_s, 1),
        )

    # complete 函数，返回一次对话补全的纯文本结果。
    def complete(
        self,
        messages: Sequence[_MessageLike],
        *,
        role: str = "planner",
        model: str | None = None,
        temperature: float | None = None,
        label: str | None = None,
        **kwargs: Any,
    ) -> str:
        model_name = model or self._model_for(role)
        self._emit_llm_call(label, role, model_name)
        # 供应商专属参数必须走 SDK 的 extra_body 形参（并进请求体）；
        # 直接 ** 展开会被 SDK 当未知 kwarg 拒绝（TypeError）。
        vendor_kwargs = {"extra_body": self.config.extra_body} if self.config.extra_body else {}
        started = time.monotonic()
        try:
            resp = self.client.chat.completions.create(
                model=model_name,
                messages=self._payload(messages),
                temperature=self._temperature_for(role) if temperature is None else temperature,
                **vendor_kwargs,
                **kwargs,
            )
        except Exception as exc:  # 网络/服务端错误：标记可重试，交由上层错误路由
            raise LLMError("llm_request_failed", f"LLM request failed: {str(exc)[:300]}", {
                "error": str(exc),
                "type": type(exc).__name__,
                "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                "body": str(getattr(getattr(exc, "response", None), "text", ""))[:500],
            }, retryable=True) from exc
        self._emit_usage(label, role, model_name, resp, time.monotonic() - started)
        return resp.choices[0].message.content or ""

    # structured 函数，强制 JSON 输出并用 Pydantic 校验；失败则带报错回喂重试。
    def structured(
        self,
        messages: Sequence[_MessageLike],
        schema: Type[T],
        *,
        role: str = "extractor",
        model: str | None = None,
        temperature: float | None = None,
        max_retries: int | None = None,
        label: str | None = None,
    ) -> T:
        retries = self.config.max_structured_retries if max_retries is None else max_retries
        payload = self._payload(messages)
        model_name = model or self._model_for(role)
        self._emit_llm_call(label, role, model_name)
        last_error: Exception | None = None
        vendor_kwargs = {"extra_body": self.config.extra_body} if self.config.extra_body else {}
        for _ in range(retries + 1):
            started = time.monotonic()
            try:
                resp = self.client.chat.completions.create(
                    model=model_name,
                    messages=payload,
                    temperature=self._temperature_for(role) if temperature is None else temperature,
                    response_format={"type": "json_object"},
                    **vendor_kwargs,
                )
            except Exception as exc:
                raise LLMError("llm_request_failed", f"LLM request failed: {str(exc)[:300]}", {
                    "error": str(exc),
                    "type": type(exc).__name__,
                    "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                    "body": str(getattr(getattr(exc, "response", None), "text", ""))[:500],
                }, retryable=True) from exc
            # 每次实际请求（含校验失败回喂重试）都记 usage
            self._emit_usage(label, role, model_name, resp, time.monotonic() - started)
            content = resp.choices[0].message.content or ""
            try:
                return schema.model_validate(json.loads(content))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                payload.append({"role": "assistant", "content": content})
                payload.append({"role": "user", "content": _repair_prompt(schema, exc)})
        raise LLMError(
            "llm_structured_invalid",
            "LLM failed to produce schema-valid JSON",
            {"error": str(last_error), "attempts": retries + 1},
        )


# _repair_prompt 函数，构造带 schema 与校验错误的纠错提示。
def _repair_prompt(schema: Type[BaseModel], error: Exception) -> str:
    return (
        "你上一条回复不符合要求的 JSON schema。\n"
        f"校验错误：\n{error}\n\n"
        "请只返回一个符合以下 JSON Schema 的 JSON 对象，不要任何多余文字或 Markdown 代码块：\n"
        f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )
