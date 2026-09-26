# 端到端编排：图外预处理（导入→MinerU→adapter→知识抽取）+ 图内 LangGraph 决策循环。
# 任务状态与事件经 EventStore 落 SQLite（重启不丢、可回放），SSE 从事件表增量读取。
# 支持人工干预（POST /workflow/{task_id}/resume）；重启后凭 checkpointer + 事件库可恢复 workflow 实例。
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config_loader import AppConfig
from app.core.log_context import reset_log_context, set_log_context
from app.events.context import reset_event_emitter, set_event_emitter
from app.events.store import EventStore, TERMINAL_STATUSES
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

# 进程内 ControlWorkflow 实例缓存（运行中的任务用；重启后可从 checkpointer 重建——见 _build_workflow）。
_DEFAULT_DB = "data/autoagent.db"


# TaskRegistry 类，任务登记 + 事件推送的门面，后端落 EventStore（持久化）。
# 兼容旧内存接口（create/update/get/push_event/push_sentinel/get_queue），并新增 list_tasks/read_events。
class TaskRegistry:
    def __init__(self) -> None:
        self._store: EventStore | None = None
        self._workflows: dict[str, ControlWorkflow] = {}
        self._lock = threading.Lock()
        # 默认懒初始化（测试覆盖时由 attach_store 替换）
        self._db_path = os.environ.get("CONTROL_AGENT_SESSION_DB", _DEFAULT_DB)

    # attach_store 方法，注入一个已建好的 EventStore（测试隔离用）。
    def attach_store(self, store: EventStore) -> None:
        with self._lock:
            self._store = store
            self._workflows.clear()

    # _ensure 方法，惰性创建默认 EventStore。
    def _ensure(self) -> EventStore:
        if self._store is None:
            self._store = EventStore(self._db_path)
        return self._store

    # reconfigure 方法，按配置切换库路径（仅在首次生效，避免运行中换库丢数据）。
    def reconfigure(self, db_path: str, **_legacy) -> None:
        with self._lock:
            if self._store is None:
                self._db_path = db_path or self._db_path
            else:
                # 已有连接：路径不同则重建（一般发生在进程启动后首次加载配置时）
                if db_path and db_path != self._db_path:
                    self._store.close()
                    self._db_path = db_path
                    self._store = EventStore(self._db_path)

    # ── 任务登记（落库）────────────────────────────────────

    # create 方法，注册新任务，返回 task_id。
    def create(self, paper_id: str, user_id: str) -> str:
        task_id = f"task_{uuid4().hex[:12]}"
        self._ensure().create_task(task_id, paper_id, user_id)
        return task_id

    # update 方法，更新任务元数据（status/stage/error/result/criteria）。
    def update(self, task_id: str, **kw) -> None:
        self._ensure().update_task(task_id, **kw)

    # get 方法，返回任务元数据快照（含 result/criteria 反序列化）。
    def get(self, task_id: str) -> dict | None:
        return self._ensure().get_task(task_id)

    # list_tasks 方法，列出任务（按创建时间倒序，可按 status/paper_id 过滤）。
    def list_tasks(self, status: str | None = None, paper_id: str | None = None,
                   limit: int = 50, offset: int = 0) -> list[dict]:
        return self._ensure().list_tasks(status, paper_id, limit, offset)

    # delete 方法，删除任务记录及其事件流（运行中的任务由路由层拒绝）。
    def delete(self, task_id: str) -> bool:
        return self._ensure().delete_task(task_id)

    # ── 事件日志（append-only 落库）──────────────────────

    # push_event 方法，写一条事件到事件库（持久化，不丢）。
    def push_event(self, task_id: str, event: dict) -> None:
        self._ensure().append_event(task_id, event)

    # push_sentinel 方法，兼容旧调用（事件库模式下 SSE 按"终态+读空"自动收尾，无需哨兵）。
    def push_sentinel(self, task_id: str) -> None:  # noqa: ARG002
        return None

    # read_events 方法，读取 seq > after_seq 的事件（SSE 增量拉取 + 回放共用）。
    def read_events(self, task_id: str, after_seq: int = 0, limit: int = 200) -> list[dict]:
        return self._ensure().read_events(task_id, after_seq, limit)

    # is_terminal 方法，判断任务是否已到终态（SSE 收尾用）。
    def is_terminal(self, task_id: str) -> bool:
        t = self._ensure().get_task(task_id)
        return bool(t and t.get("status") in TERMINAL_STATUSES)

    # event_store 方法，返回底层 EventStore（监测端点统计用）。
    def event_store(self) -> EventStore:
        return self._ensure()

    # mark_orphans_interrupted 方法，启动时把被杀的 running 任务标为可恢复（供 lifespan 调用）。
    def mark_orphans_interrupted(self) -> int:
        return self._ensure().mark_orphans_interrupted()

    # ── Workflow 实例缓存（运行中的任务 + 重启重建）──────

    # set_workflow / get_workflow 方法，保存/取回任务对应的 ControlWorkflow 实例（resume 用）。
    def set_workflow(self, task_id: str, wf: ControlWorkflow) -> None:
        with self._lock:
            self._workflows[task_id] = wf

    def get_workflow(self, task_id: str) -> ControlWorkflow | None:
        with self._lock:
            return self._workflows.get(task_id)

    def drop_workflow(self, task_id: str) -> None:
        with self._lock:
            self._workflows.pop(task_id, None)


