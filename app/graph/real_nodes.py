# 真实节点依赖：planner/codegen 走 DeepSeek，executor 走 MATLAB MCP（含 figure 目录扫描 + 代码落盘）。
# 与 graph/nodes.py 的占位实现同构，供 workflow 注入真实闭环。
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.graph.nodes import NodeDeps
from app.graph.state import Artifact, WorkflowState
from app.llm.client import LLMClient
from app.llm.schemas import system, user
from app.tools.matlab_mcp import MatlabMcpClient

# 生成代码时注入的约定：把所有 figure 存到 outdir，供执行后扫描登记。
# 生成代码时的产物保存约定：脚本由 run_matlab_file 执行，工作目录即脚本所在目录，
# 直接用相对文件名/pwd 保存，避免依赖注入 outdir 变量（对 function 开头的脚本更稳）。
_FIGURE_SAVE_HINT = (
    "所有产物直接保存到当前工作目录（用相对文件名或 fullfile(pwd,...)，不要依赖名为 outdir 的变量）。"
    "若产生图形，用 exportgraphics 或 saveas 将每个 figure 存为 fig_1.png、fig_2.png。"
)

# MATLAB 脚本结构约束，避免 local function 相关的常见运行错误。
_SCRIPT_RULES = (
    "严格遵守 MATLAB 脚本规则：(1) 生成单个脚本文件；"
    "(2) 所有 local function 只定义一次，且全部放在脚本最末尾；"
    "(3) 脚本正文（非 function）在前，函数定义在后，不要在中间穿插 function；"
    "(4) 不要重复定义同名函数；(5) 脚本第一行不要是 function（保持为脚本而非函数文件）。"
)

_ARTIFACT_EXTS = {".png": "figure", ".jpg": "figure", ".fig": "figure", ".mat": "data", ".slx": "model", ".csv": "data"}


# _read_json 函数，安全读取落盘的 JSON（不存在返回空）。
def _read_json(path: str) -> Any:
    p = Path(path)
    if not path or not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return {}


# _source_excerpt_for 函数，顺 evidence_ref 锚点从 ParsedPaper 拉取论文原文推导，供 codegen 参考。
def _source_excerpt_for(state: WorkflowState) -> str:
    ref_path = state.parsed_doc_ref
    if not ref_path or not Path(ref_path).exists():
        return ""  # ParsedPaper 未持久化则优雅降级（回到只用 plan/criteria）
    try:
        from app.ingestion.adapter import load_parsed_paper
        from app.knowledge.evidence import build_source_excerpt
        paper = load_parsed_paper(ref_path)
        refs: list[str] = [c.get("evidence_ref", "") for c in state.acceptance_criteria]
        know = _read_json(state.knowledge_json)
        refs += [e.get("evidence_ref", "") for e in know.get("equations", [])]
        refs += [c.get("evidence_ref", "") for c in know.get("controllers", [])]
        excerpt = build_source_excerpt(paper, refs)
    except Exception:
        return ""
    if not excerpt:
        return ""
    return (
        "\n【论文原文（相关推导，务必按论文真实方法实现，尤其稳定性/裕度分析的判据与公式）】：\n"
        + excerpt + "\n"
    )


# RealPlanner 类，用 DeepSeek 依据知识 JSON 生成执行计划。
class RealPlanner:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        knowledge = _read_json(state.knowledge_json)
        prior = state.plan.get("_error_feedback", "")
        prompt = (
            "你是控制系统复现专家。根据以下从论文抽取的结构化知识（公式/控制器/参数），"
            "制定一个用 MATLAB 复现该控制器的执行计划。输出 JSON："
            '{"objective":str,"approach":str,"steps":[str],"key_equations":[str],"key_parameters":[str]}。\n'
            f"知识：{json.dumps(knowledge, ensure_ascii=False)[:12000]}\n"
        )
        if prior:
            prompt += f"\n上一次执行失败，请修正方案。失败信息：{prior}\n"
        result = self.llm.complete([system("只输出 JSON 计划。"), user(prompt)], role="planner",
                                   label="规划：生成仿真执行方案")
        plan = _read_json_text(result)
        plan.setdefault("objective", "reproduce controller")
        return plan


