---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 0e20042592d71a85ccdd0527c3b6c51c_01aaffeb6e0911f1a99c5254007bceed
    ReservedCode1: 3RanXhG0sbkqgV5uOFrKwHFZGwuF5p3vzrMhBkurqU+NE/0QEO+Hwhmv0mNTdy5UwWubLYrsrhzw1W7cxSp3iwZuW8F/e2/J17PbxH56M+Evj0+5h56qhcw29YPmMK789Murd8pmI29JtceZN2MDreyYqYmqpIXk1cxOtL1CmlnlNAzovuclu8fYBXA=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 0e20042592d71a85ccdd0527c3b6c51c_01aaffeb6e0911f1a99c5254007bceed
    ReservedCode2: 3RanXhG0sbkqgV5uOFrKwHFZGwuF5p3vzrMhBkurqU+NE/0QEO+Hwhmv0mNTdy5UwWubLYrsrhzw1W7cxSp3iwZuW8F/e2/J17PbxH56M+Evj0+5h56qhcw29YPmMK789Murd8pmI29JtceZN2MDreyYqYmqpIXk1cxOtL1CmlnlNAzovuclu8fYBXA=
---


# control-agent 全流程流水线详解

> 一条控制领域论文从上传到最终产出验证代码的完整数据链路。

---

## 总览：八阶段流水线

```
用户上传 PDF
    │
    ▼
[1] 论文导入        downloader.py / PaperService.import_paper()
    │  paper_id, pdf_path, file_hash
    ▼
[2] MinerU 解析     mineru_client.py / PaperService.parse_paper()
    │  MineruResult + ParsedPaper
    ├──────────────────────┬──────────────────────┐
    ▼                      ▼                      ▼
[3] 切块 & 索引        [4] 知识抽取              [5] RAG 检索
    chunker.py             equation_extractor      retriever.py
    index_builder.py       controller_extractor    vectorstore.py
    embedder.py            parameter_extractor
    │  Chunk[]             postprocessor.py
    │                      │  MergedKnowledge
    │                      │
    ▼                      ▼
    └──────────┬───────────┘
               ▼
[6] LLM 分析 & 规划    graph/workflow.py / LangGraph 工作流
    │  WorkflowState 驱动
    ├─ planner（理解论文+知识+检索结果→生成代码方案）
    ▼
[7] 工具调用层
    ├─ MATLAB 路径      matlab_service.py → matlab_mcp.py
    ├─ Simulink 路径    simulink_service.py → simulink_toolkit.py
    │
    ├── 高风险工具？─→ [审批] request_human_approval()
    │       │                │  approved / rejected
    │       ▼                ▼
    └── 执行工具 ──→ ToolResult ──→ 报错？──→ [8] 错误处理
                                        │           route_after_error()
                                        │           ├─ 可重试 → retry
                                        │           ├─ 需重规划 → 回 LLM
                                        │           └─ 致命 → 终止
                                        ▼
                                   [验证] CodeVerifierService
                                        │  promote_if_verified()
                                        ▼
                                   最终产出物（已验证代码/模型）
```

---

## 阶段一：论文导入

**入口**：`POST /papers/import`

### 调用链

