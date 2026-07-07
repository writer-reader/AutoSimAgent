# 端到端编排：图外预处理（导入→MinerU→adapter→知识抽取）+ 图内 LangGraph 决策循环。
# 供 API 以 BackgroundTasks 异步驱动，任务状态经 checkpointer 持久化、可查询。
from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import uuid4

from app.core.config_loader import AppConfig
from app.graph.real_nodes import build_real_deps
from app.graph.state import WorkflowState
from app.graph.workflow import ControlWorkflow
from app.ingestion.adapter import mineru_output_to_paper, save_parsed_paper
from app.ingestion.mineru_client import MineruClient
from app.knowledge.llm_extractor import LlmKnowledgeExtractor
from app.knowledge.postprocessor import merge_knowledge, save_merged_knowledge
from app.llm.client import LLMClient
from app.tools.matlab_mcp import MatlabMcpClient
from app.tools.mcp_factory import get_matlab_client


# 简单的进程内任务登记（自用单机；BackgroundTasks 驱动）。
class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, paper_id: str, user_id: str) -> str:
        task_id = f"task_{uuid4().hex[:12]}"
        with self._lock:
            self._tasks[task_id] = {"task_id": task_id, "paper_id": paper_id, "user_id": user_id,
                                    "status": "created", "stage": "pending", "error": None, "result": None}
        return task_id

    def update(self, task_id: str, **kw) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(kw)

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            return dict(self._tasks[task_id]) if task_id in self._tasks else None


registry = TaskRegistry()


# OrchestratorService 类，串联图外预处理与图内决策。
class OrchestratorService:
    def __init__(self, config: AppConfig, matlab_autostart: bool = True) -> None:
        self.config = config
        self.llm = LLMClient(config.model)
        self._matlab_autostart = matlab_autostart

    # run_pipeline 函数，执行完整流水（在后台线程中调用）。
    def run_pipeline(self, task_id: str, paper_id: str, pdf_path: str, user_id: str = "local") -> None:
        try:
            registry.update(task_id, status="running", stage="mineru")
            mineru = MineruClient(self.config.mineru)
            result = self._parse_or_reuse(mineru, paper_id, pdf_path)

            registry.update(task_id, stage="adapter")
            paper = mineru_output_to_paper(result, paper_id=paper_id)
            doc_ref = save_parsed_paper(paper)

            registry.update(task_id, stage="knowledge")
            eqs, ctrls, params, criteria = LlmKnowledgeExtractor(self.llm).extract(paper, criteria_samples=self.config.knowledge.criteria_samples)
            merged = merge_knowledge(paper_id, eqs, ctrls, params, self.config.knowledge.confidence_threshold, criteria=criteria)
            knowledge_ref = save_merged_knowledge(merged)
            crit_dicts = [c.model_dump() for c in criteria]
            registry.update(task_id, criteria=crit_dicts)

            registry.update(task_id, stage="graph")
            matlab = MatlabMcpClient(get_matlab_client(self.config.matlab, autostart=self._matlab_autostart))
            deps = build_real_deps(self.llm, matlab)
            wf = ControlWorkflow(deps=deps)
            state = WorkflowState(trace_id=task_id, task_id=task_id, paper_id=paper_id, user_id=user_id,
                                  parsed_doc_ref=doc_ref, knowledge_json=knowledge_ref,
                                  acceptance_criteria=crit_dicts)
            final = wf.run(state)
            registry.update(task_id, status=final.status, stage="done",
                            result={"verification": final.verification_result,
                                    "verdict": final.verdict,
                                    "code_paths": final.generated_code_paths,
                                    "calib_rounds": final.retries.calib,
                                    "tool_calls": len(final.tool_results)})
        except Exception as exc:  # 保底：任何阶段异常都登记，不吞
            registry.update(task_id, status="failed", stage="error", error=f"{type(exc).__name__}: {exc}")

    def _parse_or_reuse(self, mineru: MineruClient, paper_id: str, pdf_path: str) -> str:
        existing = Path("data/mineru") / paper_id
        found = next(existing.rglob("*content_list.json"), None) if existing.exists() else None
        if found:
            return str(found)
        return mineru.parse_pdf(paper_id, pdf_path).content_list_path