# RealCodeGen 类，用 DeepSeek 依据计划生成 MATLAB 代码。
class RealCodeGen:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def __call__(self, state: WorkflowState) -> str:
        plan = state.plan
        # L2 回滚时带上一次 stderr
        last = state.latest_tool()
        err_ctx = ""
        if last and not last.ok and last.stderr:
            err_ctx = f"\n上一版代码报错，请修复：\n{last.stderr[:1500]}\n上一版代码：\n{state.generated_code[:2000]}\n"
        # 校准回滚时带上一轮验收 mismatch（不泄露期望值，只说未达标+实际算出值）
        calib_ctx = ""
        if state.verdict and not state.verdict.get("passed"):
            fails = [r for r in state.verdict.get("results", []) if not r.get("passed")]
            calib_ctx = (
                f"\n上一轮仿真跑通但指标未达标（{state.verdict.get('summary','')}）。未达标项：\n"
                + "\n".join(f"- {r.get('metric')}: 你上一版算出 {r.get('actual')}，不满足要求（{r.get('reason','')}）" for r in fails)
                + "\n请检查模型/参数/仿真设置是否有误，修正后使这些指标真实达标（不要为凑数而硬编码）。上一版代码：\n"
                + state.generated_code[:2500] + "\n"
            )
        # 验收标准 → 要求代码计算并输出
        crit_ctx = _criteria_prompt(state.acceptance_criteria)
        # 论文原文推导（顺 evidence_ref 锚点检索 ParsedPaper，给 codegen 真实方法）
        src_ctx = _source_excerpt_for(state)
        prompt = (
            "根据以下执行计划生成一段可直接运行的 MATLAB 代码（R2024b）。"
            "假设已有变量 outdir 指向输出目录。" + _FIGURE_SAVE_HINT + _SCRIPT_RULES + crit_ctx + src_ctx +
            f"\n计划：{json.dumps(plan, ensure_ascii=False)[:8000]}\n{err_ctx}{calib_ctx}"
            "只输出 MATLAB 代码，不要 markdown 代码块标记。"
        )
        code = self.llm.complete([system("你是 MATLAB 代码专家，只输出裸代码。"), user(prompt)], role="codegen",
                                 label="代码生成：MATLAB/Simulink")
        return _strip_code_fence(code)


# RealExecutor 类，用 MATLAB MCP 执行代码，扫描 figure，落盘代码。
class RealExecutor:
    def __init__(self, matlab: MatlabMcpClient, work_root: str = "data/code/generated") -> None:
        self.matlab = matlab
        self.work_root = Path(work_root)

    def __call__(self, code: str, state: WorkflowState) -> tuple[bool, str, str, list[Artifact]]:
        outdir = (self.work_root / state.task_id).resolve()
        outdir.mkdir(parents=True, exist_ok=True)
        # 以文件方式执行：含 local function 的完整脚本必须用 run_matlab_file，
        # evaluate_matlab_code 是逐句求值，无法处理脚本内 function 定义 + ode 回调。
        # 脚本写入 outdir，run_matlab_file 会把工作目录设为脚本所在目录，故产物落 outdir。
        code_path = outdir / f"gen_{state.tool_call_seq}.m"
        code_path.write_text(code, encoding="utf-8")
        state.generated_code_paths.append(str(code_path))

        # ── 静态检查：有 error 级问题则直接返回失败，不执行 ──────────────
        try:
            check_result = self.matlab.check_code(str(code_path))
            if check_result.ok and check_result.stdout:
                import json as _json
                issues = _json.loads(check_result.stdout).get("code_issues", [])
                errors = [i for i in issues if i.get("severity") == "error"]
                if errors:
                    err_lines = "\n".join(
                        f"  Line {i.get('line', '?')}: {i.get('description', '')}"
                        for i in errors
                    )
                    before = {p.name for p in outdir.iterdir() if p.is_file()}
                    return False, "", f"[静态检查] MATLAB 语法错误，已拦截（未执行）：\n{err_lines}", []
        except Exception:
            pass  # 静态检查失败不阻断流程，继续执行

        before = {p.name for p in outdir.iterdir() if p.is_file()}
        result = self.matlab.run_file(str(code_path))
        artifacts = self._scan_artifacts(outdir, before)
        state.computed_metrics = self._read_metrics(outdir)
        return result.ok, result.stdout, result.stderr, artifacts

    # _read_metrics 函数，读取 outdir/results.json 作为算出的指标。
    @staticmethod
    def _read_metrics(outdir: Path) -> dict:
        rj = outdir / "results.json"
        if not rj.exists():
            return {}
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"_raw": data}
        except (json.JSONDecodeError, ValueError):
            return {}

    def _scan_artifacts(self, outdir: Path, before: set[str]) -> list[Artifact]:
        arts: list[Artifact] = []
        for p in sorted(outdir.iterdir()):
            if not p.is_file() or p.name in before:
                continue
            kind = _ARTIFACT_EXTS.get(p.suffix.lower())
            if kind:
                arts.append(Artifact(kind=kind, path=str(p), label=p.stem))
        return arts


