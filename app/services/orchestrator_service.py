# 端到端编排：图外预处理（导入→MinerU→adapter→知识抽取）+ 图内 LangGraph 决策循环。
# 供 API 以 BackgroundTasks 异步驱动，任务状态经 checkpointer 持久化、可查询。
# 支持 SSE 实时事件流（GET /workflow/{task_id}/stream）和人工干预（POST /workflow/{task_id}/resume）。
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from uuid import uuid4

from app.core.config_loader import AppConfig
from app.graph.real_nodes import build_real_deps
from app.graph.state import WorkflowState
from app.graph.workflow import ControlWorkflow, build_checkpointer
from app.ingestion.adapter import mineru_output_to_paper, save_parsed_paper
from app.ingestion.mineru_client import MineruClient
from app.knowledge.llm_extractor import LlmKnowledgeExtractor
from app.knowledge.postprocessor import merge_knowledge, save_merged_knowledge
from app.llm.client import LLMClient
from app.tools.matlab_mcp import MatlabMcpClient
from app.tools.mcp_factory import get_matlab_client

# SSE 事件队列每个任务最多缓存多少条，超出旧事件被丢弃（防内存泄漏）。
_QUEUE_MAXSIZE = 256
# 任务最大保留时间（秒），超时后 get_queue 的消费者会收到 sentinel None 并断开。
_TASK_TTL = 7200


# TaskRegistry 类，进程内任务登记 + 每任务 SSE 事件队列 + ControlWorkflow 实例缓存。
class TaskRegistry:
    def __init__(self, queue_maxsize: int = _QUEUE_MAXSIZE, task_ttl: float = _TASK_TTL) -> None:
        self._tasks: dict[str, dict] = {}
        self._queues: dict[str, queue.Queue] = {}
        self._workflows: dict[str, ControlWorkflow] = {}
        self._lock = threading.Lock()
        self._queue_maxsize = queue_maxsize
        self._task_ttl = task_ttl

    # reconfigure 方法，由 OrchestratorService.__init__ 在加载配置后调用，覆盖默认值。
    def reconfigure(self, queue_maxsize: int, task_ttl: float) -> None:
        with self._lock:
            self._queue_maxsize = queue_maxsize
            self._task_ttl = task_ttl

    # create 方法，注册新任务，分配事件队列，记录创建时间。
    def create(self, paper_id: str, user_id: str) -> str:
        task_id = f"task_{uuid4().hex[:12]}"
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "paper_id": paper_id,
                "user_id": user_id,
                "status": "created",
                "stage": "pending",
                "error": None,
                "result": None,
                "created_at": time.time(),
            }
            self._queues[task_id] = queue.Queue(maxsize=self._queue_maxsize)
        return task_id

    # update 方法，更新任务元数据字段。
    def update(self, task_id: str, **kw) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(kw)

    # get 方法，返回任务元数据快照（懒清理：顺便清掉超时任务）。
    def get(self, task_id: str) -> dict | None:
        self._cleanup_expired()
        with self._lock:
            return dict(self._tasks[task_id]) if task_id in self._tasks else None

    # _cleanup_expired 方法，清理超过 TTL 的已终止任务（非阻塞懒清理）。
    def _cleanup_expired(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                tid for tid, meta in self._tasks.items()
                if meta.get("status") in ("completed", "failed")
                and now - meta.get("created_at", now) > self._task_ttl
            ]
            for tid in expired:
                self._tasks.pop(tid, None)
                self._queues.pop(tid, None)
                self._workflows.pop(tid, None)

    # push_event 方法，向任务事件队列写入一条事件。
    # 队列满时丢弃最旧事件，并在新事件中附加 _dropped=True 标记，告知消费者数据不连续。
    def push_event(self, task_id: str, event: dict) -> None:
        q = self._queues.get(task_id)
        if q is None:
            return
        event.setdefault("ts", time.time())
        try:
            q.put_nowait(event)
        except queue.Full:
            dropped = True
            try:
                q.get_nowait()
            except queue.Empty:
                dropped = False
            try:
                if dropped:
                    event = {**event, "_dropped": True}  # 告知消费者此前有事件被丢弃
                q.put_nowait(event)
            except queue.Full:
                pass

    # push_sentinel 方法，推终止哨兵（None），告知 SSE 消费者流结束。
    def push_sentinel(self, task_id: str) -> None:
        q = self._queues.get(task_id)
        if q is not None:
            try:
                q.put_nowait(None)
            except queue.Full:
                pass

    # get_queue 方法，返回任务事件队列（SSE 端点用）。
    def get_queue(self, task_id: str) -> queue.Queue | None:
        return self._queues.get(task_id)

    # set_workflow / get_workflow 方法，保存/取回任务对应的 ControlWorkflow 实例（resume 用）。
    def set_workflow(self, task_id: str, wf: ControlWorkflow) -> None:
        with self._lock:
            self._workflows[task_id] = wf

    def get_workflow(self, task_id: str) -> ControlWorkflow | None:
        with self._lock:
            return self._workflows.get(task_id)


