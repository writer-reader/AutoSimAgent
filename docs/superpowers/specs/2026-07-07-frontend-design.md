# Frontend Design Spec — control-agent
**日期：** 2026-07-07  
**状态：** 待实现  
**作者：** brainstorming session

---

## 1. 背景与目标

为 control-agent 后端（FastAPI + SSE + LangGraph 八阶段流水线）设计一个对外演示用前端。  
核心场景：演示完整操作流程——上传论文 → 实时追踪流水线 → 审批 MATLAB 代码 → 查看验收结果。

**约束：**
- 后端运行在 `127.0.0.1:8000`，前端开发时通过 Vite proxy 转发
- 单任务专注视图，不需要多用户、不需要路由
- 视觉风格：简洁专业、白色调，SaaS 感

---

## 2. 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 框架 | React 18 + TypeScript | 生态成熟，组件复用好 |
| 构建 | Vite | 轻量，HMR 快 |
| 样式 | Tailwind CSS | 白色调 SaaS 风，无主题绑架 |
| 组件库 | shadcn/ui（基于 Radix） | 无主题绑架，可组合 |
| 状态管理 | Zustand | 单任务场景足够，比 Redux 轻 |
| 代码编辑器 | Monaco Editor | Step 2 审批 + Step 3 只读复用 |

不引入 TanStack Query——单任务专注视图下状态足够简单，Zustand + 原生 fetch 即可。

---

## 3. 整体架构

### 3.1 页面结构

单页应用，无路由，状态驱动三步向导：

```
Header（步骤指示器：●──○──○）
└── 内容区（全屏，step: 1 | 2 | 3）
    ├── Step 1：论文导入
    ├── Step 2：实时流水线面板（含审批弹层）
    └── Step 3：最终结果页
```

步骤**单向自动推进**：
- Step 1 → 2：`POST /papers/import` + `POST /workflow/start` 均成功后自动跳转
- Step 2 → 3：SSE `done` 事件且 `status === "completed"` 时跳转；`status === "failed"` 停在 Step 2 错误态

步骤条**不感知**审批子态，审批以模态层在 Step 2 内部处理。

### 3.2 Zustand Store 结构

```typescript
interface AppStore {
  // 步骤控制
  step: 1 | 2 | 3

  // 导入阶段
  paperId: string | null
  pdfPath: string | null
  importError: string | null

  // 任务阶段
  taskId: string | null          // 同时写入 sessionStorage
  taskStatus: string | null
  currentStage: string | null
  currentStageLabel: string | null

  // SSE 日志
  eventLog: LogEntry[]           // 最近 200 条
  knownStages: string[]          // 动态构建，保留参考排序

  // 审批弹层
  approvalPayload: InterruptPayload | null
  approvalCount: number          // 第 N 次审批计数
  currentInterruptKey: string | null  // 透传给 /resume，不展示

  // 结果页
  finalResult: TaskResult | null
  criteria: CriteriaItem[]       // 来自 knowledge_done 事件

  // Actions（略）
}
```

### 3.3 刷新恢复

`taskId` 同时存入 `sessionStorage`。页面 mount 时执行以下恢复流程：

```
读 sessionStorage.taskId
  │
  ├─ 无 taskId → 停在 Step 1
  │
  └─ 有 taskId → GET /tasks/{taskId}
        ├─ 404（任务已过期） → 清空 sessionStorage，停在 Step 1
        ├─ status === "completed" → 加载 result 写入 store，跳 Step 3
        ├─ status === "failed"    → 跳 Step 2 错误态，显示错误信息
        ├─ status === "awaiting_approval" → 跳 Step 2，审批弹层等 interrupt payload
        └─ status === "running" / "created" → 跳 Step 2，重连 SSE
```

> 关键：`completed` / `failed` 任务不能依赖 SSE 重连（流已关闭，`done` 不会再推），**必须先查 `GET /tasks`，从轮询结果恢复状态**，而非重连 SSE 等事件。

---

## 4. Step 1 — 论文导入

### 布局