```
HTTP Request                    路由层                       业务层                      底层实现
───────────                    ──────                      ──────                      ────────

PaperImportRequest  ──→  routers/papers.py         PaperService             ingestion/downloader.py
{                         import_paper()  ──→        .import_paper() ──→      import_local_pdf()
  local_path,              │                         │                        │
  metadata                 │                         │                        ├─ 校验文件存在
}                          │                         │                        ├─ 校验 .pdf 后缀
                           │                         │                        ├─ 校验大小 ≤100MB
                           │                         │                        ├─ sha256_file() 指纹
                           │                         │                        ├─ paper_id = paper_{hash前12位}
                           │                         │                        ├─ 复制到 data/papers/
                           │                         │                        └─ 返回 DownloadResult
                           │                         │
                           ▼                         ▼
                    PaperImportResponse       DownloadResult
                    {paper_id, pdf_path,      {paper_id, pdf_path,
                     file_hash}                file_hash, metadata}
```

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/api/routers/papers.py` | `import_paper()` | 路由处理器，接收 HTTP 请求 |
| `app/api/schemas.py` | `PaperImportRequest` | 校验请求体（Pydantic） |
| `app/api/schemas.py` | `PaperImportResponse` | 定义返回格式 |
| `app/api/dependencies.py` | `get_paper_service()` | 依赖注入，构造 PaperService |
| `app/services/paper_service.py` | `PaperService.import_paper()` | 业务编排，调底层导入 |
| `app/ingestion/downloader.py` | `PaperSource` | 入参数据类（本地路径+元数据） |
| `app/ingestion/downloader.py` | `DownloadResult` | 出参数据类（paper_id+路径+哈希） |
| `app/ingestion/downloader.py` | `sha256_file()` | SHA256 分块哈希计算 |
| `app/ingestion/downloader.py` | `import_local_pdf()` | 核心逻辑：校验→哈希→复制归档 |

### 异常路径

| 校验项 | 失败抛出的异常 | HTTP 状态码 |
|--------|---------------|-------------|
| 文件不存在 | `DownloadError("paper_missing")` | 400 |
| 不是 PDF | `DownloadError("paper_not_pdf")` | 400 |
| 超过 100MB | `DownloadError("paper_too_large")` | 400 |

异常被 `main.py` 中的 `control_agent_error_handler` 捕获，转为 `{"code": "...", "message": "...", "retryable": false}` 返回。

---

## 阶段二：MinerU PDF 解析

### 调用链

```
PaperService.parse_paper(paper_id, pdf_path)
    │
    ├─→ MineruClient.parse_pdf(paper_id, pdf_path)
    │       │
    │       ├─ 校验 PDF 源存在
    │       ├─ 创建 data/mineru/markdown/、json/、images/ 目录
    │       ├─ 写占位 markdown（当前为空壳）
    │       ├─ 写占位 JSON（空论文结构）          ← ⚠️ 占位实现
    │       └─ 返回 MineruResult
    │
    └─→ parse_mineru_json(mineru_result.json_path)
            │
            ├─ 读取 JSON 文件
            ├─ json.loads()
            ├─ ParsedPaper.model_validate(data)
            └─ 返回 ParsedPaper
```

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/services/paper_service.py` | `PaperService.parse_paper()` | 业务编排 |
| `app/ingestion/mineru_client.py` | `MineruClient` | MinerU 客户端（占位） |
| `app/ingestion/mineru_client.py` | `MineruClient.parse_pdf()` | 调 MinerU 解析（⚠️ 占位） |
| `app/ingestion/mineru_client.py` | `MineruResult` | 解析结果数据类 |
| `app/ingestion/parser.py` | `ParsedPaper` | 结构化论文模型 |
| `app/ingestion/parser.py` | `PaperSection` | 论文章节模型 |
| `app/ingestion/parser.py` | `PaperBlock` | 论文块（段落/公式/表格/图片） |
| `app/ingestion/parser.py` | `parse_mineru_json()` | JSON → ParsedPaper 转换 |

### 数据结构（ParsedPaper）

```
ParsedPaper
├── paper_id: str
├── title: str
├── sections: list[PaperSection]
│   ├── section_id, heading, level, page_range
│   └── blocks: list[PaperBlock]
│       ├── block_id
│       ├── type: "paragraph" | "equation" | "table" | "image"
│       ├── text: str
│       ├── latex: str | None          ← 公式 LaTeX
│       ├── table_cells: list | None    ← 表格数据
│       └── evidence_ref: str | None    ← 证据追溯引用
└── references: list[str]
```

> ⚠️ **当前状态**：MineruClient 为占位实现，`parse_pdf()` 不调真实 MinerU API，只写空 JSON。后续需替换为真实 HTTP 调用。

