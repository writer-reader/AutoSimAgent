# 基于 LLM 的知识抽取：从 ParsedPaper 一次性抽取公式/控制器/参数，输出严格 schema。
# 取代旧的正则/关键词抽取器。用「LLM 友好中间 schema + 映射严格 schema」降低校验摩擦。
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.ingestion.parser import ParsedPaper
from app.knowledge.schemas import AcceptanceCriterion, Controller, Equation, Parameter
from app.llm.client import LLMClient
from app.llm.schemas import system, user

EquationCategory = Literal["dynamics", "controller", "lyapunov", "constraint", "cost_function", "other"]
ControllerType = Literal["PID", "MPC", "sliding_mode", "backstepping", "adaptive", "robust", "other"]
ParamScope = Literal["plant", "controller", "simulation", "noise", "initial_condition", "other"]
CriterionRelation = Literal[
    "approx_zero", "approx", "less_than", "greater_than",
    "equals", "converges", "decreasing", "stable", "qualitative",
]


# _EqOut 类，LLM 输出的公式中间结构（不含 id/paper_id）。
class _EqOut(BaseModel):
    latex: str
    normalized_latex: str = ""
    category: EquationCategory = "other"
    symbols: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    evidence_ref: str = ""
    confidence: float = 0.7


# _CtrlOut 类，LLM 输出的控制器中间结构。
class _CtrlOut(BaseModel):
    type: ControllerType = "other"
    architecture: str = ""
    input_signals: list[str] = Field(default_factory=list)
    output_signals: list[str] = Field(default_factory=list)
    implementation_notes: str = ""
    evidence_ref: str = ""
    confidence: float = 0.7


# _ParamOut 类，LLM 输出的参数中间结构。
class _ParamOut(BaseModel):
    symbol: str
    name: str = ""
    value: str | float | None = None
    unit: str | None = None
    context: str = ""
    belongs_to: ParamScope = "other"
    evidence_ref: str = ""
    confidence: float = 0.7


# _CritOut 类，LLM 输出的验收标准中间结构。
class _CritOut(BaseModel):
    metric: str
    description: str = ""
    relation: CriterionRelation = "qualitative"
    expected: float | str | bool | None = None
    tolerance: float | None = None
    evidence_ref: str = ""
    confidence: float = 0.7


# KnowledgeExtraction 类，LLM 一次抽取的完整输出。
class KnowledgeExtraction(BaseModel):
    equations: list[_EqOut] = Field(default_factory=list)
    controllers: list[_CtrlOut] = Field(default_factory=list)
    parameters: list[_ParamOut] = Field(default_factory=list)
    criteria: list[_CritOut] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "你是控制系统领域的论文分析专家。给定一篇已结构化的论文（含 section 与带锚点的块），"
    "请抽取四类知识并输出 JSON：\n"
    "1) equations：动力学/控制律/李雅普诺夫/约束/代价函数等关键公式，给出 latex、normalized_latex"
    "（规整后的 LaTeX）、category、涉及 symbols、assumptions。\n"
    "2) controllers：论文提出的控制器，给出 type、architecture（简述结构）、input_signals、output_signals、"
    "implementation_notes。\n"
    "3) parameters：带数值的参数，给出 symbol、name、value、unit、belongs_to、context。\n"
    "4) criteria：论文声称的、可用仿真验证的定量结果（复现的验收标准）。每条给出：\n"
    "   - metric：一个简短的机读指标名（英文蛇形，如 freq_error_final、power_sharing_error、delay_margin_freq、stable_beyond_margin），复现代码将以此为键输出数值；\n"
    "   - description：该命题的自然语言描述；\n"
    "   - relation：approx_zero(趋于0)/approx(约等于expected)/less_than/greater_than/equals/converges(收敛)/decreasing(单调降)/stable(稳定)/qualitative(定性)；\n"
    "   - expected：期望值（数值/字符串/布尔，可空）；tolerance：数值容差（可空）。\n"
    "每一项都必须给出 evidence_ref（引用最相关块的锚点，如 'section_3.block_0'）与 confidence(0~1)。"
    "只输出符合 schema 的 JSON，不要多余文字。找不到的类别返回空数组。"
)


