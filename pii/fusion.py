"""융합 계층 : 두 엔진의 탐지 결과를 하나의 판정으로 수렴시킨다.

핵심 아이디어는 '개인정보는 홀로 존재하지 않는다'는 관찰이다.
성명 옆에는 연락처가, 주소 옆에는 우편번호가, 기관명 옆에는
사업자등록번호가 붙어 있을 확률이 높다. 정형 엔진의 확실한 탐지를
비정형 엔진의 불확실한 탐지에 대한 방증으로 쓰면, NER 단독으로는
애매했던 후보의 신뢰도를 근거 있게 끌어올릴 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import Entity, EntityType


class Decision(str, Enum):
    """엔티티별 최종 처리 판정."""

    AUTO = "자동처리"      # 신뢰도 충분 → 즉시 비식별 처리
    REVIEW = "검토필요"    # 사람 확인 후 적용
    DISCARD = "탐지제외"   # 오탐으로 판단, 처리 대상에서 제거


#: (대상 유형, 방증 유형, 허용 거리, 가산점)
#: 방증 엔티티가 지정 거리 안에 있으면 대상 엔티티 신뢰도를 올린다.
CORROBORATION_RULES: tuple[tuple[EntityType, EntityType, int, float], ...] = (
    (EntityType.PERSON, EntityType.RRN, 40, 0.30),
    (EntityType.PERSON, EntityType.PHONE, 45, 0.20),
    (EntityType.PERSON, EntityType.EMAIL, 45, 0.16),
    (EntityType.PERSON, EntityType.BIRTH, 35, 0.14),
    (EntityType.PERSON, EntityType.ACCOUNT, 40, 0.16),
    (EntityType.ADDRESS, EntityType.ZIPCODE, 25, 0.22),
    (EntityType.ADDRESS, EntityType.PHONE, 50, 0.10),
    (EntityType.BIRTH, EntityType.PERSON, 35, 0.16),
    (EntityType.ORG, EntityType.BRN, 50, 0.18),
    (EntityType.ACCOUNT, EntityType.PERSON, 30, 0.18),
    (EntityType.ZIPCODE, EntityType.ADDRESS, 25, 0.30),
)

#: 스팬 충돌 시 유형 우선순위(클수록 우선). 동일 위치를 두 규칙이 다르게
#: 해석했을 때 어느 쪽을 남길지 결정한다.
TYPE_PRIORITY: dict[EntityType, int] = {
    EntityType.RRN: 100, EntityType.FRN: 98, EntityType.CARD: 95,
    EntityType.PASSPORT: 92, EntityType.DRIVER: 92, EntityType.CREDENTIAL: 90,
    EntityType.BRN: 80, EntityType.CRN: 78, EntityType.PHONE: 70,
    EntityType.ACCOUNT: 60, EntityType.EMAIL: 75, EntityType.ADDRESS: 55,
    EntityType.BIRTH: 50, EntityType.PERSON: 45, EntityType.PLATE: 40,
    EntityType.ORG: 30, EntityType.IP: 25, EntityType.ZIPCODE: 10,
}


#: 이 값 미만의 자체 신뢰도는 '약한 후보'로 보고 방증 상한을 제한한다.
WEAK_BASE = 0.55

#: 자체 근거가 이 값에 못 미치는 후보는 웬만한 방증으로는 보강하지 않는다.
CORROB_MIN_FOR_WEAK = 0.50

#: 위 문턱을 예외적으로 넘길 수 있는 방증의 민감도(고유식별정보 수준).
STRONG_WITNESS_SENS = 3

#: 문서 단위 일관성 전파 대상 유형.
PROPAGATE_TYPES = (EntityType.PERSON, EntityType.ADDRESS, EntityType.ORG)


@dataclass
class FusionConfig:
    auto_threshold: float = 0.85
    review_threshold: float = 0.45
    #: 고유식별정보는 미탐 비용이 크므로 검토 문턱을 낮춘다.
    critical_review_threshold: float = 0.20


# ----------------------------------------------------------------------
def _distance(a: Entity, b: Entity) -> int:
    """두 엔티티 사이 문자 거리(중첩이면 0)."""
    if a.overlaps(b):
        return 0
    return b.start - a.end if b.start >= a.end else a.start - b.end


def corroborate(entities: list[Entity]) -> list[Entity]:
    """근접 방증 엔티티를 찾아 신뢰도를 상호 보강한다."""
    for target in entities:
        for t_type, w_type, max_dist, bonus in CORROBORATION_RULES:
            if target.etype is not t_type:
                continue
            for witness in entities:
                if witness is target or witness.etype is not w_type:
                    continue
                if witness.confidence < 0.60:
                    continue  # 불확실한 방증은 근거로 쓰지 않는다
                # 근거가 약한 후보는 민감도가 높고 형식 검증까지 통과한
                # 방증(주민등록번호 등)에 한해서만 보강한다. 전화번호가
                # 옆에 있다는 사실만으로 은행명이 사람 이름이 되어서는 안 된다.
                if (target.confidence < CORROB_MIN_FOR_WEAK
                        and not (witness.validated
                                 and witness.sensitivity >= STRONG_WITNESS_SENS)):
                    continue
                if _distance(target, witness) <= max_dist:
                    gain = bonus * (1.0 if witness.validated else 0.7)
                    # 방증은 '애매한 후보를 확신으로 바꾸는' 장치가 아니다.
                    # 자체 근거가 약한 후보는 보강을 받아도 검토 등급을
                    # 넘지 못하도록 상한을 따로 둔다.
                    cap = 0.98 if target.confidence >= WEAK_BASE else 0.80
                    target.confidence = min(target.confidence + gain, cap)
                    target.engines.add("cross")
                    target.evidence.append(
                        f"교차:{w_type.value} 근접(+{gain:.2f})"
                    )
                    break
    return entities


def propagate_document_level(entities: list[Entity]) -> list[Entity]:
    """문서 내 동일 표현의 판정을 일관되게 맞춘다.

    같은 문서에서 '박서준'이 한 번은 라벨 옆이라 확정되고 다른 한 번은
    문맥 단서가 없어 애매해지면, 처리본에 원문이 그대로 남는 누락이
    발생한다. 한 번 확정된 표현은 같은 문서 전체에서 동일하게 본다.
    """
    anchors: dict[tuple, float] = {}
    for e in entities:
        if e.etype in PROPAGATE_TYPES and e.confidence >= 0.85:
            key = (e.etype, e.text.strip())
            anchors[key] = max(anchors.get(key, 0.0), e.confidence)

    for e in entities:
        key = (e.etype, e.text.strip())
        if key in anchors and e.confidence < anchors[key]:
            e.confidence = max(e.confidence, anchors[key] - 0.02)
            e.engines.add("doc")
            e.evidence.append("전파:문서 내 동일 표현 확정")
    return entities


def resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """중첩 스팬을 제거해 마스킹 가능한 비중첩 집합으로 정리한다."""
    def rank(e: Entity) -> tuple:
        return (
            1 if e.validated else 0,
            TYPE_PRIORITY.get(e.etype, 0),
            round(e.confidence, 3),
            e.length,
        )

    ordered = sorted(entities, key=rank, reverse=True)
    kept: list[Entity] = []
    for cand in ordered:
        if any(cand.overlaps(k) for k in kept):
            continue
        kept.append(cand)
    return sorted(kept, key=lambda e: e.start)


def decide(entity: Entity, cfg: FusionConfig) -> Decision:
    """신뢰도와 민감도를 함께 보고 처리 판정을 내린다."""
    if entity.confidence >= cfg.auto_threshold:
        return Decision.AUTO
    floor = (cfg.critical_review_threshold if entity.sensitivity >= 3
             else cfg.review_threshold)
    return Decision.REVIEW if entity.confidence >= floor else Decision.DISCARD


def fuse(regex_hits: list[Entity], ner_hits: list[Entity],
         cfg: FusionConfig | None = None) -> tuple[list[Entity], dict[int, Decision]]:
    """전체 융합 절차를 수행한다.

    Returns:
        (확정 엔티티 목록, 엔티티 id → 판정 매핑)
    """
    cfg = cfg or FusionConfig()
    pool = corroborate(regex_hits + ner_hits)
    pool = propagate_document_level(pool)
    final = resolve_overlaps(pool)
    decisions = {id(e): decide(e, cfg) for e in final}
    return final, decisions