---

## 阶段三：RAG 索引构建

将 ParsedPaper 切块 → 嵌入 → 写入向量库，为后续 LLM 检索提供上下文。

### 调用链

```
RagService.build_index(paper: ParsedPaper)
    │
    └─→ IndexBuilder.build(paper)
            │
            ├─→ chunk_paper(paper, chunk_size=1200)
            │       遍历每个 section.block
            │       公式块取 latex，文本块取 text
            │       每个 block 生成一个 Chunk
            │       └─ 返回 Chunk[]
            │
            ├─→ vectorstore.delete_by_paper(paper_id)  ← 清空旧索引
            └─→ vectorstore.upsert(chunks)              ← 写入新 chunk
```

检索：

```
RagService.retrieve(query, paper_id, top_k=8)
    │
    └─→ Retriever.retrieve()
            └─→ InMemoryVectorStore.search()
                    关键词匹配（⚠️ 占位，非真实向量检索）
                    返回 SearchResult[]（Chunk + score）
```

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/rag/chunker.py` | `chunk_paper()` | 论文切块，保护公式结构 |
| `app/rag/schemas.py` | `Chunk` | 切块数据模型 |
| `app/rag/schemas.py` | `SearchResult` | 检索结果模型 |
| `app/rag/embedder.py` | `HashEmbedder.embed()` | 占位嵌入（SHA256 哈希模拟） |
| `app/rag/index_builder.py` | `IndexBuilder.build()` | 编排切块+写索引 |
| `app/rag/retriever.py` | `Retriever.retrieve()` | 检索入口 |
| `app/rag/vectorstore.py` | `InMemoryVectorStore` | 内存向量库（占位） |
| `app/services/rag_service.py` | `RagService` | 业务层封装 |

> ⚠️ **当前状态**：Embedder 用 SHA256 哈希模拟（非语义嵌入），VectorStore 用关键词匹配（非向量相似度），均为占位实现。

---

## 阶段四：知识抽取

从 ParsedPaper 中抽取三类结构化知识：公式、控制器、参数。

### 调用链

```
KnowledgeService.build(paper: ParsedPaper)
    │
    ├─→ EquationExtractor.extract(paper)
    │       遍历所有 section.block
    │       筛选 type=="equation" 且有 latex 的块
    │       生成 Equation 对象（equation_id, latex, normalized_latex, category...）
    │       confidence = 0.7
    │
    ├─→ ControllerExtractor.extract(paper)
    │       遍历所有 section 文本
    │       关键词匹配 "controller"/"control law"/"控制"
    │       生成 Controller 对象（type, architecture, input_signals...）
    │       confidence = 0.6
    │
    ├─→ ParameterExtractor.extract(paper)
    │       正则: \b([A-Za-z][A-Za-z0-9_]*)\s*=\s*([-+]?\d+(?:\.\d+)?)\b
    │       匹配 "Kp = 1.5" 类文本
    │       生成 Parameter 对象（symbol, value, unit, belongs_to...）
    │       confidence = 0.65
    │
    ├─→ merge_knowledge(paper_id, equations, controllers, parameters, confidence_threshold=0.75)
    │       合并三类知识 → MergedKnowledge
    │       标记 confidence < 0.75 的项为 needs_review
    │
    └─→ save_merged_knowledge(merged)
            写入 data/knowledge/merged/{paper_id}.json
            返回文件路径
