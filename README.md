# AutoSimAgent

面向控制工程论文的全自动仿真代理——读入论文，提取知识，生成并验证 MATLAB/Simulink 代码，全流程由 LLM + MCP 驱动。

## 功能概览

```
论文 PDF
   ↓  MinerU 解析
知识抽取（系统参数、验收标准）
   ↓  LLM 规划
MATLAB 代码生成
   ↓  MATLAB MCP 执行
验证（指标比对 + 人工审批可选）
   ↓
复现结果 / 产物图片
```

- **多层回滚**：执行失败按 L1（重执行）→ L2（重生成）→ L3（重规划）→ L4（重提取知识）→ L5（终止）逐层降级
- **人工干预**：`auto_approve=False` 时图在代码审批节点暂停，支持前端编辑后恢复
- **实时进度**：SSE 流式推送节点状态到前端
- **OpenAI 兼容接口**：换供应商只需改 `.env`，不动代码

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + LangGraph |
| LLM | DeepSeek（OpenAI 兼容，可替换） |
| 论文解析 | MinerU 云 API |
| 代码执行 | MATLAB via MCP |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| 配置 | YAML (`configs/`) + 环境变量 (`.env`) |

## 目录结构

```
├── app/
│   ├── api/          # FastAPI 路由与依赖注入
│   ├── core/         # 配置加载、日志、异常
│   ├── graph/        # LangGraph 工作流（节点、状态、路由）
│   ├── ingestion/    # MinerU 论文解析与下载
│   ├── knowledge/    # 知识抽取与后处理
│   ├── llm/          # LLM 客户端（OpenAI SDK 封装）
│   ├── prompts/      # Prompt 模板（YAML）
│   ├── services/     # 业务服务层
│   └── tools/        # MATLAB MCP 客户端与工具封装
├── configs/          # YAML 配置（不含密钥）
├── frontend/         # React 前端
├── scripts/          # 命令行工具（摄取、端到端联跑、任务查看）
├── tests/            # pytest 测试套件
├── .env.example      # 环境变量模板
├── pyproject.toml    # Python 项目配置与依赖
└── run_backend.py    # 后端启动入口
```

## 快速开始

### 1. 环境准备

```bash
# Python 3.11+
pip install -e ".[dev]"

# 或使用 requirements.txt
pip install -r requirements.txt
```

### 2. 配置密钥

```bash
cp .env.example .env
# 编辑 .env，填入真实密钥：
# LLM_API_KEY      — LLM API 密钥（默认 DeepSeek）
# LLM_BASE_URL     — API Base URL
# MINERU_API_KEY   — MinerU 云 API 密钥
```

### 3. 启动后端

```bash
python run_backend.py
# 默认监听 http://127.0.0.1:8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
# 默认访问 http://localhost:5173
```

### 5. 端到端联跑（命令行）

```bash
# 摄取论文
python scripts/run_ingest.py <paper_id>

# 完整联跑（需 MATLAB 已启动并连接 MCP）
python scripts/run_full.py <paper_id>

# 查看任务进度
python scripts/watch_task.py <task_id>
```

## 配置说明

所有配置文件位于 `configs/`，敏感信息通过环境变量注入，参见 `.env.example`。

| 文件 | 说明 |
|------|------|
| `model.yaml` | LLM 参数（温度、超时、重试次数） |
| `mineru.yaml` | 论文解析后端配置 |
| `graph.yaml` | LangGraph checkpointer 类型（memory / sqlite） |
| `matlab.yaml` | MATLAB MCP 连接配置 |
| `knowledge.yaml` | 知识抽取参数 |

## 测试

```bash
pytest
```

## 依赖 MATLAB

代码执行节点依赖本地 MATLAB 实例通过 MCP 协议暴露工具。需在 MATLAB 中启动 MCP server 后再运行工作流，具体配置参见 `configs/matlab.yaml`。