# RealReExtractor 类，L4 回滚时重新抽取知识（降低置信度阈值 + 增加采样数）。
class RealReExtractor:
    def __init__(self, llm: LLMClient, criteria_samples: int = 1, confidence_threshold: float = 0.6,
                 max_context_tokens: int = 12000) -> None:
        self.llm = llm
        self.criteria_samples = criteria_samples
        self.confidence_threshold = confidence_threshold
        self.max_context_tokens = max_context_tokens

    def __call__(self, state) -> Any:
        from pathlib import Path as _Path

        from app.ingestion.adapter import load_parsed_paper
        from app.knowledge.llm_extractor import LlmKnowledgeExtractor
        from app.knowledge.postprocessor import merge_knowledge, save_merged_knowledge

        ref = state.parsed_doc_ref
        if not ref or not _Path(ref).exists():
            # ParsedPaper 未落盘，退为反馈模式
            feedback = (
                "\n[L4] 知识重抽失败（ParsedPaper 未找到），"
                "请用控制工程估算值补缺失参数，在代码注释中标明。"
            )
            state.plan = {**state.plan, "_error_feedback": (state.plan.get("_error_feedback") or "") + feedback}
            return state

        try:
            paper = load_parsed_paper(ref)
            # 重抽时才启用穷尽多采样+归并去重（首次抽取只跑主 pass；回滚是召回优先、可承受多几次调用的场景）
            new_samples = max(3, self.criteria_samples + 2)
            new_threshold = round(self.confidence_threshold * 0.8, 3)
            extractor = LlmKnowledgeExtractor(self.llm)
            # prompt 全局截断：字符 ≈ token×4（英文/LaTeX 为主）
            eqs, ctrls, params, criteria = extractor.extract(
                paper, criteria_samples=new_samples, max_chars=self.max_context_tokens * 4,
            )
            merged = merge_knowledge(state.paper_id, eqs, ctrls, params, new_threshold, criteria=criteria)
            new_knowledge_ref = save_merged_knowledge(merged)
            state.knowledge_json = new_knowledge_ref
            crit_dicts = [c.model_dump() for c in criteria]
            state.acceptance_criteria = crit_dicts
            feedback = (
                f"\n[L4] 已重新抽取知识（置信度 {self.confidence_threshold}→{new_threshold}，"
                f"criteria_samples {self.criteria_samples}→{new_samples}），请按新知识重新规划。"
            )
            state.plan = {**state.plan, "_error_feedback": (state.plan.get("_error_feedback") or "") + feedback}
        except Exception as exc:
            feedback = (
                f"\n[L4] 知识重抽失败（{type(exc).__name__}: {exc}），"
                "请用控制工程估算值补缺失参数，在代码注释中标明。"
            )
            state.plan = {**state.plan, "_error_feedback": (state.plan.get("_error_feedback") or "") + feedback}
        return state


# build_real_deps 函数，组装真实节点依赖。
def build_real_deps(
    llm: LLMClient,
    matlab: MatlabMcpClient,
    tool_name: str = "evaluate_matlab_code",
    criteria_samples: int = 1,
    confidence_threshold: float = 0.6,
    max_context_tokens: int = 12000,
) -> NodeDeps:
    return NodeDeps(
        planner=RealPlanner(llm),
        codegen=RealCodeGen(llm),
        executor=RealExecutor(matlab),
        verifier=RealVerifier(llm),
        re_extractor=RealReExtractor(llm, criteria_samples, confidence_threshold, max_context_tokens),
        tool_name=tool_name,
    )


# _UNIT_FACTORS，同一物理量常见单位换算倍率（如 ms↔s），用于匹配"期望值的字面量"。
_UNIT_FACTORS = (1.0, 1e-3, 1e3, 1e-2, 1e2, 1e-6, 1e6)


# _num_matches_expected 函数，判断数值是否等于期望值（含常见单位换算）。
def _num_matches_expected(value: float, expected: float) -> bool:
    for f in _UNIT_FACTORS:
        target = expected * f
        if abs(value - target) <= abs(target) * 1e-4 + 1e-12:
            return True
    return False