```

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/knowledge/base_extractor.py` | `BaseExtractor` | 抽取器抽象基类（ABC） |
| `app/knowledge/equation_extractor.py` | `EquationExtractor.extract()` | 公式抽取 |
| `app/knowledge/controller_extractor.py` | `ControllerExtractor.extract()` | 控制器抽取（关键词） |
| `app/knowledge/parameter_extractor.py` | `ParameterExtractor.extract()` | 参数抽取（正则） |
| `app/knowledge/schemas.py` | `Equation` | 公式数据模型（含 EvidenceMixin） |
| `app/knowledge/schemas.py` | `Controller` | 控制器数据模型 |
| `app/knowledge/schemas.py` | `Parameter` | 参数数据模型 |
| `app/knowledge/schemas.py` | `EvidenceMixin` | 证据追溯混入（evidence_ref + confidence） |
| `app/knowledge/schemas.py` | `MergedKnowledge` | 合并知识模型 |
| `app/knowledge/postprocessor.py` | `merge_knowledge()` | 合并+低置信度标记 |
| `app/knowledge/postprocessor.py` | `save_merged_knowledge()` | 持久化 |
| `app/services/knowledge_service.py` | `KnowledgeService.build()` | 业务编排层 |
| `app/services/knowledge_service.py` | `KnowledgeBuildResult` | 构建结果统计 |

### 知识证据链

每个知识项都带 `evidence_ref`，可追溯到论文原文位置：

```
Equation { evidence_ref: "section_2.block_3" }
    └─→ ParsedPaper.sections[2].blocks[3]  ← 原文出处
```

---

## 阶段五：LLM 分析 & 规划（LangGraph 工作流）

工作流引擎基于 LangGraph 架构，以 `WorkflowState` 作为全流程共享状态，在各节点间流转。

### WorkflowState 状态结构

```
WorkflowState（Pydantic BaseModel）
├── trace_id: str              ← 全链路追踪 ID
├── task_id: str               ← 任务 ID
├── paper_id: str              ← 目标论文
├── user_id: str               ← 用户标识
├── ingestion_result: dict     ← 导入结果（阶段一产出）
├── knowledge_refs: list[str]  ← 知识文件路径（阶段四产出）
├── retrieved_chunks: list     ← RAG 检索结果（阶段三产出）
├── plan: dict                 ← LLM 生成的执行计划
├── generated_code_paths: list ← MATLAB 代码路径
├── generated_model_paths: list← Simulink 模型路径
├── approval_request: dict     ← 审批请求（高风险工具）
├── tool_results: list         ← 工具执行结果列表
├── simulation_metrics: dict   ← 仿真指标
├── verification_result: dict  ← 验证结果
├── errors: list               ← 错误记录（含 retryable 标记）
└── retry_count: int           ← 当前重试次数
```

### 工作流节点

| 节点 | 文件 | 函数/类 | 职责 |
|------|------|---------|------|
| 初始化 | `graph/workflow.py` | `ControlWorkflow.run_minimal()` | 保存初始状态 → 执行 → 保存最终状态 |
| 终态 | `graph/nodes.py` | `finalize()` | 标记 verification_result.status = "completed" |
| 审批 | `graph/nodes.py` | `request_human_approval()` | 生成审批请求写入 state.approval_request |
| 路由 | `graph/router.py` | `route_tool_call()` | 判断工具是否需审批（查 HIGH_RISK_TOOLS 集合） |
| 错误路由 | `graph/router.py` | `route_after_error()` | 根据错误类型决定重试/重规划/终止 |
| 审批路由 | `graph/router.py` | `route_after_approval()` | 审批通过→继续执行，拒绝→重规划或停止 |
| 持久化 | `graph/checkpoint.py` | `FileCheckpointer` | 任务状态 JSON 文件存/读 |

### 高风险工具审批机制

`router.py` 中定义了高风险工具名单：

```python
HIGH_RISK_TOOLS = {
    "run_code", "run_script",           # MATLAB 代码/脚本执行
    "add_block", "connect_blocks",      # Simulink 模型修改
    "set_block_parameters",             # Simulink 参数修改
    "run_simulation", "export_model"    # Simulink 仿真/导出
}
```

