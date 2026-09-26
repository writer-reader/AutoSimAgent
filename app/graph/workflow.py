# 组装真实 LangGraph 决策图：plan → generate →(审批)→ execute → verify → finalize，
# 失败经 route_after_error 分层回滚（L1 execute / L2 generate / L3 plan / L4 extract_knowledge / L5 fail）。
# 支持实时流式进度回调（on_progress）和人工干预（auto_approve=False 时图在 request_approval 暂停）。
from __future__ import annotations

from typing import Any, Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.graph import nodes as N
from app.graph.router import route_after_approval, route_after_error, route_after_verify, route_tool_call
from app.graph.state import WorkflowState

ProgressCallback = Callable[[str, dict], None]  # (node_name, detail_dict) -> None


# build_checkpointer 函数，按 graph.yaml 配置选择 checkpointer 实现。
# memory  → MemorySaver（进程内，重启丢失）
# sqlite  → SqliteSaver（持久化，重启后 interrupt/resume 仍可恢复）
def build_checkpointer(backend: str = "memory", path: str = "") -> Any:
    if backend == "sqlite":
        try:
            import sqlite3
            from pathlib import Path
            from langgraph.checkpoint.sqlite import SqliteSaver
            db_path = path or "data/checkpoints.db"
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path, check_same_thread=False)
            return SqliteSaver(conn)
        except ImportError as exc:
            raise ImportError(
                "langgraph sqlite checkpointer 需要 langgraph[sqlite] 依赖"
            ) from exc
    return MemorySaver()


# _wrap 函数，在节点执行前后插入进度回调。
def _wrap(handler, node_name: str, on_progress: ProgressCallback | None):
    if on_progress is None:
        return handler

    def wrapped(state):
        on_progress(f"graph:{node_name}", {"node": node_name, "phase": "start"})
        result = handler(state)
        # 节点完成时把该节点产出的关键产物外发（M0 透明化：plan/代码/工具结果/验收判定）
        on_progress(f"graph:{node_name}:done", _node_done_detail(node_name, result))
        return result

    return wrapped


# _node_done_detail 函数，按节点类型提取"完成时刻"的透明化详情。
# 黑盒→直播：plan JSON、生成代码、工具 stdout/stderr 尾部与算出指标、验收逐条判定全部进事件流。
# 对外字段刻意只读，不携带 expected/tolerance（防作弊双防线保留）。
def _node_done_detail(node_name: str, state: WorkflowState) -> dict:
    detail: dict = {"node": node_name, "phase": "done"}
    if node_name == "plan":
        detail["plan"] = state.plan
    elif node_name == "generate":
        detail["code"] = state.generated_code
        detail["code_paths"] = list(state.generated_code_paths)
    elif node_name == "execute":
        last = state.latest_tool()
        if last is not None:
            detail["tool_result"] = {
                "seq": last.index,
                "ok": last.ok,
                "stdout_tail": (last.stdout or "")[-2000:],
                "stderr_tail": (last.stderr or "")[-2000:],
                "artifacts": [a.model_dump() for a in last.artifacts],
                "error_layer": last.error_layer,
            }
        detail["metrics"] = state.computed_metrics
        detail["retries"] = state.retries.model_dump()
    elif node_name == "verify":
        detail["verdict"] = state.verdict
    elif node_name == "extract_knowledge":
        detail["knowledge_ref"] = state.knowledge_json
        detail["criteria_count"] = len(state.acceptance_criteria)
    return detail