# _sanitize_desc 函数，抹掉描述中等于期望值的数字（防止答案经 description 泄露给 codegen）。
def _sanitize_desc(desc: str, expected: Any) -> str:
    if not isinstance(expected, (int, float)) or isinstance(expected, bool) or expected == 0:
        return desc

    def _repl(m: re.Match) -> str:
        try:
            v = float(m.group(0))
        except ValueError:
            return m.group(0)
        return "(值略)" if _num_matches_expected(v, float(expected)) else m.group(0)

    return re.sub(r"\d+\.?\d*(?:[eE][-+]?\d+)?", _repl, desc)


# _criteria_prompt 函数，把验收标准转成 codegen 的"必须输出这些指标"提示。
# ⚠️ 刻意不泄露 expected/tolerance，且净化 description 中的答案数字——指标必须从模型真算。
def _criteria_prompt(criteria: list[dict]) -> str:
    if not criteria:
        return ""
    lines = ["\n【验收指标】代码必须**从仿真/模型真实计算**以下指标（严禁直接赋常数字面量，也严禁把目标值反推成参数再算回来），并在脚本末尾用 jsonencode 写入当前目录的 results.json（顶层键与 metric 名完全一致，值为数值/布尔）："]
    for c in criteria:
        rel = c.get("relation", "")
        hint = {
            "converges": "（需仿真到稳态后取误差实际值）",
            "approx_zero": "（取实际残差值，勿直接写0）",
            "stable": "（需判定系统是否稳定）",
            "decreasing": "（需验证单调性）",
        }.get(rel, "")
        desc = _sanitize_desc(c.get("description", ""), c.get("expected"))
        lines.append(f"- {c.get('metric')}: {desc}{hint}")
    lines.append(
        "特别地，任何'裕度/margin/临界值'类指标必须通过对给定通信图/参数做特征值或稳定性扫描算出，"
        "不得预设目标值再反推。写 results.json 示例："
        "fid=fopen('results.json','w'); fwrite(fid, jsonencode(results)); fclose(fid);"
    )
    return "\n".join(lines)


# RealVerifier 类，读取算出的指标与验收标准做逐条比对（数值在代码判，模糊项交 LLM）。
class RealVerifier:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        last = state.latest_tool()
        if not (last and last.ok):
            return {"passed": False, "summary": "execution_failed", "results": []}
        criteria = state.acceptance_criteria
        if not criteria:
            return {"passed": True, "summary": "ran_ok_no_criteria", "results": []}
        metrics = state.computed_metrics or {}
        results = [self._check_one(c, metrics, last.stdout) for c in criteria]
        # 防作弊 A：确定性字面量泄露检测——代码含等于期望值的字面量即判可疑（抓反推凑答案）
        leaked = _literal_leak_check(state.generated_code, criteria)
        # 防作弊 B：LLM 读代码判硬编码/反推
        hardcoded = self._detect_hardcoded(state.generated_code, [c.get("metric", "") for c in criteria])
        suspect = {**leaked, **hardcoded}
        for r in results:
            if r["metric"] in suspect:
                r["passed"] = False
                r["reason"] = f"作弊嫌疑（未从模型正向计算）：{suspect[r['metric']]}"
                r["hardcoded"] = True
        n_pass = sum(1 for r in results if r["passed"])
        return {"passed": n_pass == len(results), "results": results,
                "summary": f"{n_pass}/{len(results)} criteria met",
                "hardcoded": list(suspect.keys())}

    # _detect_hardcoded 函数，用 LLM 读代码，判定哪些指标是硬编码/反推而非正向计算。
    def _detect_hardcoded(self, code: str, metrics: list[str]) -> dict[str, str]:
        if not code or not metrics:
            return {}
        prompt = (
            "审查以下 MATLAB 代码，判断每个指标是否为【作弊】。作弊包括两类：\n"
            "(a) 直接赋常数字面量（如 x = 7.6;）；\n"
            "(b) 反推凑答案：先设一个目标值（如 tau_target = 7.6e-3），再据此反解参数(fzero/解方程)，"
            "最后用被凑过的参数'算'回该目标——这本质是抄答案。\n"
            "只有当指标是对给定输入正向、独立计算得到时才算合法。"
            "输出 JSON：{\"hardcoded\":{\"metric名\":\"简短理由\"}}，只列作弊的，没有则空对象。\n"
            f"待查指标：{metrics}\n代码：\n{code[:6000]}"
        )
        try:
            out = self.llm.structured([system("你是严格的代码审查员，专抓硬编码与反推凑答案作弊。"), user(prompt)], _HardcodeOut, role="extractor",
                                      label="审查：硬编码/作弊检查")
            return {k: v for k, v in out.hardcoded.items() if k in metrics}
        except Exception:
            return {}

    # _check_one 函数，判定单条验收标准。
    def _check_one(self, crit: dict, metrics: dict, stdout: str) -> dict[str, Any]:
        metric = crit.get("metric", "")
        relation = crit.get("relation", "qualitative")
        expected = crit.get("expected")
        tol = crit.get("tolerance")
        actual = metrics.get(metric)
        base = {"metric": metric, "expected": expected, "actual": actual, "relation": relation}

        # 数值型关系：代码内直接判
        numeric = {"approx_zero", "approx", "less_than", "greater_than", "equals"}
        if relation in numeric and _is_number(actual):
            passed, reason = _numeric_check(relation, float(actual), expected, tol)
            return {**base, "passed": passed, "reason": reason}
        # 布尔 equals
        if relation == "equals" and isinstance(actual, bool):
            return {**base, "passed": actual == expected, "reason": "bool eq"}
        # 模糊/定性或指标缺失 → LLM 判
        return {**base, **self._llm_judge(crit, metrics, stdout)}

    # _llm_judge 函数，用 LLM 判定模糊/定性命题。
    def _llm_judge(self, crit: dict, metrics: dict, stdout: str) -> dict[str, Any]:
        prompt = (
            "判断以下论文验收标准是否被仿真结果满足。只输出 JSON：{\"passed\":bool,\"reason\":str}。\n"
            f"验收标准：{json.dumps(crit, ensure_ascii=False)}\n"
            f"代码算出的指标(results.json)：{json.dumps(metrics, ensure_ascii=False)[:2000]}\n"
            f"仿真输出摘要：{(stdout or '')[:1000]}\n"
        )
        try:
            out = self.llm.structured([system("你是严谨的复现结果审核员。"), user(prompt)], _JudgeOut, role="extractor",
                                      label="审核：复现结果评审")
            return {"passed": bool(out.passed), "reason": out.reason}
        except Exception as exc:
            return {"passed": False, "reason": f"judge_failed: {exc}"}