当 LLM 计划调用这些工具时：
1. `route_tool_call(tool_name)` → 返回 `"request_human_approval"`
2. 暂停执行，生成审批请求
3. 用户 approve → 继续执行工具
4. 用户 reject → 回 LLM 重新规划

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/graph/state.py` | `WorkflowState` | 工作流全量状态（Pydantic） |
| `app/graph/workflow.py` | `ControlWorkflow` | 工作流封装 |
| `app/graph/nodes.py` | `finalize()` | 终止节点 |
| `app/graph/nodes.py` | `request_human_approval()` | 审批请求生成 |
| `app/graph/router.py` | `route_tool_call()` | 工具路由决策 |
| `app/graph/router.py` | `route_after_error()` | 错误恢复路由 |
| `app/graph/router.py` | `route_after_approval()` | 审批后路由 |
| `app/graph/checkpoint.py` | `FileCheckpointer` | 状态持久化 |

---

## 阶段六：工具调用 —— MATLAB 路径

### 调用链

```
MatlabService.execute_code(code: str)
    │
    └─→ MatlabMcpClient.run_code(code)
            └─→ McpClientBase.call_tool("run_code", {"code": code})
                    └─ 返回 ToolResult
            └─ 返回 MatlabRunResult {ok, stdout, stderr, artifacts}

MatlabService 后处理:
    ├─ 检测 "NaN" / "Inf" → warnings.append("output_contains_nan_or_inf")
    └─ 返回 MatlabValidationResult {ok, run_result, warnings}
```

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/services/matlab_service.py` | `MatlabService.execute_code()` | 执行代码 + 基础校验 |
| `app/services/matlab_service.py` | `MatlabValidationResult` | 校验结果 |
| `app/tools/matlab_mcp.py` | `MatlabMcpClient` | MATLAB MCP 封装 |
| `app/tools/matlab_mcp.py` | `MatlabMcpClient.run_code()` | 执行 MATLAB 代码 |
| `app/tools/matlab_mcp.py` | `MatlabMcpClient.run_script()` | 执行 MATLAB 脚本 |
| `app/tools/matlab_mcp.py` | `MatlabMcpClient.check_code()` | 代码静态检查 |
| `app/tools/matlab_mcp.py` | `MatlabMcpClient.list_toolboxes()` | 查询可用工具箱 |
| `app/tools/matlab_mcp.py` | `MatlabRunResult` | 运行结果 |
| `app/tools/mcp_client_base.py` | `McpClientBase` | MCP 协议基类（占位） |
| `app/tools/mcp_client_base.py` | `ToolResult` | 工具调用统一结果 |
| `app/tools/mcp_client_base.py` | `ToolSpec` | 工具规格描述 |

---

## 阶段七：工具调用 —— Simulink 路径

### 调用链

```
SimulinkService.build_from_script(model_name, script_path)
    └─→ SimulinkToolkitClient.open_model(script_path)  → ToolResult

SimulinkService.run_simulation(model_name, timeout_s=600)
    └─→ SimulinkToolkitClient.run_simulation(model_name, {timeout_s})  → ToolResult
```

Simulink 工具集（5 个高风险需审批）：

