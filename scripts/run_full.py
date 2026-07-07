# 完整端到端真实联跑：复用已摄取知识 → DeepSeek 规划/代码 → MATLAB 真机执行 → 分层回滚/figure。
# 用法: python scripts/run_full.py <paper_id>
# 前置: 该 paper 已由 run_ingest.py 完成 MinerU 解析与知识抽取。
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config_loader import load_config, validate_required_secrets
from app.graph.real_nodes import build_real_deps
from app.graph.state import WorkflowState
from app.graph.workflow import ControlWorkflow
from app.llm.client import LLMClient
from app.tools.matlab_mcp import MatlabMcpClient
from app.tools.mcp_factory import get_matlab_client, shutdown_matlab_client


def main(paper_id: str) -> None:
    cfg = load_config("configs")
    validate_required_secrets(cfg)

    parsed = Path("data/knowledge/parsed") / f"{paper_id}.json"
    knowledge = Path("data/knowledge/merged") / f"{paper_id}.json"
    if not knowledge.exists():
        print(f"[!] 知识文件不存在: {knowledge}；请先跑 run_ingest.py")
        raise SystemExit(1)
    merged = json.loads(knowledge.read_text(encoding="utf-8"))
    criteria = merged.get("criteria", [])
    print(f"[0] paper={paper_id} criteria={len(criteria)} 条")
    for c in criteria:  # 验收标准确认卡点（脚本模式自动继续）
        print(f"    - {c.get('metric')}: {c.get('description','')} [{c.get('relation')} {c.get('expected','')}]")

    llm = LLMClient(cfg.model)
    print("[1] starting MATLAB MCP (boot ~120s) ...", flush=True)
    matlab = MatlabMcpClient(get_matlab_client(cfg.matlab, autostart=True))
    print("[1] MATLAB ready", flush=True)

    deps = build_real_deps(llm, matlab)
    wf = ControlWorkflow(deps=deps)
    state = WorkflowState(
        trace_id=paper_id, task_id=f"full_{paper_id}", paper_id=paper_id,
        parsed_doc_ref=str(parsed), knowledge_json=str(knowledge),
        acceptance_criteria=criteria,
    )
    print("[2] running graph (plan → codegen → MATLAB → verify校准/rollback) ...", flush=True)
    try:
        final = wf.run(state, recursion_limit=80)
    finally:
        shutdown_matlab_client()

    print("\n========== 联跑结果 ==========", flush=True)
    print(f"status         : {final.status}")
    print(f"tool_calls     : {len(final.tool_results)}")
    print(f"retries        : L1={final.retries.l1} L2={final.retries.l2} L3={final.retries.l3} L4={final.retries.l4} calib={final.retries.calib}")
    print(f"verification   : {json.dumps(final.verification_result, ensure_ascii=False)[:400]}")
    print(f"computed_metrics: {json.dumps(final.computed_metrics, ensure_ascii=False)[:400]}")
    print(f"code_paths     : {final.generated_code_paths}")
    for r in final.verdict.get("results", []):
        print(f"    verdict: {r.get('metric')} passed={r.get('passed')} expected={r.get('expected')} actual={r.get('actual')} ({r.get('reason','')})")
    for r in final.tool_results:
        tail = (r.stderr or r.stdout or "")[:120].replace("\n", " ")
        print(f"  #{r.index} ok={r.ok} layer={r.error_layer} out/err: {tail}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/run_full.py <paper_id>")
        raise SystemExit(2)
    main(sys.argv[1])
