# 定义公式、控制器、参数和合并知识的结构化数据模型。
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# EvidenceMixin 类，封装该模块中的相关状态与行为。
class EvidenceMixin(BaseModel):
    evidence_ref: str
    confidence: float = Field(ge=0.0, le=1.0)


# Equation 类，封装该模块中的相关状态与行为。
class Equation(EvidenceMixin):
    equation_id: str
    paper_id: str
    latex: str
    normalized_latex: str
    category: Literal["dynamics", "controller", "lyapunov", "constraint", "cost_function", "other"]
    symbols: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


# Controller 类，封装该模块中的相关状态与行为。
class Controller(EvidenceMixin):
    controller_id: str
    paper_id: str
    type: Literal["PID", "MPC", "sliding_mode", "backstepping", "adaptive", "robust", "other"]
    architecture: str
    input_signals: list[str] = Field(default_factory=list)
    output_signals: list[str] = Field(default_factory=list)
    related_equation_ids: list[str] = Field(default_factory=list)
    related_parameter_ids: list[str] = Field(default_factory=list)
    implementation_notes: str = ""


# Parameter 类，封装该模块中的相关状态与行为。
class Parameter(EvidenceMixin):
    parameter_id: str
    paper_id: str
    symbol: str
    name: str
    value: str | float | None = None
    unit: str | None = None
    context: str
    belongs_to: Literal["plant", "controller", "simulation", "noise", "initial_condition", "other"]


# AcceptanceCriterion 类，论文声称的可验证结果（复现的基准真值）。
class AcceptanceCriterion(EvidenceMixin):
    criterion_id: str
    paper_id: str
    metric: str                 # 机读指标名，须与代码 results.json 的键一致
    description: str            # 该命题的自然语言描述
    relation: Literal[
        "approx_zero", "approx", "less_than", "greater_than",
        "equals", "converges", "decreasing", "stable", "qualitative",
    ] = "qualitative"
    expected: float | str | bool | None = None
    tolerance: float | None = None


# MergedKnowledge 类，封装该模块中的相关状态与行为。
class MergedKnowledge(BaseModel):
    paper_id: str
    equations: list[Equation] = Field(default_factory=list)
    controllers: list[Controller] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    needs_review: list[dict[str, str]] = Field(default_factory=list)