```
SimulinkToolkitClient
├── open_model()           ← 打开模型
├── read_model_structure() ← 读取模型结构
├── add_block()            ← 🔴 需审批
├── connect_blocks()       ← 🔴 需审批
├── set_block_parameters() ← 🔴 需审批
├── run_simulation()       ← 🔴 需审批
└── export_model()         ← 🔴 需审批
```

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/services/simulink_service.py` | `SimulinkService` | Simulink 业务编排 |
| `app/services/simulink_service.py` | `SimulinkService.build_from_script()` | 从脚本构建模型 |
| `app/services/simulink_service.py` | `SimulinkService.run_simulation()` | 运行仿真 |
| `app/tools/simulink_toolkit.py` | `SimulinkToolkitClient` | Simulink 工具集封装 |

---

## 阶段八：错误处理 & 反馈循环

### 异常体系（11 种）

```
ControlAgentError（基类）
├── ConfigError
├── IngestionError
│   ├── DownloadError        ← 论文导入失败
│   └── ParseError           ← MinerU JSON 解析失败
├── ExtractionError          ← 知识抽取失败
├── RagError                 ← RAG 索引/检索失败
├── WorkflowError            ← 工作流执行失败
├── ApprovalError            ← 审批超时/拒绝
├── ToolExecutionError
│   ├── MatlabExecutionError ← MATLAB 运行错误
│   └── SimulinkExecutionError ← Simulink 错误
└── VerificationError        ← 代码验证失败
```

每个异常都带：
- `code`：机器可读错误码
- `message`：用户可读描述
- `details`：内部调试详情（`to_public_dict()` 对外隐藏）
- `retryable`：是否可重试

### 错误恢复决策

```
route_after_error(state, max_retries=2)
    │
    ├─ 无错误记录？
    │   └─→ "continue"（继续正常流程）
    │
    ├─ 最新错误 retryable=true 且 retry_count < 2？
    │   └─→ "retry_node"（重试当前节点，retry_count++）
    │
    ├─ 最新错误 needs_replan=true？
    │   └─→ "plan_solution"（回 LLM 重新规划）
    │
    └─ 其他（不可重试 / 已耗尽重试次数）
        └─→ "finalize_failed"（终止，标记失败状态）
```

### 验证晋级

```
CodeVerifierService.promote_if_verified(generated_path, verified_dir="data/code/verified")
    │
    ├─ 校验文件存在
    ├─ 创建 verified 目录
    ├─ shutil.copy2() 复制到 verified 目录
    └─ 返回 VerificationResult {ok, verified_path, reason}
```

### 涉及的关键类/方法

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `app/core/exceptions.py` | `ControlAgentError` | 统一异常基类 |
| `app/core/exceptions.py` | `*.to_public_dict()` | 安全对外暴露 |
| `app/graph/router.py` | `route_after_error()` | 错误后路由决策 |
| `app/services/code_verifier_service.py` | `CodeVerifierService` | 代码验证+晋级 |
| `app/services/code_verifier_service.py` | `VerificationResult` | 验证结果 |

---

## 配置驱动架构

8 个 YAML 配置文件通过 `config_loader.py` 加载为 Pydantic 模型：

```
configs/
├── core.yaml          → CoreConfig         (日志/任务队列)
├── mineru.yaml        → MineruConfig       (MinerU API)
├── knowledge.yaml     → KnowledgeConfig    (置信度阈值)
├── rag.yaml           → RagConfig          (切块/检索参数)
├── matlab.yaml        → MatlabConfig       (MCP 服务/审批)
├── simulink.yaml      → SimulinkConfig     (仿真/审批工具列表)
├── graph.yaml         → GraphConfig        (checkpoint/重试)
└── model.yaml         → ModelConfig        (LLM/嵌入模型)
                    ↓
              AppConfig（聚合根）
                    ↓
              各 Service 层读取
```

### 配置加载流程

```
load_config("configs")
    │
    └─ for name in CONFIG_MODELS:
           ├─ load_yaml(configs/{name}.yaml)  ← 读 YAML
           ├─ model.model_validate(data)      ← Pydantic 校验
           └─ 存入 values[name]
    │
    └─ AppConfig.model_validate(values)  ← 聚合校验
        任一文件缺失 / schema 不合法 → ConfigError 终止启动
```

---

## 数据流全景图

```
                         ┌────────────────────────────────────────────────────────┐
                         │                    configs/ (8 YAML)                     │
                         │  core | mineru | knowledge | rag | matlab | simulink    │
                         │              graph | model                               │
                         └────────────────────┬───────────────────────────────────┘
                                              │ load_config()
                                              ▼