registry = TaskRegistry()


# OrchestratorService 类，串联图外预处理与图内决策，支持 SSE 流与人工干预。
class OrchestratorService:
    def __init__(self, config: AppConfig, matlab_autostart: bool = True) -> None:
        self.config = config
        self.llm = LLMClient(config.model)
        self._matlab_autostart = matlab_autostart
        # 配置全局 registry（模块级单例）
        registry.reconfigure(config.graph.sse_queue_maxsize, config.graph.task_ttl_s)

    # run_pipeline 方法，执行完整流水（在 BackgroundTasks 线程中调用）。
    def run_pipeline(self, task_id: str, paper_id: str, pdf_path: str, user_id: str = "local") -> None:
        def _push(event_type: str, **kw):
            registry.push_event(task_id, {"type": event_type, **kw})

        try:
            # ── 图外预处理 ──────────────────────────────────────
            registry.update(task_id, status="running", stage="mineru")
            _push("stage", stage="mineru", label="PDF 解析中（MinerU）")

            mineru = MineruClient(self.config.mineru)
            result = self._parse_or_reuse(mineru, paper_id, pdf_path)

            registry.update(task_id, stage="adapter")
            _push("stage", stage="adapter", label="结构化适配中")
            paper = mineru_output_to_paper(result, paper_id=paper_id)
            doc_ref = save_parsed_paper(paper)

            registry.update(task_id, stage="knowledge")
            _push("stage", stage="knowledge", label="知识抽取中（LLM）")
            eqs, ctrls, params, criteria = LlmKnowledgeExtractor(self.llm).extract(
                paper, criteria_samples=self.config.knowledge.criteria_samples
            )
            merged = merge_knowledge(paper_id, eqs, ctrls, params, self.config.knowledge.confidence_threshold, criteria=criteria)
            knowledge_ref = save_merged_knowledge(merged)
            crit_dicts = [c.model_dump() for c in criteria]
            registry.update(task_id, criteria=crit_dicts)
            _push("knowledge_done", criteria_count=len(crit_dicts))

            # ── 构建图 ─────────────────────────────────────────
            registry.update(task_id, stage="graph:init")
            _push("stage", stage="graph:init", label="初始化 LangGraph + MATLAB MCP")

            matlab = MatlabMcpClient(get_matlab_client(self.config.matlab, autostart=self._matlab_autostart))
            deps = build_real_deps(
                self.llm,
                matlab,
                criteria_samples=self.config.knowledge.criteria_samples,
                confidence_threshold=self.config.knowledge.confidence_threshold,
            )

            auto_approve = not self.config.matlab.require_human_approval_for_code_execution
            checkpointer = build_checkpointer(
                self.config.graph.checkpoint_backend,
                self.config.graph.checkpoint_path,
            )
            # 从 graph 配置读取分层重试预算
            retry_budget = {
                "L1": self.config.graph.l1_budget,
                "L2": self.config.graph.l2_budget,
                "L3": self.config.graph.l3_budget,
                "L4": self.config.graph.l4_budget,
            }

            def _on_progress(node_stage: str, detail: dict) -> None:
                registry.update(task_id, stage=node_stage)
                _push("node", stage=node_stage, **detail)

            wf = ControlWorkflow(
                deps=deps,
                checkpointer=checkpointer,
                on_progress=_on_progress,
                auto_approve=auto_approve,
                require_verification_approval=self.config.graph.require_verification_approval,
                retry_budget=retry_budget,
                calib_budget=self.config.graph.calib_budget,
            )
            registry.set_workflow(task_id, wf)

            initial_state = WorkflowState(
                trace_id=task_id,
                task_id=task_id,
                paper_id=paper_id,
                user_id=user_id,
                parsed_doc_ref=doc_ref,
                knowledge_json=knowledge_ref,
                acceptance_criteria=crit_dicts,
            )

            # ── 运行图（首次，可能在 interrupt 处提前返回）─────────
            registry.update(task_id, stage="graph:plan")
            _push("stage", stage="graph:plan", label="LangGraph 图启动")

            final = wf.run(initial_state)

            # ── 检查是否暂停在 interrupt() ─────────────────────
            if wf.is_interrupted(task_id):
                payload = wf.get_interrupt_payload(task_id)
                registry.update(task_id, status="awaiting_approval", stage="request_approval")
                _push("interrupt",
                      stage="request_approval",
                      label="等待人工审批：MATLAB 代码已生成，请审核后 resume",
                      payload=payload)
                # 不推 sentinel，SSE 连接保持，等 resume 后续事件
                return

            # ── 正常结束 ───────────────────────────────────────
            self._finalize(task_id, final, _push)

        except Exception as exc:
            registry.update(task_id, status="failed", stage="error", error=f"{type(exc).__name__}: {exc}")
            registry.push_event(task_id, {"type": "error", "error": str(exc)})
            registry.push_sentinel(task_id)

    # resume_pipeline 方法，在人工干预后继续图执行（在 BackgroundTasks 线程中调用）。
    def resume_pipeline(self, task_id: str, approved: bool, edited_code: str | None = None) -> None:
        def _push(event_type: str, **kw):
            registry.push_event(task_id, {"type": event_type, **kw})

        wf = registry.get_workflow(task_id)
        if wf is None:
            registry.update(task_id, status="failed", stage="error", error="workflow_instance_not_found")
            _push("error", error="workflow_instance_not_found")
            registry.push_sentinel(task_id)
            return

        decision = {"approved": approved}
        if edited_code:
            decision["edited_code"] = edited_code

        action_label = "批准执行" if approved else "拒绝→回规划"
        registry.update(task_id, status="running", stage="resuming")
        _push("resume", label=f"恢复执行：{action_label}", approved=approved)

        try:
            final = wf.resume(task_id, decision)

            # 恢复后仍可能再次 interrupt（多轮审批场景）
            if wf.is_interrupted(task_id):
                payload = wf.get_interrupt_payload(task_id)
                registry.update(task_id, status="awaiting_approval", stage="request_approval")
                _push("interrupt",
                      stage="request_approval",
                      label="等待人工审批（新轮次）",
                      payload=payload)
                return

            self._finalize(task_id, final, _push)

        except Exception as exc:
            registry.update(task_id, status="failed", stage="error", error=f"{type(exc).__name__}: {exc}")
            _push("error", error=str(exc))
            registry.push_sentinel(task_id)

    # _finalize 方法，统一处理图正常结束后的登记与事件推送。
    def _finalize(self, task_id: str, final: WorkflowState, push_fn) -> None:
        result = {
            "verification": final.verification_result,
            "verdict": final.verdict,
            "code_paths": final.generated_code_paths,
            "calib_rounds": final.retries.calib,
            "tool_calls": len(final.tool_results),
        }
        registry.update(task_id, status=final.status, stage="done", result=result)
        push_fn("done", status=final.status, result=result)
        registry.push_sentinel(task_id)

    def _parse_or_reuse(self, mineru: MineruClient, paper_id: str, pdf_path: str) -> str:
        existing = Path("data/mineru") / paper_id
        found = next(existing.rglob("*content_list.json"), None) if existing.exists() else None
        if found:
            return str(found)
        return mineru.parse_pdf(paper_id, pdf_path).content_list_path
