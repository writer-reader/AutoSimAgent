# 环境变量处理分析报告

## 执行摘要

对项目 `Y:\AI\myproject\mycontrolagent\control_agent\` 的环境变量处理方式进行全面检查，发现项目采用 **YAML 配置文件 + 环境变量占位符** 的设计模式，但**环境变量尚未被实际加载和使用**。

---

## 1. 环境变量处理机制

### 1.1 配置系统架构

项目使用分层的配置管理方案：

```
configs/*.yaml  →  config_loader.py  →  AppConfig (Pydantic 模型)
```

- **配置存储**: YAML 文件存储在 `configs/` 目录
- **配置加载**: `app/core/config_loader.py` 负责加载和校验
- **配置模型**: 使用 Pydantic `BaseModel` 定义类型安全的配置类

### 1.2 环境变量占位符设计

在 YAML 配置中，使用 `_env` 后缀的字段来存储**环境变量的名称**（而非值），实现配置与敏感信息分离：

| 配置文件 | 字段名 | 环境变量名 | 用途 |
|---------|--------|-----------|------|
| `core.yaml` | `celery_broker_url_env` | `CELERY_BROKER_URL` | Celery 消息队列 URL |
| `core.yaml` | `celery_result_backend_env` | `CELERY_RESULT_BACKEND` | Celery 结果后端 URL |
| `mineru.yaml` | `api_key_env` | `MINERU_API_KEY` | Mineru API 密钥 |
| `model.yaml` | `qwen_api_key_env` | `QWEN_API_KEY` | 通义千问 API 密钥 |

**示例** (`configs/model.yaml`):
```yaml
version: "1.0"
default_llm: "qwen-plus"
embedding_model: "text-embedding-v4"
qwen_api_key_env: "QWEN_API_KEY"  # 环境变量名，而非键值
embedding_batch_size: 32
temperature:
  planner: 0.2
  extractor: 0.0
  codegen: 0.1
```

### 1.3 配置模型定义

**文件**: `app/core/config_loader.py`

```python
# 核心配置
class CoreConfig(VersionedConfig):
    log_level: str
    log_path: str
    celery_broker_url_env: str  # 存储环境变量名
    celery_result_backend_env: str

# Mineru 配置
class MineruConfig(VersionedConfig):
    backend: str
    api_key_env: str | None = None  # 存储环境变量名
    # ...

# 模型配置
class ModelConfig(VersionedConfig):
    default_llm: str
    qwen_api_key_env: str  # 存储环境变量名
    # ...
```

---

## 2. 发现的问题

### 2.1 环境变量未被实际加载 ⚠️

**关键发现**: 搜索整个代码库，`os.getenv()` 或 `os.environ.get()` **没有被调用**来读取这些 `_env` 字段指定的环境变量。

**证据**:
- 在 `app/` 目录下所有 Python 文件中搜索 `os.getenv`、`environ.get`、`api_key_env` 等关键词，无匹配结果
- `config_loader.py` 仅加载 YAML 配置到 Pydantic 模型，但**没有进一步读取环境变量**

**影响**:
- 配置中的 `QWEN_API_KEY`、`MINERU_API_KEY`、`CELERY_BROKER_URL` 等环境变量**不会被加载**
- 应用运行时会出现 API 密钥缺失、连接字符串缺失等错误

### 2.2 缺少 `.env` 文件支持

**检查结果**:
- 项目根目录和 `control_agent/` 目录下**没有** `.env` 或 `.env.example` 文件
- `requirements.txt` 中**没有** `python-dotenv` 依赖

**建议**:
- 创建 `.env.example` 模板文件，列出所有需要的环境变量
- 可选安装 `python-dotenv` 以支持从 `.env` 文件加载环境变量

### 2.3 仅有的环境变量使用

**文件**: `run_backend.py`

```python
import os

def main() -> None:
    host = os.getenv("CONTROL_AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("CONTROL_AGENT_PORT", "8000"))
    uvicorn.run("app.api.main:app", host=host, port=port, reload=False)
```

这是**唯一实际使用环境变量**的代码，用于配置 FastAPI 服务监听地址和端口。

---

## 3. 配置文件清单

### 3.1 项目根目录

| 文件 | 存在 | 说明 |
|------|------|------|
| `.env` | ❌ | 不存在 |
| `.env.example` | ❌ | 不存在 |
| `config.py` | ❌ | 不存在 |
| `settings.py` | ❌ | 不存在 |
| `config.yaml` / `config.yml` | ❌ | 不存在 |
| `pyproject.toml` | ✅ | 存在，定义项目元数据和依赖 |

### 3.2 `configs/` 目录

所有配置文件均存在：

| 文件 | 包含环境变量字段 |
|------|----------------|
| `core.yaml` | ✅ `celery_broker_url_env`, `celery_result_backend_env` |
| `graph.yaml` | ❌ |
| `knowledge.yaml` | ❌ |
| `matlab.yaml` | ❌ |
| `mineru.yaml` | ✅ `api_key_env` |
| `model.yaml` | ✅ `qwen_api_key_env` |
| `rag.yaml` | ❌ |
| `simulink.yaml` | ❌ |

### 3.3 `app/` 目录配置模块

- **`app/core/config_loader.py`**: 主要的配置加载模块
- 无其他独立配置模块（`config.py`、`settings.py` 不存在）

---

## 4. 修复建议

### 4.1 实现环境变量加载逻辑

在 `config_loader.py` 中添加环境变量解析：

```python
import os

def resolve_env_var(config: VersionedConfig) -> dict[str, Any]:
    """将配置中的 _env 字段解析为实际环境变量值"""
    result = {}
    for field_name, value in config.model_dump().items():
        if field_name.endswith("_env") and isinstance(value, str):
            # 读取环境变量值
            env_var_name = value
            env_value = os.getenv(env_var_name)
            if env_value is None:
                raise ConfigError(
                    "env_var_missing",
                    f"Required environment variable {env_var_name} is not set",
                    {"env_var": env_var_name}
                )
            # 将 _env 字段替换为实际值（去掉 _env 后缀）
            actual_field = field_name.replace("_env", "")
            result[actual_field] = env_value
        else:
            result[field_name] = value
    return result
```

### 4.2 创建 `.env.example` 文件

```bash
# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# API Keys
MINERU_API_KEY=your_mineru_api_key_here
QWEN_API_KEY=your_qwen_api_key_here

# Server
CONTROL_AGENT_HOST=127.0.0.1
CONTROL_AGENT_PORT=8000
```

### 4.3 添加 `python-dotenv` 依赖

在 `pyproject.toml` 或 `requirements.txt` 中添加：

```toml
dependencies = [
  "fastapi>=0.110",
  "pydantic>=2",
  "PyYAML>=6",
  "uvicorn>=0.27",
  "python-dotenv>=1.0",  # 新增
]
```

在应用启动时加载 `.env`：

```python
# app/__init__.py 或 run_backend.py
from dotenv import load_dotenv
load_dotenv()
```

---

## 5. 代码片段汇总

### 5.1 配置加载器 (`app/core/config_loader.py`)

```python
# 加载并校验 configs 目录中的 YAML 配置，向业务代码提供类型化配置对象。
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import ConfigError

class CoreConfig(VersionedConfig):
    log_level: str
    log_path: str
    celery_broker_url_env: str  # 环境变量名占位符
    celery_result_backend_env: str

class ModelConfig(VersionedConfig):
    default_llm: str
    qwen_api_key_env: str  # 环境变量名占位符
    embedding_batch_size: int
    temperature: dict[str, float]

def load_config(config_dir: str | Path = "configs") -> AppConfig:
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
```

### 5.2 启动脚本 (`run_backend.py`)

```python
# 后端服务启动入口。运行后会启动 FastAPI，并加载 app.api.main:app。
import os
import uvicorn

def main() -> None:
    host = os.getenv("CONTROL_AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("CONTROL_AGENT_PORT", "8000"))
    uvicorn.run("app.api.main:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
```

### 5.3 YAML 配置示例 (`configs/model.yaml`)

```yaml
version: "1.0"
default_llm: "qwen-plus"
embedding_model: "text-embedding-v4"
qwen_api_key_env: "QWEN_API_KEY"  # 环境变量名称（而非值）
embedding_batch_size: 32
temperature:
  planner: 0.2
  extractor: 0.0
  codegen: 0.1
```

---

## 6. 总结

### 现状
- ✅ 配置了完善的 YAML 配置系统
- ✅ 使用 Pydantic 进行类型安全的配置校验
- ✅ 设计了环境变量占位符机制 (`_env` 字段)
- ❌ **环境变量未被实际加载和使用**
- ❌ 缺少 `.env` 文件和 `python-dotenv` 支持

### 风险
- 应用无法读取 API 密钥等敏感配置
- Celery 等外部服务连接会失败
- 配置系统设计完整但**未生效**

### 优先级建议
1. **高优先级**: 实现 `config_loader.py` 中的环境变量解析逻辑
2. **高优先级**: 创建 `.env.example` 并提供给部署人员
3. **中优先级**: 集成 `python-dotenv` 支持
4. **低优先级**: 添加配置验证测试用例

---

**分析完成时间**: 2026-07-02  
**分析范围**: `Y:\AI\myproject\mycontrolagent\control_agent\`