```
┌──────────────────────────────┐
│  拖拽区（视觉，不能替代路径）  │
│  ┌────────────────────────┐  │
│  │ 📄 拖拽 PDF 到此处      │  │
│  │ 文件名将自动填入下方      │  │
│  └────────────────────────┘  │
│                              │
│  本地路径 ___________________│
│  （请输入文件完整路径）        │
│                              │
│  [可选 metadata key-value]   │
│                              │
│      [开始导入并运行]          │
└──────────────────────────────┘
```

**拖拽行为：** 浏览器沙箱只能拿到 `File` 对象，无法获取真实路径。拖入时仅读取文件名填入输入框作为提示，用户需手动确认/补全完整路径，旁边加说明文字。

### 调用流程

```
点击「开始导入并运行」
  │
  ├─→ POST /papers/import { local_path, metadata }
  │     ├─ 成功 → 存 paperId，继续
  │     └─ 失败 → 显示内联错误，停止
  │
  └─→ POST /workflow/start { paper_id, pdf_path, user_id: "local" /* demo 临时值，多用户场景需改为实际标识 */ }
        ├─ 成功 → 存 taskId（Zustand + sessionStorage），进 Step 2
        └─ 失败 → 显示内联错误 + 「重新启动」按钮（用已有 paperId 重调 start）
```

**「重新启动」语义：** 直接使用已有 `paperId` 重调 `POST /workflow/start`，跳过重新导入，避免重复写入。

---

## 5. Step 2 — 实时流水线面板

### 布局

```
┌──────────────────────────────────────┐
│  阶段进度条（动态构建，水平节点列表）   │
│  ○─●─○─○─○─○─⚠️─○                  │
├──────────────────────────────────────┤
│                                      │
│  SSE 事件日志（滚动区，自动到底）       │
│  [10:01] stage: PDF 解析中（MinerU）  │
│  [10:02] knowledge_done: 3 criteria  │
│  [10:03] ⚠️ 等待人工审批：MATLAB 代码 │
│  ...                                 │
├──────────────────────────────────────┤
│  状态栏：● 运行中 / ⚠️ 等待审批 /     │
│          ✅ 完成 / ❌ 失败             │
└──────────────────────────────────────┘

[审批弹层（模态，interrupt 触发）]
```

### 阶段进度条

- **动态构建**：维护一份参考排序表（`mineru → adapter → knowledge → graph:init → graph:plan → request_approval → done`），仅用于排序；实际节点列表从 SSE `stage` 事件追加
- 收到未知 `stage` → 追加到末尾，进度条不断
- `request_approval` 阶段渲染橙色脉冲动画

### SSE 日志

过滤 `heartbeat` / `resume`，其余事件按视觉层级分两档渲染：

| 事件类型 | 渲染 | 视觉层级 |
|---|---|---|
| `stage` | 普通行，灰色时间戳 | 主层级 |
| `knowledge_done` | 蓝色，"知识抽取完成，{n} 条验收标准" | 主层级 |
| `interrupt` | **橙色加粗**，"⚠️ 等待人工审批：{tool}" | 主层级 |
| `error` | 红色，显示 error 字段 | 主层级 |
| `node` | 小字（text-xs）灰色缩进，"↳ {stage}: {detail}" | 次层级（细粒度进度） |
| `_dropped: true` | 黄色警告，"⚠️ 部分事件已丢失" | 主层级 |

最近 200 条，自动滚动到底。

### 连接中断兜底

连续 4 次心跳缺失（>60s 无响应）→ 日志区顶部显示内联警告"连接已中断，正在重连…"，不阻断界面，`EventSource` 自动重连。

### 状态栏按钮

| 状态 | 按钮 | 调用接口 |
|---|---|---|
| 运行中 | — | — |
| 等待审批 | 见审批弹层 | `POST /resume` |
| 流水线失败 | 重新运行 | `POST /workflow/start`（清空 taskId） |
| 完成 | 查看结果（自动跳 Step 3）| — |

---

## 6. 审批弹层

### 触发与关闭

