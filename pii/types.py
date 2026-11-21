"""공통 자료구조 정의.

탐지 엔진(정형/비정형)이 서로 다른 방식으로 동작하더라도
동일한 Entity 객체를 산출하도록 계약(contract)을 고정한다.
팀원 간 인터페이스 합의 지점이므로 변경 시 반드시 PR 리뷰를 거칠 것.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class EntityType(str, Enum):
    """탐지 대상 개인정보 유형."""

    # --- 고유식별정보 (개인정보보호법 제24조) ---
    RRN = "주민등록번호"
    FRN = "외국인등록번호"
    PASSPORT = "여권번호"
    DRIVER = "운전면허번호"

    # --- 금융/사업자 정보 ---
    CARD = "신용카드번호"
    ACCOUNT = "계좌번호"
    BRN = "사업자등록번호"
    CRN = "법인등록번호"

    # --- 연락처/식별 보조정보 ---
    PHONE = "전화번호"
    EMAIL = "이메일"
    ZIPCODE = "우편번호"
    PLATE = "차량번호"
    IP = "IP주소"

    # --- 기술 자격증명 ---
    CREDENTIAL = "인증정보"

    # --- 비정형(문맥 의존) 정보 ---
    PERSON = "성명"
    ADDRESS = "주소"
    ORG = "소속기관"
    BIRTH = "생년월일"


#: 유형별 민감도. 처리 정책(마스킹/가명처리/삭제) 결정과 위험도 점수 산정에 사용.
SENSITIVITY: dict[EntityType, int] = {
    EntityType.RRN: 3,
    EntityType.FRN: 3,
    EntityType.PASSPORT: 3,
    EntityType.DRIVER: 3,
    EntityType.CREDENTIAL: 3,
    EntityType.CARD: 3,
    EntityType.ACCOUNT: 2,
    EntityType.BRN: 1,
    EntityType.CRN: 1,
    EntityType.PHONE: 2,
    EntityType.EMAIL: 2,
    EntityType.BIRTH: 2,
    EntityType.ADDRESS: 2,
    EntityType.PERSON: 2,
    EntityType.PLATE: 1,
    EntityType.ZIPCODE: 1,
    EntityType.IP: 1,
    EntityType.ORG: 0,
}

#: 탐지 엔진 식별자.
Engine = Literal["regex", "ner_model", "ner_lexicon"]


@dataclass
class Entity:
    """탐지된 개인정보 1건.

    Attributes:
        start, end: 원문 기준 문자 오프셋(반열린 구간).
        text: 탐지된 원문 조각.
        etype: 개인정보 유형.
        confidence: 0.0~1.0 신뢰도. 융합 단계에서 재계산된다.
        engines: 이 스팬을 탐지한 엔진 집합. 2개 이상이면 교차 검증 성립.
        validated: 체크섬 등 형식 검증 통과 여부(정형 정보에 한함).
        evidence: 판정 근거 문자열 목록. 감사 로그와 오탐 분석에 사용.
    """

    start: int
    end: int
    text: str
    etype: EntityType
    confidence: float = 0.5
    engines: set[str] = field(default_factory=set)
    validated: bool = False
    evidence: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def sensitivity(self) -> int:
        return SENSITIVITY.get(self.etype, 0)

    @property
    def cross_verified(self) -> bool:
        """서로 다른 엔진 2개 이상이 동일 스팬을 지목했는지."""
        return len(self.engines) >= 2

    def overlaps(self, other: "Entity") -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "type": self.etype.value,
            "confidence": round(self.confidence, 3),
            "engines": sorted(self.engines),
            "validated": self.validated,
            "sensitivity": self.sensitivity,
            "evidence": self.evidence,
        }

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 편의용
        return (
            f"Entity({self.etype.value}, '{self.text}', "
            f"[{self.start}:{self.end}], conf={self.confidence:.2f}, "
            f"engines={sorted(self.engines)})"
        )
