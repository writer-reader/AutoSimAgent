# 测试配置加载：所有必需配置文件可读、schema 正确。
from __future__ import annotations

from pathlib import Path

from app.core.config_loader import load_config


# test_load_config_reads_all_required_config_files 测试函数，验证目标行为符合预期。
def test_load_config_reads_all_required_config_files() -> None:
    config = load_config(Path(__file__).resolve().parents[1] / "configs")

    assert config.mineru.backend == "api"
    assert config.matlab.session_isolation == "per_user"
    assert config.model.provider == "deepseek"
    # 对齐 matlab-mcp-server v0.12.0 真实工具名（model_edit/model_test 不存在）
    assert "evaluate_matlab_code" in config.matlab.high_risk_tools
    assert "run_matlab_test_file" in config.matlab.high_risk_tools


# test_rag_config_removed 测试函数，确认 RAG 配置已彻底移除。
def test_rag_config_removed() -> None:
    config = load_config(Path(__file__).resolve().parents[1] / "configs")
    assert not hasattr(config, "rag")
