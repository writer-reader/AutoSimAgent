# 测试共享夹具：路径注入 + 假 LLM 客户端 + 事件库隔离。
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from app.core.config_loader import ModelConfig
from app.events.store import EventStore


# _isolated_event_store 夹具（autouse），每个用例用独立的临时事件库，避免污染开发库。
@pytest.fixture(autouse=True)
def _isolated_event_store(tmp_path):
    from app.services.orchestrator_service import registry
    store = EventStore(tmp_path / "test_agent.db")
    registry.attach_store(store)
    # 复位 MATLAB MCP 单例（防止跨用例泄漏：某些用例可能触发 get_matlab_client）
    from app.tools import mcp_factory
    mcp_factory._singleton = None  # noqa: SLF001
    yield store
    store.close()
    # 重置 workflow 缓存与 matlab 单例（若有）
    from app.services.orchestrator_service import registry as reg
    for tid in list(reg._workflows.keys()):  # noqa: SLF001
        reg._workflows.pop(tid, None)  # noqa: SLF001
    mcp_factory._singleton = None  # noqa: SLF001


# _FakeMsg / _FakeResp，模拟 openai chat.completions 返回结构。
class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})


class _FakeResp:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeMsg(content)]


# FakeChatClient 类，可编排多轮返回的假 OpenAI 兼容客户端。
class FakeChatClient:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[dict] = []
        completions = type("C", (), {"create": self._create})()
        self.chat = type("Chat", (), {"completions": completions})()

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        out = self._outputs.pop(0) if self._outputs else "{}"
        return _FakeResp(out)


# fake_model_config 夹具，构造不触发真实 env 的最小 ModelConfig。
@pytest.fixture
def fake_model_config(monkeypatch) -> ModelConfig:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "test-model")
    return ModelConfig(version="1.0", temperature={"planner": 0.2, "extractor": 0.0, "codegen": 0.1})


@pytest.fixture
def make_fake_chat():
    return FakeChatClient