# ControlWorkflow 类，封装 LangGraph 图的构建与运行。
class ControlWorkflow:
    # __init__ 方法，注入节点依赖、checkpointer、审批模式、预算与进度回调。
    def __init__(
        self,
        deps: N.NodeDeps | None = None,
        checkpointer: Any | None = None,
        auto_approve: bool = True,
        require_verification_approval: bool = False,
        retry_budget: dict | None = None,
        calib_budget: int = 4,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.deps = deps or N.NodeDeps()
        self.checkpointer = checkpointer or MemorySaver()
        self.auto_approve = auto_approve
        self.require_verification_approval = require_verification_approval
        self.retry_budget = retry_budget  # None → router.py 模块常量
        self.calib_budget = calib_budget
        self.on_progress = on_progress
        self.graph = self._build()

    # _build 方法，声明节点与条件边。
    def _build(self):
        g: StateGraph = StateGraph(WorkflowState)

        g.add_node("plan", _wrap(lambda s: N.plan_node(s, self.deps), "plan", self.on_progress))
        g.add_node("generate", _wrap(lambda s: N.generate_node(s, self.deps), "generate", self.on_progress))
        g.add_node(
            "request_approval",
            _wrap(
                lambda s: N.request_approval_node(s, self.auto_approve),
                "request_approval",
                self.on_progress,
            ),
        )
        g.add_node("execute", _wrap(lambda s: N.execute_node(s, self.deps), "execute", self.on_progress))
        g.add_node("verify", _wrap(lambda s: N.verify_node(s, self.deps), "verify", self.on_progress))
        g.add_node(
            "request_verification_approval",
            _wrap(
                lambda s: N.request_verification_approval_node(s, self.auto_approve),
                "request_verification_approval",
                self.on_progress,
            ),
        )
        g.add_node("extract_knowledge",
                   _wrap(lambda s: N.extract_knowledge_node(s, self.deps), "extract_knowledge", self.on_progress))
        g.add_node("finalize", N.finalize_node)
        g.add_node("finalize_failed", N.finalize_failed_node)

        g.add_edge(START, "plan")
        g.add_edge("plan", "generate")

        # generate 后：高风险工具先审批（首次），重试时已审批直接执行
        g.add_conditional_edges(
            "generate",
            lambda s: route_tool_call(self.deps.tool_name, s),
            {"request_approval": "request_approval", "execute_tool": "execute"},
        )
        # 审批后：通过→执行，拒绝→回 plan，pending→等待（真中断场景由 resume() 驱动）
        g.add_conditional_edges(
            "request_approval",
            route_after_approval,
            {"execute_tool": "execute", "plan": "plan", "request_approval": END},
        )
        # 执行后：分层路由（传入预算）
        g.add_conditional_edges(
            "execute",
            lambda s: route_after_error(s, self.retry_budget),
            {
                "verify": "verify",
                "execute": "execute",
                "generate": "generate",
                "plan": "plan",
                "extract_knowledge": "extract_knowledge",
                "finalize_failed": "finalize_failed",
            },
        )
        g.add_edge("extract_knowledge", "plan")
        # 验收判定后：达标且需人工确认→验收审批；达标且自动→finalize；未达标有预算→回 generate 校准；否则失败
        g.add_conditional_edges(
            "verify",
            lambda s: route_after_verify(s, self.require_verification_approval, self.calib_budget),
            {
                "finalize": "finalize",
                "request_verification_approval": "request_verification_approval",
                "generate": "generate",
                "finalize_failed": "finalize_failed",
            },
        )
        # 验收审批后：approved→finalize，rejected→回 generate 再迭代
        g.add_conditional_edges(
            "request_verification_approval",
            lambda s: "finalize" if s.verification_approval_status == "approved" else "generate",
            {"finalize": "finalize", "generate": "generate"},
        )
        g.add_edge("finalize", END)
        g.add_edge("finalize_failed", END)

        return g.compile(checkpointer=self.checkpointer)

    def _config(self, task_id: str, recursion_limit: int = 50) -> dict:
        return {"configurable": {"thread_id": task_id}, "recursion_limit": recursion_limit}

    # run 方法，执行图并返回终态 WorkflowState（同步，可能在 interrupt 处提前返回）。
    def run(self, state: WorkflowState, recursion_limit: int = 50) -> WorkflowState:
        config = self._config(state.task_id, recursion_limit)
        result = self.graph.invoke(state, config)
        return WorkflowState.model_validate(result)

    # is_interrupted 方法，判断图是否暂停在某个 interrupt() 点（审批等待中）。
    def is_interrupted(self, task_id: str) -> bool:
        config = self._config(task_id)
        try:
            snap = self.graph.get_state(config)
            # tasks 中有 interrupts 说明暂停在 interrupt() 处
            return bool(snap.tasks and any(t.interrupts for t in snap.tasks))
        except Exception:
            return False

    # has_checkpoint 方法，判断该 thread 是否已有 checkpoint（图跑过至少一个节点）。
    # 用于 restart_pipeline 选择续跑（invoke None）还是从图起点跑。
    def has_checkpoint(self, task_id: str) -> bool:
        config = self._config(task_id)
        try:
            snap = self.graph.get_state(config)
            # values 非空 = 已持久化过状态（checkpoint 存在）
            return bool(getattr(snap, "values", None))
        except Exception:
            return False

    # resume_from_checkpoint 方法，从最后 checkpoint 续跑（进程被杀后崩溃恢复）。
    # 关键：invoke(None, config)——只传 config、不重灌输入，LangGraph 从最后完成节点继续。
    # 不同于 run()（invoke(state) 重灌输入）与 resume()（invoke(Command(resume)) 审批恢复）。
    def resume_from_checkpoint(self, task_id: str, recursion_limit: int = 50) -> WorkflowState:
        config = self._config(task_id, recursion_limit)
        result = self.graph.invoke(None, config)
        return WorkflowState.model_validate(result)

    # get_interrupt_payload 方法，返回 interrupt() 传递的 payload（代码预览等）。
    def get_interrupt_payload(self, task_id: str) -> dict:
        config = self._config(task_id)
        try:
            snap = self.graph.get_state(config)
            for t in snap.tasks:
                for intr in t.interrupts:
                    return intr.value if isinstance(intr.value, dict) else {"raw": intr.value}
        except Exception:
            pass
        return {}

    # resume 方法，向暂停的图传入人工决定并继续执行。
    # decision: {"approved": bool, "edited_code": str|None}
    def resume(self, task_id: str, decision: dict, recursion_limit: int = 50) -> WorkflowState:
        config = self._config(task_id, recursion_limit)
        result = self.graph.invoke(Command(resume=decision), config)
        return WorkflowState.model_validate(result)
