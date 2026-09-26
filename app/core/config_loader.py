# 加载并校验 configs 目录中的 YAML 配置，向业务代码提供类型化配置对象。
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import ConfigError


# _load_dotenv_once 函数，尽力加载 .env（未安装 python-dotenv 时静默跳过）。
def _load_dotenv_once() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


# require_env 函数，读取必需环境变量，缺失即抛 ConfigError（fail-fast）。
def require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise ConfigError(
            "env_var_missing",
            f"Required environment variable {var_name} is not set",
            {"env_var": var_name},
        )
    return value


# VersionedConfig 类，封装该模块中的相关状态与行为。
class VersionedConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    version: str = Field(min_length=1)


# CoreConfig 类，封装该模块中的相关状态与行为。
class CoreConfig(VersionedConfig):
    log_level: str
    log_path: str


# MineruConfig 类，封装该模块中的相关状态与行为。
class MineruConfig(VersionedConfig):
    backend: str
    max_pdf_size_mb: int
    timeout_s: int
    output_formats: list[str]
    api_base_url: str | None = None
    api_key_env: str | None = None
    model_version: str | None = None
    enable_formula: bool = True
    enable_table: bool = True
    poll_interval_s: int = 5
    retry: dict[str, Any]


# KnowledgeConfig 类，封装该模块中的相关状态与行为。
class KnowledgeConfig(VersionedConfig):
    model: str
    confidence_threshold: float
    needs_review_threshold: float
    max_context_tokens: int
    extractors: dict[str, Any]
    criteria_samples: int = 3


# RagConfig 已随 RAG 移除。


# MatlabConfig 类，封装该模块中的相关状态与行为。
class MatlabConfig(VersionedConfig):
    matlab_mcp_server_version: str
    session_isolation: str
    mcp_server_command: list[str]
    mcp_server_args: list[str] = Field(default_factory=list)
    startup_timeout_s: int
    tool_timeout_s: int
    working_dir_root: str
    require_human_approval_for_code_execution: bool
    high_risk_tools: list[str] = Field(default_factory=list)


# SimulinkConfig 类，封装该模块中的相关状态与行为。
class SimulinkConfig(VersionedConfig):
    simulink_agentic_toolkit_version: str
    session_isolation: str
    model_root: str
    human_approval_required_tools: list[str]
    simulation_timeout_s: int


# GraphConfig 类，封装该模块中的相关状态与行为。
class GraphConfig(VersionedConfig):
    checkpoint_backend: str
    checkpoint_path: str
    max_retries_per_node: int           # 保留旧字段，未被读取（细化字段见下）
    approval_timeout_s: int
    # 事件溯源 + 会话留存统一库（M0 起 tasks/events 落此库，重启不丢、可回放）
    session_db_path: str = "data/autoagent.db"
    # 任务生命周期与事件队列（原 orchestrator_service.py 硬编码）
    task_ttl_s: int = 7200          # 已终止任务保留秒数，超时后懒清理
    sse_queue_maxsize: int = 256    # 每任务 SSE 事件队列最大条数
    # 分层重试预算（默认值与代码常量一致，可在 graph.yaml 中覆盖）
    l1_budget: int = 2     # 瞬时错误（超时/MCP busy）重试次数
    l2_budget: int = 2     # 代码级错误（语法/运行时）重试次数
    l3_budget: int = 1     # 方案级错误（不收敛/架构错）回滚次数
    l4_budget: int = 1     # 知识级错误（缺参数/抽错公式）重抽次数
    calib_budget: int = 4  # 结果校准最大轮数（跑通但指标不达标）


# ModelConfig 类，LLM 配置。连接信息（key/base_url/模型名）走 .env，此处仅留行为参数。
class ModelConfig(VersionedConfig):
    provider: str = "openai"
    api_key_env: str = "LLM_API_KEY"
    base_url_env: str = "LLM_BASE_URL"
    default_llm_env: str = "LLM_DEFAULT_MODEL"
    planner_llm_env: str = "LLM_PLANNER_MODEL"
    request_timeout_s: int = 120
    sdk_max_retries: int = 1         # OpenAI SDK 内部自动重试次数（0=由应用层全权控制重试与回滚）
    max_structured_retries: int = 2
    temperature: dict[str, float] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)  # 透传 chat.completions 的供应商专属参数（如 enable_thinking）

    # base_url 属性，从环境变量解析 LLM base_url（缺失即 fail-fast）。
    @property
    def base_url(self) -> str:
        return require_env(self.base_url_env)

    # default_llm 属性，从环境变量解析默认模型名。
    @property
    def default_llm(self) -> str:
        return require_env(self.default_llm_env)

    # planner_llm 属性，从环境变量解析规划模型名（可空，回退默认）。
    @property
    def planner_llm(self) -> str | None:
        return os.getenv(self.planner_llm_env) or None


# AppConfig 类，封装该模块中的相关状态与行为。
class AppConfig(BaseModel):
    core: CoreConfig
    mineru: MineruConfig
    knowledge: KnowledgeConfig
    matlab: MatlabConfig
    simulink: SimulinkConfig
    graph: GraphConfig
    model: ModelConfig


CONFIG_MODELS: dict[str, type[VersionedConfig]] = {
    "core": CoreConfig,
    "mineru": MineruConfig,
    "knowledge": KnowledgeConfig,
    "matlab": MatlabConfig,
    "simulink": SimulinkConfig,
    "graph": GraphConfig,
    "model": ModelConfig,
}


# load_yaml 函数，加载外部文件或配置并转换为内部对象。
def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError("config_missing", "Required config file is missing", {"file": path.name})
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
    except yaml.YAMLError as exc:
        raise ConfigError("config_yaml_invalid", "Config file is not valid YAML", {"file": path.name}) from exc
    if not isinstance(data, dict):
        raise ConfigError("config_invalid", "Config file must contain a mapping", {"file": path.name})
    return data


# load_config 函数，加载外部文件或配置并转换为内部对象。
def load_config(config_dir: str | Path = "configs") -> AppConfig:
    _load_dotenv_once()
    base = Path(config_dir)
    values: dict[str, VersionedConfig] = {}
    for name, model in CONFIG_MODELS.items():
        try:
            values[name] = model.model_validate(load_yaml(base / f"{name}.yaml"))
        except ValidationError as exc:
            raise ConfigError(
                "config_schema_invalid",
                f"{name} config failed schema validation",
                {"file": f"{name}.yaml", "errors": exc.errors()},
            ) from exc
    return AppConfig.model_validate(values)


# validate_required_secrets 函数，启动时校验必需密钥/连接是否就位（fail-fast）。
def validate_required_secrets(config: AppConfig) -> None:
    required: list[str] = [
        config.model.api_key_env,
        config.model.base_url_env,
        config.model.default_llm_env,
    ]
    if config.mineru.api_key_env:
        required.append(config.mineru.api_key_env)
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ConfigError(
            "env_var_missing",
            "Required environment variables are not set",
            {"env_vars": missing},
        )
