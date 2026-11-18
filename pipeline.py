"""파이프라인 : 탐지 → 융합 → 판정 → 처리 → 리포트.

기본 동작은 '탐지 자동, 처리 반자동'이다. 신뢰도가 충분한 항목만
자동 처리하고 나머지는 검토 대기로 분류한다. 오탐으로 원문을 훼손하는
것 자체가 사고이므로, 전자동 모드는 명시적으로 켜야만 동작하게 두었다.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from . import regex_engine
from .fusion import Decision, FusionConfig, fuse
from .masking import MaskResult, Masker, Strategy
from .ner_engine import NerEngine
from .types import Entity, EntityType


@dataclass
class ScanReport:
    source: str
    entities: list[Entity] = field(default_factory=list)
    decisions: dict[int, Decision] = field(default_factory=dict)
    engine_info: dict = field(default_factory=dict)

    # --------------------------------------------------------------
    def by_decision(self, decision: Decision) -> list[Entity]:
        return [e for e in self.entities if self.decisions.get(id(e)) is decision]

    @property
    def auto(self) -> list[Entity]:
        return self.by_decision(Decision.AUTO)

    @property
    def review(self) -> list[Entity]:
        return self.by_decision(Decision.REVIEW)

    @property
    def discarded(self) -> list[Entity]:
        return self.by_decision(Decision.DISCARD)

    @property
    def actionable(self) -> list[Entity]:
        return self.auto + self.review

    @property
    def risk_score(self) -> int:
        """0~100 정수 위험도. 민감도 가중 합을 상한으로 정규화."""
        raw = sum((e.sensitivity + 1) * e.confidence for e in self.actionable)
        return int(min(raw / 0.3, 100))

    def type_counts(self) -> dict[str, int]:
        return dict(Counter(e.etype.value for e in self.actionable))

    # --------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "risk_score": self.risk_score,
            "summary": {
                "total": len(self.entities),
                "auto": len(self.auto),
                "review": len(self.review),
                "discarded": len(self.discarded),
                "by_type": self.type_counts(),
            },
            "engine": self.engine_info,
            "entities": [
                {**e.to_dict(), "decision": self.decisions[id(e)].value}
                for e in self.entities
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_markdown(self) -> str:
        lines = [
            f"## 개인정보 탐지 리포트 — `{self.source}`",
            "",
            f"- 위험도 점수: **{self.risk_score}** / 100",
            f"- 자동처리 {len(self.auto)}건 · 검토필요 {len(self.review)}건 "
            f"· 탐지제외 {len(self.discarded)}건",
            f"- NER 모델 백엔드: "
            f"{'활성' if self.engine_info.get('model_available') else '비활성(사전 기반 단독)'}",
            "",
            "| # | 유형 | 원문 | 위치 | 신뢰도 | 탐지엔진 | 판정 |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, e in enumerate(self.entities, 1):
            preview = e.text if len(e.text) <= 24 else e.text[:21] + "…"
            lines.append(
                f"| {i} | {e.etype.value} | `{preview}` | {e.start}–{e.end} "
                f"| {e.confidence:.2f} | {', '.join(sorted(e.engines))} "
                f"| {self.decisions[id(e)].value} |"
            )
        return "\n".join(lines)


# ======================================================================
class PiiPipeline:
    def __init__(self,
                 use_model: bool = True,
                 model_id: str | None = None,
                 fusion_config: FusionConfig | None = None,
                 policy: dict[EntityType, Strategy] | None = None,
                 secret: str = "capstone-default-salt") -> None:
        self.ner = NerEngine(use_model=use_model, model_id=model_id)
        self.cfg = fusion_config or FusionConfig()
        self.masker = Masker(secret=secret, policy=policy)

    # ------------------------------------------------------------------
    def scan(self, text: str, source: str = "input") -> ScanReport:
        """탐지만 수행한다. 원문은 변경하지 않는다."""
        regex_hits = regex_engine.detect(text)
        ner_hits = self.ner.detect(text)
        entities, decisions = fuse(regex_hits, ner_hits, self.cfg)
        return ScanReport(
            source=source,
            entities=entities,
            decisions=decisions,
            engine_info={
                "regex_hits": len(regex_hits),
                "ner_hits": len(ner_hits),
                "model_available": self.ner.model_available,
            },
        )

    def process(self, text: str, source: str = "input",
                include_review: bool = False) -> tuple[ScanReport, MaskResult]:
        """탐지 후 비식별 처리본을 생성한다.

        Args:
            include_review: True 면 검토필요 항목까지 함께 처리한다.
                            운영 환경에서는 검토자 승인 절차를 거친 뒤에만
                            True 로 호출할 것.
        """
        report = self.scan(text, source=source)
        targets = report.actionable if include_review else report.auto
        masked = self.masker.apply(text, targets)
        return report, masked