registry = TaskRegistry()


# OrchestratorService 类，串联图外预处理与图内决策，支持 SSE 流与人工干预。
class OrchestratorService:
    def __init__(self, config: AppConfig, matlab_autostart: bool = True) -> None:
        self.config = config
        self.llm = LLMClient(config.model)
        self._matlab_autostart = matlab_autostart
        # 切换 registry 到配置的库路径（启动后立即生效）
        registry.reconfigure(config.graph.session_db_path)

    # run_pipeline 方法，执行完整流水（在 BackgroundTasks 线程中调用）。
    def run_pipeline(self, task_id: str, paper_id: str, pdf_path: str, user_id: str = "local") -> None:
        _tokens = self._attach_task_context(task_id, paper_id)
        def _push(event_type: str, **kw):
            registry.push_event(task_id, {"type": event_type, **kw})

        try:
            # ── 图外预处理（幂等：MinerU/adapter/知识抽取均复用已有产物）──
            doc_ref, knowledge_ref, crit_dicts, merged = self._preprocess(task_id, paper_id, pdf_path, _push)

            # ── 构建图 ─────────────────────────────────────────
            registry.update(task_id, status="running", stage="graph:init")
            _push("stage", stage="graph:init", label="初始化 LangGraph + MATLAB MCP")

            wf = self._build_workflow(task_id)
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
            self._after_run(task_id, wf, final, _push)

        except Exception as exc:
            registry.update(task_id, status="failed", stage="error", error=f"{type(exc).__name__}: {exc}")
            registry.push_event(task_id, {"type": "error", "error": str(exc),
                                          "error_class": type(exc).__name__})
        finally:
            self._detach_task_context(_tokens)

    # _preprocess 方法，图外预处理（MinerU→adapter→知识抽取），幂等：各步产物已存在则复用。
    # 返回 (doc_ref, knowledge_ref, crit_dicts, merged)。run_pipeline 与 restart_pipeline 共用。
    def _preprocess(self, task_id: str, paper_id: str, pdf_path: str, _push) -> tuple[str, str, list[dict], Any]:
        registry.update(task_id, status="running", stage="mineru")
        _push("stage", stage="mineru", label="PDF 解析中（MinerU）")

        mineru = MineruClient(self.config.mineru)
        result = self._parse_or_reuse(mineru, paper_id, pdf_path)

        # adapter 复用：parsed/{paper_id}.json 已存在则 load，跳过重新适配
        parsed_path = Path("data/knowledge/parsed") / f"{paper_id}.json"
        registry.update(task_id, stage="adapter")
        _push("stage", stage="adapter", label="结构化适配中")
        if parsed_path.exists():
            from app.ingestion.adapter import load_parsed_paper
            doc_ref = str(parsed_path)
            paper = load_parsed_paper(doc_ref)
        else:
            paper = mineru_output_to_paper(result, paper_id=paper_id)
            doc_ref = save_parsed_paper(paper)

        # 知识抽取复用：merged/{paper_id}.json 已存在则 load，跳过 LLM 抽取（省时省钱、确定性）
        merged_path = Path("data/knowledge/merged") / f"{paper_id}.json"
        registry.update(task_id, stage="knowledge")
        _push("stage", stage="knowledge", label="知识抽取中（LLM）")
        if merged_path.exists():
            knowledge_ref = str(merged_path)
            merged = _load_merged_knowledge(knowledge_ref)
            crit_dicts = (merged.get("criteria") if isinstance(merged, dict) else None) or []
        else:
            eqs, ctrls, params, criteria = LlmKnowledgeExtractor(self.llm).extract(
                paper, criteria_samples=self.config.knowledge.criteria_samples,
                max_chars=self.config.knowledge.max_context_tokens * 4,
            )
            merged = merge_knowledge(paper_id, eqs, ctrls, params, self.config.knowledge.confidence_threshold, criteria=criteria)
            knowledge_ref = save_merged_knowledge(merged)
            crit_dicts = [c.model_dump() for c in criteria]

        registry.update(task_id, criteria=crit_dicts)
        # 透明化：把论文被读成的样子（公式/参数/控制器/验收标准）外发
        _push("knowledge_done",
              criteria_count=len(crit_dicts),
              criteria=[{"criteria_id": c.get("criterion_id"), "description": c.get("description")} for c in crit_dicts],
              knowledge=_summarize_knowledge(merged))
        return doc_ref, knowledge_ref, crit_dicts, merged

    # _after_run 方法，图运行后的统一收尾：判 interrupt 或 finalize。
    def _after_run(self, task_id: str, wf: "ControlWorkflow", final: WorkflowState, _push) -> None:
        if wf.is_interrupted(task_id):
            payload = wf.get_interrupt_payload(task_id)
            registry.update(task_id, status="awaiting_approval", stage="request_approval")
            _push("interrupt",
                  stage="request_approval",
                  label="等待人工审批：MATLAB 代码已生成，请审核后 resume",
                  payload=payload)
            return
        self._finalize(task_id, final, _push)

    # resume_pipeline 方法，在人工干预后继续图执行（在 BackgroundTasks 线程中调用）。
    def resume_pipeline(self, task_id: str, approved: bool, edited_code: str | None = None, interrupt_key: str | None = None) -> None:
        _task = registry.get(task_id) or {}
        _tokens = self._attach_task_context(task_id, _task.get("paper_id"))
        def _push(event_type: str, **kw):
            registry.push_event(task_id, {"type": event_type, **kw})

        # 重启恢复：内存里没有 workflow 实例时，凭 checkpointer 重建一个（thread_id=task_id 续上状态）
        wf = registry.get_workflow(task_id)
        if wf is None:
            try:
                wf = self._build_workflow(task_id)
                registry.set_workflow(task_id, wf)
            except Exception as exc:
                registry.update(task_id, status="failed", stage="error", error=f"resume_rebuild_failed: {exc}")
                _push("error", error=f"无法重建 workflow 实例：{exc}")
                return

        decision = {"approved": approved}
        if edited_code:
            decision["edited_code"] = edited_code

        action_label = "批准执行" if approved else "拒绝→回规划"
        # 清掉上一次失败的 error 残留，避免"状态恢复运行/待审批但 error 还挂着旧报错"的矛盾展示
        registry.update(task_id, status="running", stage="resuming", error=None)
        _push("resume", label=f"恢复执行：{action_label}", approved=approved)

        try:
            final = wf.resume(task_id, decision)
            self._after_run(task_id, wf, final, _push)
        except Exception as exc:
            registry.update(task_id, status="failed", stage="error", error=f"{type(exc).__name__}: {exc}")
            _push("error", error=str(exc), error_class=type(exc).__name__)
        finally:
            self._detach_task_context(_tokens)

    # restart_pipeline 方法，崩溃恢复：从最近 checkpoint 续跑（连回滚中断点都能续）。
    # 有 checkpoint → resume_from_checkpoint（不重灌输入）；无 checkpoint → 幂等重跑图外预处理 + 从图起点跑。
    def restart_pipeline(self, task_id: str) -> None:
        task = registry.get(task_id)
        if task is None:
            _tokens = self._attach_task_context(task_id, None)
            registry.push_event(task_id, {"type": "error", "error": "task_not_found"})
            self._detach_task_context(_tokens)
            return
        paper_id = task.get("paper_id", "")
        user_id = task.get("user_id", "local")
        _tokens = self._attach_task_context(task_id, paper_id)
        def _push(event_type: str, **kw):
            registry.push_event(task_id, {"type": event_type, **kw})

        try:
            wf = self._build_workflow(task_id)
            registry.set_workflow(task_id, wf)

            if wf.has_checkpoint(task_id):
                # 图内有 checkpoint：从最后完成节点续跑（invoke(None, config)）
                registry.update(task_id, status="running", stage="restarting", error=None)
                _push("restart", label="从断点恢复执行（续跑 LangGraph）", has_checkpoint=True)
                final = wf.resume_from_checkpoint(task_id)
                self._after_run(task_id, wf, final, _push)
            else:
                # 无 checkpoint（死在图外预处理）：幂等重跑图外预处理再进图
                registry.update(task_id, status="running", stage="restarting", error=None)
                _push("restart", label="从断点恢复执行（重跑图外预处理）", has_checkpoint=False)
                # pdf_path 从 paper_id 派生（路径确定性：data/papers/{paper_id}.pdf）
                pdf_path = str(Path("data/papers") / f"{paper_id}.pdf")
                doc_ref, knowledge_ref, crit_dicts, merged = self._preprocess(task_id, paper_id, pdf_path, _push)

                registry.update(task_id, stage="graph:init")
                _push("stage", stage="graph:init", label="初始化 LangGraph + MATLAB MCP")
                initial_state = WorkflowState(
                    trace_id=task_id, task_id=task_id, paper_id=paper_id, user_id=user_id,
                    parsed_doc_ref=doc_ref, knowledge_json=knowledge_ref, acceptance_criteria=crit_dicts,
                )
                registry.update(task_id, stage="graph:plan")
                _push("stage", stage="graph:plan", label="LangGraph 图启动")
                final = wf.run(initial_state)
                self._after_run(task_id, wf, final, _push)
        except Exception as exc:
            registry.update(task_id, status="failed", stage="error", error=f"{type(exc).__name__}: {exc}")
            _push("error", error=str(exc), error_class=type(exc).__name__)
        finally:
            self._detach_task_context(_tokens)

    # _attach_task_context 方法，把当前任务的事件出口与日志追踪字段挂到执行线程上下文：
    # 事件出口让无 task_id 的深层组件（LLMClient）也能发 llm_call 等透明化事件；
    # 日志上下文让线程内所有日志自动携带 task_id/paper_id/trace_id（JsonFormatter 输出）。
    # 返回两个 token（事件、日志），收尾时经 _detach_task_context 配对复位。
    @staticmethod
    def _attach_task_context(task_id: str, paper_id: str | None = None):
        emit_token = set_event_emitter(
            lambda etype, kw: registry.push_event(task_id, {"type": etype, **kw})
        )
        log_token = set_log_context(task_id=task_id, paper_id=paper_id, trace_id=task_id)
        return emit_token, log_token

    # _detach_task_context 方法，复位 _attach_task_context 挂上的两个上下文。
    @staticmethod
    def _detach_task_context(tokens) -> None:
        emit_token, log_token = tokens
        reset_event_emitter(emit_token)
        reset_log_context(log_token)

    # _build_workflow 方法，按配置组装 ControlWorkflow（run/resume 共用，保证重启可续）。
    def _build_workflow(self, task_id: str) -> ControlWorkflow:
        matlab = MatlabMcpClient(get_matlab_client(self.config.matlab, autostart=self._matlab_autostart))
        deps = build_real_deps(
            self.llm,
            matlab,
            criteria_samples=self.config.knowledge.criteria_samples,
            confidence_threshold=self.config.knowledge.confidence_threshold,
            max_context_tokens=self.config.knowledge.max_context_tokens,
        )
        auto_approve = not self.config.matlab.require_human_approval_for_code_execution
        checkpointer = build_checkpointer(
            self.config.graph.checkpoint_backend,
            self.config.graph.checkpoint_path,
        )
        retry_budget = {
            "L1": self.config.graph.l1_budget,
            "L2": self.config.graph.l2_budget,
            "L3": self.config.graph.l3_budget,
            "L4": self.config.graph.l4_budget,
        }

        def _on_progress(node_stage: str, detail: dict) -> None:
            registry.update(task_id, stage=node_stage)
            registry.push_event(task_id, {"type": "node", "stage": node_stage, **detail})

        return ControlWorkflow(
            deps=deps,
            checkpointer=checkpointer,
            on_progress=_on_progress,
            auto_approve=auto_approve,
            require_verification_approval=self.config.graph.require_verification_approval,
            retry_budget=retry_budget,
            calib_budget=self.config.graph.calib_budget,
        )

    # _finalize 方法，统一处理图正常结束后的登记与事件推送。
    def _finalize(self, task_id: str, final: WorkflowState, push_fn) -> None:
        # 从 acceptance_criteria 和 verdict.results 构建 criteria_results（前端约定格式）
        verdict_results: list[dict] = (final.verdict or {}).get("results", [])
        criteria_results = []
        for i, crit in enumerate(final.acceptance_criteria):
            verdict_item = verdict_results[i] if i < len(verdict_results) else {}
            criteria_results.append({
                "criteria_id": crit.get("criterion_id", f"c{i}"),
                "passed": bool(verdict_item.get("passed", False)),
                "detail": verdict_item.get("detail") or verdict_item.get("message") or None,
            })

        verification = dict(final.verification_result)
        verification["criteria_results"] = criteria_results

        # 产物：跨工具调用去重后的文件清单（figure/data/model），前端据此展示仿真图像
        artifacts: list[dict] = []
        seen_paths: set[str] = set()
        for tr in final.tool_results:
            for a in tr.artifacts:
                if a.path in seen_paths:
                    continue
                seen_paths.add(a.path)
                artifacts.append({"kind": a.kind, "path": a.path, "label": a.label})

        result = {
            "verification": verification,
            # verdict 前端期望 string|null，从 dict 中取 summary 字段
            "verdict": (final.verdict or {}).get("summary") or None,
            "code_paths": final.generated_code_paths,
            "artifacts": artifacts,
            "calib_rounds": final.retries.calib,
            "tool_calls": len(final.tool_results),
        }
        registry.update(task_id, status=final.status, stage="done", result=result)
        push_fn("done", status=final.status, result=result)

    def _parse_or_reuse(self, mineru: MineruClient, paper_id: str, pdf_path: str) -> str:
        existing = Path("data/mineru") / paper_id
        found = next(existing.rglob("*content_list.json"), None) if existing.exists() else None
        if found:
            return str(found)
        return mineru.parse_pdf(paper_id, pdf_path).content_list_path


