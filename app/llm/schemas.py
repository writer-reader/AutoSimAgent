# LLM 调用的通用消息结构与便捷构造函数。
from __future__ import annotations

from pydantic import BaseModel


# Message 类，表示一条对话消息（OpenAI chat 格式）。
class Message(BaseModel):
    role: str  # system | user | assistant
    content: str


# system 函数，构造 system 角色消息。
def system(content: str) -> Message:
    return Message(role="system", content=content)


# user 函数，构造 user 角色消息。
def user(content: str) -> Message:
    return Message(role="user", content=content)


# assistant 函数，构造 assistant 角色消息。
def assistant(content: str) -> Message:
    return Message(role="assistant", content=content)
