# 定义项目统一异常体系，确保错误码、用户消息和内部细节分离。
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
# ControlAgentError 类，封装该模块中的相关状态与行为。
class ControlAgentError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False

    # __str__ 方法，返回便于日志和调试阅读的错误文本。
    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    # to_public_dict 函数，封装该模块的一段可复用业务逻辑。
    def to_public_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


# ConfigError 类，封装该模块中的相关状态与行为。
class ConfigError(ControlAgentError):
    pass


# IngestionError 类，封装该模块中的相关状态与行为。
class IngestionError(ControlAgentError):
    pass


# DownloadError 类，封装该模块中的相关状态与行为。
class DownloadError(IngestionError):
    pass


# ParseError 类，封装该模块中的相关状态与行为。
class ParseError(IngestionError):
    pass


# ExtractionError 类，封装该模块中的相关状态与行为。
class ExtractionError(ControlAgentError):
    pass


# RagError 类，封装该模块中的相关状态与行为。
class RagError(ControlAgentError):
    pass


# LLMError 类，封装 LLM 调用相关错误（请求失败、结构化输出不合法等）。
class LLMError(ControlAgentError):
    pass


# WorkflowError 类，封装该模块中的相关状态与行为。
class WorkflowError(ControlAgentError):
    pass


# ApprovalError 类，封装该模块中的相关状态与行为。
class ApprovalError(ControlAgentError):
    pass


# ToolExecutionError 类，封装该模块中的相关状态与行为。
class ToolExecutionError(ControlAgentError):
    pass


# MatlabExecutionError 类，封装该模块中的相关状态与行为。
class MatlabExecutionError(ToolExecutionError):
    pass


# SimulinkExecutionError 类，封装该模块中的相关状态与行为。
class SimulinkExecutionError(ToolExecutionError):
    pass


# VerificationError 类，封装该模块中的相关状态与行为。
class VerificationError(ControlAgentError):
    pass