# _load_merged_knowledge 函数，读 merged/{paper_id}.json 为 dict（图外预处理复用 + _summarize 用）。
def _load_merged_knowledge(ref_path: str) -> dict:
    p = Path(ref_path)
    if not ref_path or not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


# _summarize_knowledge 函数，把 MergedKnowledge 摘要成可外发的 JSON（截断防事件过大）。
# 公式取 latex/category/confidence/evidence_ref；参数取 symbol/value/unit/confidence；控制器取 type/confidence。
def _summarize_knowledge(merged) -> dict:
    if merged is None:
        return {}
    try:
        m = merged.model_dump() if hasattr(merged, "model_dump") else dict(merged)
    except Exception:
        return {}
    eqs = []
    for e in (m.get("equations") or [])[:60]:
        eqs.append({
            "latex": (e.get("latex") or "")[:400],
            "category": e.get("category"),
            "confidence": e.get("confidence"),
            "evidence_ref": e.get("evidence_ref"),
        })
    pars = []
    for p in (m.get("parameters") or [])[:80]:
        pars.append({
            "symbol": p.get("symbol"),
            "value": p.get("value"),
            "unit": p.get("unit"),
            "confidence": p.get("confidence"),
            "evidence_ref": p.get("evidence_ref"),
        })
    ctrls = []
    for c in (m.get("controllers") or [])[:40]:
        ctrls.append({
            "type": c.get("type"),
            "architecture": c.get("architecture"),
            "confidence": c.get("confidence"),
            "evidence_ref": c.get("evidence_ref"),
        })
    return {"equations": eqs, "parameters": pars, "controllers": ctrls,
            "equation_count": len(m.get("equations") or []),
            "parameter_count": len(m.get("parameters") or []),
            "controller_count": len(m.get("controllers") or [])}