# _CriteriaOnly 类，仅验收标准的抽取/归并输出。
class _CriteriaOnly(BaseModel):
    criteria: list[_CritOut] = Field(default_factory=list)


# 穷尽式验收标准抽取（专用 pass，治单次抽取"只挑子集"的非确定性）。
CRITERIA_EXHAUSTIVE_PROMPT = (
    "你是控制论文复现专家。从下面的论文中，找出所有**可用仿真代码定量验证**的声称结果。\n"
    "每条给出：metric（英文蛇形指标名）、description（命题描述）、"
    "relation（approx_zero/approx/less_than/greater_than/equals/converges/decreasing/stable/qualitative）、"
    "expected（期望数值，可null）、tolerance（容差，可null）、evidence_ref（段落锚点）、confidence（0~1）。\n\n"
    "【典型可验证命题】：稳态频率/电压误差、功率分配误差、settling时间、超调量、"
    "稳定裕度临界值（如'延迟小于τ_max时稳定'）、鲁棒性指标等。\n\n"
    "示例输出格式：\n"
    '{"criteria": [{"metric": "freq_error_final", "description": "所有节点频率误差稳态收敛到零", '
    '"relation": "approx_zero", "expected": 0.0, "tolerance": null, '
    '"evidence_ref": "section_3.block_2", "confidence": 0.9}]}\n\n'
    "尽量多找，找不确定的可以把confidence设低（0.5以下）。不必穷尽，有多少写多少。只输出JSON。"
)

# 归并去重：把多次采样的候选合并成稳定、全覆盖、不重复的清单。
CRITERIA_CONSOLIDATE_PROMPT = (
    "以下是对同一篇论文多次抽取得到的候选验收标准（可能重复、命名不一致、粒度不同）。"
    "请合并语义等价项、统一 metric 命名(英文蛇形)、去重，输出一份**完整且不重复**的清单。"
    "保留所有语义不同的命题不要丢失覆盖；同义项合并为一条并取更明确的 description/expected/relation。只输出 JSON。"
)


# paper_to_prompt_text 函数，将 ParsedPaper 渲染为带锚点的可读文本供 LLM 抽取。
def paper_to_prompt_text(paper: ParsedPaper, max_chars: int = 48000) -> str:
    lines: list[str] = [f"# {paper.title or paper.paper_id}", f"(paper_id: {paper.paper_id})", ""]
    for sec in paper.sections:
        lines.append(f"## [{sec.section_id}] {sec.heading}")
        for block in sec.blocks:
            ref = block.evidence_ref or f"{sec.section_id}.{block.block_id}"
            if block.type == "equation":
                lines.append(f"[{ref}] (equation) {block.latex or block.text}")
            elif block.type == "table":
                lines.append(f"[{ref}] (table) {block.caption or ''} {block.html or ''}")
            elif block.type == "image":
                lines.append(f"[{ref}] (figure) {block.caption or ''}")
            else:
                lines.append(f"[{ref}] {block.text}")
        lines.append("")
    text = "\n".join(lines)
    return text[:max_chars]


