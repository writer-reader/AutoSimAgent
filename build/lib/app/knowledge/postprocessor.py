# 合并三类知识并标记低置信度待审阅项。
from __future__ import annotations

import json
from pathlib import Path

from app.knowledge.schemas import AcceptanceCriterion, Controller, Equation, MergedKnowledge, Parameter


# merge_knowledge 函数，封装该模块的一段可复用业务逻辑。
def merge_knowledge(
    paper_id: str,
    equations: list[Equation],
    controllers: list[Controller],
    parameters: list[Parameter],
    confidence_threshold: float = 0.75,
    criteria: list[AcceptanceCriterion] | None = None,
) -> MergedKnowledge:
    criteria = criteria or []
    needs_review: list[dict[str, str]] = []
    for item in [*equations, *controllers, *parameters, *criteria]:
        if item.confidence < confidence_threshold:
            needs_review.append({
                "id": getattr(item, "equation_id", getattr(item, "controller_id",
                     getattr(item, "parameter_id", getattr(item, "criterion_id", "")))),
                "reason": "low_confidence",
            })
    return MergedKnowledge(
        paper_id=paper_id, equations=equations, controllers=controllers,
        parameters=parameters, criteria=criteria, needs_review=needs_review,
    )


# save_merged_knowledge 函数，保存业务状态或产物到指定位置。
def save_merged_knowledge(knowledge: MergedKnowledge, output_dir: str | Path = "data/knowledge/merged") -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    output_path = path / f"{knowledge.paper_id}.json"
    output_path.write_text(json.dumps(knowledge.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_path)
