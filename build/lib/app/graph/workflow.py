# 组装真实 LangGraph 决策图：plan → generate →(审批)→ execute → verify → finalize，
# 失败经 route_after_error 分层回滚（L1 execute / L2 generate / L3 plan / L4 extract_knowledge / L5 fail）。
from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph import nodes as N
from app.graph.router import route_after_approval, route_after_error, route_after_verify, route_tool_call
from app.graph.state import WorkflowState


# ControlWorkflow 类，封装 LangGraph 图的构建与运行。
class ControlWorkflow:
    # __init__ 方法，注入节点依赖与 checkpointer。
    def __init__(self, deps: N.NodeDeps | None = None, checkpointer: Any | None = None, auto_approve: bool = True) -> None:
        self.deps = deps or N.NodeDeps()
        self.checkpointer = checkpointer or MemorySaver()
        self.auto_approve = auto_approve
        self.graph = self._build()

    # _build 方法，声明节点与条件边。
    def _build(self):
        g: StateGraph = StateGraph(WorkflowState)

        g.add_node("plan", lambda s: N.plan_node(s, self.deps))
        g.add_node("generate", lambda s: N.generate_node(s, self.deps))
        g.add_node("request_approval", lambda s: N.request_approval_node(s, self.auto_approve))
        g.add_node("execute", lambda s: N.execute_node(s, self.deps))
        g.add_node("verify", lambda s: N.verify_node(s, self.deps))
        g.add_node("extract_knowledge", lambda s: s)  # L4 回滚占位（真实抽取在图外，这里仅重置入口）
        g.add_node("finalize", N.finalize_node)
        g.add_node("finalize_failed", N.finalize_failed_node)

        g.add_edge(START, "plan")
        g.add_edge("plan", "generate")

        # generate 后：高风险工具先审批，否则直接执行
        g.add_conditional_edges(
            "generate",
            lambda s: route_tool_call(self.deps.tool_name),
            {"request_approval": "request_approval", "execute_tool": "execute"},
        )
        # 审批后：通过→执行，拒绝→回 plan
        g.add_conditional_edges(
            "request_approval",
            route_after_approval,
            {"execute_tool": "execute", "plan": "plan", "request_approval": END},
        )
        # 执行后：分层路由
        g.add_conditional_edges(
            "execute",
            route_after_error,
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
        # 验收判定后：达标→finalize，未达标→回 generate 校准（预算内），否则失败
        g.add_conditional_edges(
            "verify",
            route_after_verify,
            {"finalize": "finalize", "generate": "generate", "finalize_failed": "finalize_failed"},
        )
        g.add_edge("finalize", END)
        g.add_edge("finalize_failed", END)

        return g.compile(checkpointer=self.checkpointer)

    # run 方法，执行图并返回终态 WorkflowState。
    def run(self, state: WorkflowState, recursion_limit: int = 50) -> WorkflowState:
        config = {"configurable": {"thread_id": state.task_id}, "recursion_limit": recursion_limit}
        result = self.graph.invoke(state, config)
        return WorkflowState.model_validate(result)
