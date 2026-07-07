# 编排 LLM 知识抽取与合并保存流程。
from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.parser import ParsedPaper
from app.knowledge.llm_extractor import LlmKnowledgeExtractor
from app.knowledge.postprocessor import merge_knowledge, save_merged_knowledge
from app.llm.client import LLMClient


@dataclass
# KnowledgeBuildResult 类，封装该模块中的相关状态与行为。
class KnowledgeBuildResult:
    paper_id: str
    equation_count: int
    controller_count: int
    parameter_count: int
    criteria_count: int
    merged_path: str
    needs_review_count: int
    warnings: list[str]


# KnowledgeService 类，封装该模块中的相关状态与行为。
class KnowledgeService:
    # __init__ 方法，注入 LLM 客户端、置信度阈值与验收标准采样次数。
    def __init__(self, llm: LLMClient, confidence_threshold: float = 0.75, criteria_samples: int = 3) -> None:
        self.extractor = LlmKnowledgeExtractor(llm)
        self.confidence_threshold = confidence_threshold
        self.criteria_samples = criteria_samples

    # build 函数，抽取四类知识、合并并落盘。
    def build(self, paper: ParsedPaper) -> KnowledgeBuildResult:
        equations, controllers, parameters, criteria = self.extractor.extract(
            paper, criteria_samples=self.criteria_samples
        )
        merged = merge_knowledge(paper.paper_id, equations, controllers, parameters,
                                 self.confidence_threshold, criteria=criteria)
        merged_path = save_merged_knowledge(merged)
        return KnowledgeBuildResult(
            paper_id=paper.paper_id,
            equation_count=len(equations),
            controller_count=len(controllers),
            parameter_count=len(parameters),
            criteria_count=len(criteria),
            merged_path=merged_path,
            needs_review_count=len(merged.needs_review),
            warnings=[],
        )