- SSE `interrupt` 事件 → 弹层出现，背景变暗
- 不可点击背景关闭，必须明确决策（批准 / 拒绝）
- 决策后调 `POST /resume` → 弹层关闭，Step 2 恢复运行

### Payload 结构（前后端约定）

```typescript
interface InterruptPayload {
  tool: string          // 显示在标题，如 "run_code"
  language: string      // Monaco 语言模式，如 "matlab"
  code: string          // 编辑器初始内容
  interrupt_key: string // 后端识别本次审批的唯一 key（不展示）
}
```

### 布局

```
┌────────────────────────────────────┐
│  ⚠️ 请审核：{tool}                 │
│  第 {N} 次审批                     │
├────────────────────────────────────┤
│  [Monaco Editor，高度 400px，       │
│   语言 = payload.language，         │
│   可编辑，右上角「重置」按钮]        │
├────────────────────────────────────┤
│  [拒绝重规划]      [批准执行]        │
│  (destructive)     (primary)        │
└────────────────────────────────────┘
```

### 连续 interrupt 处理

- 新 `interrupt` 到来时**直接替换**弹层内容（不排队）
- `approvalCount` 自增，显示"第 N 次审批"
- `currentInterruptKey` 更新为最新 key

### resume 接口调用

```typescript
POST /workflow/{taskId}/resume
params: {
  approved: boolean,
  edited_code?: string,     // 用户修改的代码
  interrupt_key: string     // 从 store.currentInterruptKey 读取，不展示
}
```

> ⚠️ **后端待改动**：当前 `/resume` 接口无 `interrupt_key` 参数，需补充。

---

## 7. Step 3 — 最终结果页

### 布局

```
┌────────────────────────────────────┐
│  ✅ 流水线完成 / ❌ 流水线失败       │
│  verdict / 耗时                     │
├────────────────────────────────────┤
│  验收标准结果（主要内容）             │
│  ✅ 控制器增益满足要求               │
│  ❌ 超调量超出范围                   │
│  ...                               │
├────────────────────────────────────┤
│  生成代码（Monaco 只读）             │
│  [下载]  [在 MATLAB 中打开]         │
├────────────────────────────────────┤
│  过程详情（可折叠）                  │
│  calib_rounds / tool_calls         │
├────────────────────────────────────┤
│  [重新运行另一篇]                   │
└────────────────────────────────────┘
```

### criteria 与 verification 映射约定

`knowledge_done` 事件存入 Zustand 的 `criteria` 数组和 `done.result.verification` 里的通过状态**按 `criteria_id` 字段对应**，不按 index（index 不稳定）：

```typescript
// knowledge_done 存入 store 的格式
interface CriteriaItem {
  criteria_id: string   // 唯一标识，与 verification 对应
  description: string   // 展示给用户的验收描述
}

// done.result.verification 格式
interface VerificationResult {
  criteria_results: {
    criteria_id: string
    passed: boolean
    detail?: string
  }[]
}
```

Step 3 渲染时以 `criteria_id` join 两个数组，无匹配项显示"未验证"。

> ⚠️ **后端待改动**：`knowledge_done` 事件的 criteria 数组需包含 `criteria_id` 字段；`verification_result` 需包含 `criteria_results` 数组，每项带 `criteria_id` 和 `passed`。

### 数据来源

| 字段 | 来源 |
|---|---|
| `verdict` | SSE `done` 事件 `result.verdict` |
| criteria 列表 | Zustand `criteria`（从 `knowledge_done` 事件存入） |
| criteria 通过状态 | `done` 事件 `result.verification` |
| 代码内容 | `GET /workflow/{taskId}/code/{filename}` |
| `calib_rounds` / `tool_calls` | `done` 事件 `result` |

> ⚠️ **后端待改动**：需新增 `GET /workflow/{taskId}/code/{filename}` 接口返回代码内容，供 Monaco 只读渲染和下载使用。

### 失败态

失败路由规则：
- SSE 收到 `done` 事件且 `status === "failed"` → 进入 Step 3，标题改为 `❌ 流水线失败`，显示 `result.error`，按钮「重新运行」清空 `taskId` 回 Step 1
- SSE 收到 `error` 事件（无 `done`，如进程崩溃） → 停在 Step 2 错误态，显示错误信息，同样提供「重新运行」按钮

