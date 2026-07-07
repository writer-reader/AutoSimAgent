# DeepSeek（OpenAI 兼容）LLM 客户端：文本补全 + 结构化输出（Pydantic 校验失败回喂重试）。
from __future__ import annotations

import json
from typing import Any, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config_loader import ModelConfig, require_env
from app.core.exceptions import LLMError
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
            self.client = OpenAI(api_key=key, base_url=config.base_url, timeout=config.request_timeout_s)

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

    # complete 函数，返回一次对话补全的纯文本结果。
    def complete(
        self,
        messages: Sequence[_MessageLike],
        *,
        role: str = "planner",
        model: str | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=model or self._model_for(role),
                messages=self._payload(messages),
                temperature=self._temperature_for(role) if temperature is None else temperature,
                **kwargs,
            )
        except Exception as exc:  # 网络/服务端错误：标记可重试，交由上层错误路由
            raise LLMError("llm_request_failed", "LLM request failed", {"error": str(exc)}, retryable=True) from exc
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
    ) -> T:
        retries = self.config.max_structured_retries if max_retries is None else max_retries
        payload = self._payload(messages)
        last_error: Exception | None = None
        for _ in range(retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=model or self._model_for(role),
                    messages=payload,
                    temperature=self._temperature_for(role) if temperature is None else temperature,
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                raise LLMError("llm_request_failed", "LLM request failed", {"error": str(exc)}, retryable=True) from exc
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