# LlmKnowledgeExtractor 类，LLM 知识抽取器。
class LlmKnowledgeExtractor:
    # __init__ 方法，注入 LLM 客户端。
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    # extract 函数，抽取并映射为严格 schema 的四类知识。
    # criteria_samples>=2 时启用穷尽多采样+归并去重（治验收标准非确定性）；<=1 用主 pass 结果（快）。
    def extract(
        self, paper: ParsedPaper, criteria_samples: int = 1
    ) -> tuple[list[Equation], list[Controller], list[Parameter], list[AcceptanceCriterion]]:
        text = paper_to_prompt_text(paper)
        out = self.llm.structured(
            [system(SYSTEM_PROMPT), user(text)], KnowledgeExtraction, role="extractor"
        )
        eqs, ctrls, params, main_criteria = self._map(paper.paper_id, out)
        if criteria_samples <= 1:
            criteria = main_criteria
        else:
            sampled = self.extract_criteria(paper.paper_id, text, samples=criteria_samples)
            # 穷尽采样失败（模型未响应 exhaustive prompt）时 fallback 到主抽取结果
            criteria = sampled if sampled else main_criteria
        return eqs, ctrls, params, criteria

    # extract_criteria 函数，穷尽多采样 + LLM 归并去重，产出稳定全覆盖的验收标准。
    def extract_criteria(self, paper_id: str, text: str, samples: int = 3) -> list[AcceptanceCriterion]:
        candidates: list[_CritOut] = []
        for _ in range(max(1, samples)):
            out = self.llm.structured(
                [system(CRITERIA_EXHAUSTIVE_PROMPT), user(text)], _CriteriaOnly, role="extractor"
            )
            candidates.extend(out.criteria)
        if not candidates:
            return []
        merged = candidates
        if samples > 1 and len(candidates) > 1:
            payload = json.dumps([c.model_dump() for c in candidates], ensure_ascii=False)
            try:
                cons = self.llm.structured(
                    [system(CRITERIA_CONSOLIDATE_PROMPT), user(payload)], _CriteriaOnly, role="extractor"
                )
                if cons.criteria:
                    merged = cons.criteria
            except Exception:
                merged = candidates  # 归并失败则退回并集
        # 确定性去重（按 metric 名，防归并遗漏）+ 映射严格 schema
        result: list[AcceptanceCriterion] = []
        seen: set[str] = set()
        for c in merged:
            key = c.metric.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(AcceptanceCriterion(
                criterion_id=f"crit_{paper_id}_{len(result)}", paper_id=paper_id,
                metric=c.metric, description=c.description or c.metric,
                relation=c.relation, expected=c.expected, tolerance=c.tolerance,
                evidence_ref=c.evidence_ref or "unknown", confidence=c.confidence,
            ))
        return result

    # _map 函数，为中间结构补 id/paper_id，转为严格 schema。
    @staticmethod
    def _map(paper_id: str, out: KnowledgeExtraction) -> tuple[list[Equation], list[Controller], list[Parameter], list[AcceptanceCriterion]]:
        equations = [
            Equation(
                equation_id=f"eq_{paper_id}_{i}", paper_id=paper_id,
                latex=e.latex, normalized_latex=e.normalized_latex or e.latex,
                category=e.category, symbols=e.symbols, assumptions=e.assumptions,
                evidence_ref=e.evidence_ref or "unknown", confidence=e.confidence,
            )
            for i, e in enumerate(out.equations)
        ]
        controllers = [
            Controller(
                controller_id=f"ctrl_{paper_id}_{i}", paper_id=paper_id,
                type=c.type, architecture=c.architecture,
                input_signals=c.input_signals, output_signals=c.output_signals,
                implementation_notes=c.implementation_notes,
                evidence_ref=c.evidence_ref or "unknown", confidence=c.confidence,
            )
            for i, c in enumerate(out.controllers)
        ]
        parameters = [
            Parameter(
                parameter_id=f"param_{paper_id}_{i}", paper_id=paper_id,
                symbol=p.symbol, name=p.name or p.symbol, value=p.value, unit=p.unit,
                context=p.context, belongs_to=p.belongs_to,
                evidence_ref=p.evidence_ref or "unknown", confidence=p.confidence,
            )
            for i, p in enumerate(out.parameters)
        ]
        criteria = [
            AcceptanceCriterion(
                criterion_id=f"crit_{paper_id}_{i}", paper_id=paper_id,
                metric=c.metric, description=c.description or c.metric,
                relation=c.relation, expected=c.expected, tolerance=c.tolerance,
                evidence_ref=c.evidence_ref or "unknown", confidence=c.confidence,
            )
            for i, c in enumerate(out.criteria)
        ]
        return equations, controllers, parameters, criteria
