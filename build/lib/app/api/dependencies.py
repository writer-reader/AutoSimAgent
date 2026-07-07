# 集中定义 FastAPI 依赖注入入口。
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config_loader import AppConfig, load_config, validate_required_secrets
from app.services.orchestrator_service import OrchestratorService
from app.services.paper_service import PaperService

# 项目根（app/api/dependencies.py → parents[2]），使 configs 定位不依赖 CWD。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# get_config 函数，加载并缓存 AppConfig（进程级单例）。
@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    config = load_config(_PROJECT_ROOT / "configs")
    validate_required_secrets(config)
    return config


# get_paper_service 函数，构造 PaperService（含 MinerU 客户端）。
def get_paper_service() -> PaperService:
    from app.ingestion.mineru_client import MineruClient
    return PaperService(MineruClient(get_config().mineru))


# get_orchestrator 函数，构造编排服务（进程级单例）。
@lru_cache(maxsize=1)
def get_orchestrator() -> OrchestratorService:
    return OrchestratorService(get_config())