┌─────────┐    POST /papers/import    ┌──────────────┐    parse_paper()    ┌──────────────┐
│  用户    │ ──────────────────────→  │  PaperService │ ─────────────────→  │ MineruClient  │
│         │                          │                │                    │  (占位)       │
│         │ ←── PaperImportResponse   │  import_paper │ ←── MineruResult   │              │
└─────────┘                          │  parse_paper  │                    └──────┬───────┘
                                     └───────┬──────┘                            │
                                             │                                   ▼
                                     ┌───────┴──────────────────────────┐  ┌──────────┐
                                     │                                  │  │  parser  │
                                     ▼                                  │  │  .py     │
                              ┌─────────────┐                          │  └────┬─────┘
                              │ RagService  │                          │       │
                              │             │                          │       ▼
                              │ build_index │                          │  ParsedPaper
                              │ retrieve    │                          │       │
                              └──────┬──────┘                          │       │
                                     │                                 │       │
                              Chunk[]│                                 │       │
                                     │                                 │       │
                                     ▼                                 ▼       │
                              ┌─────────────┐                   ┌─────────────┐│
                              │ VectorStore │                   │KnowledgeSvc  ││
                              │  (内存占位)  │                   │             ││
                              └──────┬──────┘                   │ build()     ││
                                     │                          └──────┬──────┘│
                                     │                                 │       │
                                     │    ┌────────────────────────────┘       │
                                     │    │                                    │
                                     ▼    ▼                                    │
                              ┌─────────────────┐                              │
                              │   LangGraph      │                              │
                              │   Workflow       │                              │
                              │                  │                              │
                              │  WorkflowState   │                              │
                              │  ┌──────────────┐│                              │
                              │  │ plan         ││ ← LLM 生成执行计划            │
                              │  │ tool_results ││                              │
                              │  │ errors       ││                              │
                              │  │ retry_count  ││                              │
                              │  └──────────────┘│                              │
                              └────────┬─────────┘                              │
                                       │                                        │
                          ┌────────────┼────────────┐                           │
                          ▼            ▼            ▼                           │
                   ┌──────────┐ ┌───────────┐ ┌───────────┐                    │
                   │ MATLAB   │ │ Simulink  │ │  审批      │                    │
                   │ MCP      │ │ Toolkit   │ │  机制      │                    │
                   └────┬─────┘ └─────┬─────┘ └─────┬─────┘                    │
                        │             │             │                            │
                        ▼             ▼             ▼                            │
                   ┌──────────────────────────────────────┐                      │
                   │           ToolResult / Error          │                      │
                   └────────────────┬─────────────────────┘                      │
                                    │                                            │
                           route_after_error()                                   │
                           ┌──────┼──────┐                                       │
                           ▼      ▼      ▼                                       │
                        retry  replan  finalize                                  │
                                    │                                            │
                                    ▼                                            │
                           ┌──────────────────┐                                  │
                           │ CodeVerifierSvc  │                                  │
                           │ promote_if_      │                                  │
                           │ verified()       │                                  │
                           └────────┬─────────┘                                  │
                                    │                                            │
                                    ▼                                            │
                           ┌──────────────────┐                                  │
                           │ data/code/       │                                  │
                           │ verified/        │  ← 最终产出物                     │
                           └──────────────────┘                                  │
```

---

## 关键设计决策说明

| 决策 | 说明 |
|------|------|
| **占位实现策略** | MineruClient、HashEmbedder、InMemoryVectorStore 均为可替换占位，真实实现只需满足相同接口 |
| **安全审批** | MATLAB 代码执行 + Simulink 5 种模型修改工具需人工审批，审批通过才继续 |
| **证据链** | 所有知识抽取项带 `evidence_ref`，可追溯到论文原文块 |
| **分层异常** | `to_public_dict()` 对外暴露安全信息，`details` 字段仅内部可见 |
| **配置校验** | 8 个 YAML 由 Pydantic 严格校验，启动时任一不合法即终止 |
| **任务可恢复** | `FileCheckpointer` 持久化 WorkflowState，支持中断后恢复 |
| **模块化错误恢复** | `route_after_error()` 根据 retryable/needs_replan 自动决策，最多重试 2 次 |
*（内容由AI生成，仅供参考）*