# _JudgeOut 类，LLM 判定输出。
class _JudgeOut(BaseModel):
    passed: bool
    reason: str = ""


# _HardcodeOut 类，硬编码审查输出（metric名 → 理由）。
class _HardcodeOut(BaseModel):
    hardcoded: dict[str, str] = {}


# _literal_leak_check 函数，确定性检测：代码中出现等于某指标期望值的字面量即判可疑（抓反推凑答案）。
# 只对非零数值 expected 生效（0 太常见会误伤）。
def _literal_leak_check(code: str, criteria: list[dict]) -> dict[str, str]:
    flagged: dict[str, str] = {}
    if not code:
        return flagged
    nums: list[float] = []
    for tok in re.findall(r"\d+\.?\d*(?:[eE][-+]?\d+)?", code):
        try:
            nums.append(float(tok))
        except ValueError:
            continue
    for c in criteria:
        exp = c.get("expected")
        if not isinstance(exp, (int, float)) or isinstance(exp, bool) or exp == 0:
            continue
        if any(_num_matches_expected(n, float(exp)) for n in nums):
            flagged[c.get("metric", "")] = f"代码含等于期望值({exp})的字面量，疑似反推/抄答案"
    return flagged


# _is_number 函数，判断是否可作数值比较。
def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# _numeric_check 函数，数值关系判定。
def _numeric_check(relation: str, actual: float, expected: Any, tol: float | None) -> tuple[bool, str]:
    t = tol if tol is not None else 1e-3
    if relation == "approx_zero":
        return abs(actual) <= t, f"|{actual}|<= {t}"
    if relation == "approx" and _is_number(expected):
        return abs(actual - float(expected)) <= t, f"|{actual}-{expected}|<= {t}"
    if relation == "less_than" and _is_number(expected):
        return actual < float(expected), f"{actual}<{expected}"
    if relation == "greater_than" and _is_number(expected):
        return actual > float(expected), f"{actual}>{expected}"
    if relation == "equals" and _is_number(expected):
        return abs(actual - float(expected)) <= t, f"{actual}=={expected}"
    return False, "unhandled_numeric"


# _strip_code_fence 函数，去除 LLM 可能输出的 markdown 代码块围栏。
def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return t


# _read_json_text 函数，从可能含围栏的文本中解析 JSON。
def _read_json_text(text: str) -> dict[str, Any]:
    stripped = _strip_code_fence(text)
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else {"raw": data}
    except (json.JSONDecodeError, ValueError):
        return {"objective": "reproduce controller", "raw": stripped[:500]}