---

## 8. 共享组件：CodePanel

> Monaco Editor 主包 2MB+，**必须通过 `@monaco-editor/react` 的 `<Editor>` 组件按需加载**（内置 dynamic import，首屏不加载）。`CodePanel` 内部直接使用该组件，外部无需关心加载时机。

统一封装 Monaco Editor，在两处复用：

```typescript
interface CodePanelProps {
  language: string
  value: string
  readOnly?: boolean
  onChange?: (v: string) => void
  onReset?: () => void      // 仅 editable 模式
  onDownload?: () => void   // 仅 readOnly 模式
  onOpenMatlab?: () => void // 仅 readOnly 模式（调用系统 open 命令打开文件，需后端提供文件路径；演示阶段可降级为不展示此按钮）
  height?: string           // 默认 400px
}
```

---

## 9. SSE 集成

### Vite proxy 配置（关键）

Vite 的 HTTP proxy 默认缓冲响应体，会导致 SSE 流被攒满后一次性吐出，等于废了实时性。必须在 proxy 配置中关闭缓冲：

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      rewrite: (path) => path.replace(/^\/api/, ''),
      configure: (proxy) => {
        proxy.on('proxyRes', (proxyRes) => {
          // SSE 响应禁止缓冲：让数据块立即透传
          if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
            proxyRes.headers['x-accel-buffering'] = 'no'
          }
        })
      }
    }
  }
}

```typescript
// hooks/useWorkflowStream.ts

useEffect(() => {
  if (!taskId) return
  const es = new EventSource(`/api/workflow/${taskId}/stream`)

  es.onmessage = (e) => {
    const event = JSON.parse(e.data)
    // 更新日志、阶段、审批状态
    // interrupt → setApprovalPayload
    // knowledge_done → setCriteria
    // done/error → es.close()
  }

  es.onerror = () => { /* 显示重连提示，EventSource 自动重连 */ }

  return () => es.close()
}, [taskId])
```

`EventSource` 利用浏览器原生自动重连，**无需手动重连逻辑**。`done` / `error` 后主动 `es.close()` 阻止无意义重连。

---

## 10. 错误处理约定

后端统一错误格式：`{ code: string, message: string, retryable: boolean }`

| `retryable` | 前端处理 |
|---|---|
| `true` | 显示错误信息 + "重试"按钮 |
| `false` | 显示错误信息，无重试，提供"重新运行"入口 |

---

## 11. 需要后端配合的改动

| 改动 | 说明 | 优先级 |
|---|---|---|
| `/resume` 加 `interrupt_key` 参数 | 多轮审批时后端需识别当前审批 | 高 |
| 新增 `GET /workflow/{id}/code/{filename}` | Step 3 代码内容预览与下载 | 高 |
| `interrupt` payload 标准化 | 统一包含 `tool / language / code / interrupt_key` | 高 |
| `knowledge_done` criteria 数组加 `criteria_id` | 前端按 id join，不按 index | 高 |
| `done.result.verification` 加 `criteria_results` | 每项含 `criteria_id + passed`，供 Step 3 验收表渲染 | 高 |

---

## 12. 目录结构（建议）

```
frontend/
├── src/
│   ├── api/
│   │   └── client.ts           # axios + Vite proxy /api
│   ├── hooks/
│   │   └── useWorkflowStream.ts
│   ├── store/
│   │   └── app.ts              # Zustand store
│   ├── components/
│   │   ├── CodePanel.tsx       # 共享 Monaco 组件
│   │   ├── StageProgress.tsx   # 动态阶段进度条
│   │   ├── EventLog.tsx        # SSE 事件日志
│   │   └── ApprovalDialog.tsx  # 审批弹层
│   ├── steps/
│   │   ├── Step1Import.tsx
│   │   ├── Step2Pipeline.tsx
│   │   └── Step3Result.tsx
│   └── App.tsx                 # 步骤指示器 + 内容区切换
├── vite.config.ts
└── package.json
```
