"""비식별 처리 계층.

원문은 절대 덮어쓰지 않는다. 처리본을 새로 만들고, 어떤 스팬을 어떻게
바꿨는지 별도 감사 로그로 남긴다. 가명처리는 동일 원본이 항상 동일
가명으로 매핑되도록 HMAC 기반 결정적 방식을 쓴다. 문서 간 연결성을
유지해야 분석 목적의 활용이 가능하기 때문이다.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from enum import Enum

from .types import Entity, EntityType


class Strategy(str, Enum):
    MASK = "전체마스킹"
    PARTIAL = "부분마스킹"
    PSEUDONYM = "가명처리"
    HASH = "해시치환"
    REMOVE = "삭제"
    KEEP = "유지"


#: 유형별 기본 처리 정책. 프로젝트 요건에 맞춰 설정 파일로 분리 가능.
DEFAULT_POLICY: dict[EntityType, Strategy] = {
    EntityType.RRN: Strategy.MASK,
    EntityType.FRN: Strategy.MASK,
    EntityType.PASSPORT: Strategy.MASK,
    EntityType.DRIVER: Strategy.MASK,
    EntityType.CARD: Strategy.MASK,
    EntityType.CREDENTIAL: Strategy.REMOVE,
    EntityType.ACCOUNT: Strategy.PARTIAL,
    EntityType.BRN: Strategy.PARTIAL,
    EntityType.CRN: Strategy.PARTIAL,
    EntityType.PHONE: Strategy.PARTIAL,
    EntityType.EMAIL: Strategy.PARTIAL,
    EntityType.ZIPCODE: Strategy.PARTIAL,
    EntityType.PLATE: Strategy.PARTIAL,
    EntityType.IP: Strategy.PARTIAL,
    EntityType.BIRTH: Strategy.PARTIAL,
    EntityType.PERSON: Strategy.PSEUDONYM,
    EntityType.ADDRESS: Strategy.PARTIAL,
    EntityType.ORG: Strategy.KEEP,
}

_PSEUDO_PREFIX: dict[EntityType, str] = {
    EntityType.PERSON: "대상자",
    EntityType.ADDRESS: "주소",
    EntityType.ORG: "기관",
}
_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class Replacement:
    start: int
    end: int
    original: str
    replaced: str
    etype: EntityType
    strategy: Strategy


@dataclass
class MaskResult:
    text: str
    replacements: list[Replacement] = field(default_factory=list)
    #: 가명 ↔ 원본 매핑. 별도 보관·접근통제 대상(재식별 키).
    pseudonym_map: dict[str, str] = field(default_factory=dict)


class Masker:
    def __init__(self, secret: str = "capstone-default-salt",
                 policy: dict[EntityType, Strategy] | None = None) -> None:
        self._key = secret.encode("utf-8")
        self.policy = {**DEFAULT_POLICY, **(policy or {})}
        self._assigned: dict[tuple[EntityType, str], str] = {}
        self._counter: dict[EntityType, int] = {}

    # ------------------------------------------------------------------
    def _pseudonym(self, etype: EntityType, value: str) -> str:
        key = (etype, value.strip())
        if key in self._assigned:
            return self._assigned[key]
        digest = hmac.new(self._key, f"{etype.value}:{value}".encode(),
                          hashlib.sha256).hexdigest()
        idx = self._counter.get(etype, 0)
        self._counter[etype] = idx + 1
        label = _ALPHA[idx % 26] + (str(idx // 26) if idx >= 26 else "")
        alias = f"{_PSEUDO_PREFIX.get(etype, '개체')}{label}"
        self._assigned[key] = alias
        # digest 는 재식별 매핑 무결성 검증용으로 보관한다.
        self._assigned[(etype, f"__digest__{alias}")] = digest[:16]
        return alias

    @staticmethod
    def _mask_all(value: str) -> str:
        return re.sub(r"[^\s\-.@]", "*", value)

    def _partial(self, etype: EntityType, value: str) -> str:
        if etype is EntityType.PHONE:
            d = re.sub(r"\D", "", value)
            if len(d) >= 10:
                return f"{d[:3]}-{'*' * (len(d) - 7)}-{d[-4:]}"
            return self._mask_all(value)

        if etype is EntityType.EMAIL:
            local, _, domain = value.partition("@")
            head = local[:2] if len(local) > 2 else local[:1]
            return f"{head}{'*' * max(len(local) - len(head), 1)}@{domain}"

        if etype is EntityType.ACCOUNT:
            d = re.sub(r"\D", "", value)
            return f"{d[:3]}{'*' * max(len(d) - 6, 1)}{d[-3:]}"

        if etype in (EntityType.BRN, EntityType.CRN):
            d = re.sub(r"\D", "", value)
            return f"{d[:3]}-**-{'*' * (len(d) - 5)}"

        if etype is EntityType.BIRTH:
            m = re.match(r"((?:19|20)\d{2})", value)
            return f"{m.group(1)}-**-**" if m else self._mask_all(value)

        if etype is EntityType.ADDRESS:
            # 시/군/구 단위까지만 남기고 이하 상세주소는 가린다.
            m = re.match(r"(.*?(?:시|군|구))(?=\s|$)", value)
            return f"{m.group(1)} ***" if m else self._mask_all(value)

        if etype is EntityType.IP:
            parts = value.split(".")
            return ".".join(parts[:2] + ["*", "*"]) if len(parts) == 4 \
                else self._mask_all(value)

        if etype is EntityType.ZIPCODE:
            return f"{value[:2]}***"

        if etype is EntityType.PLATE:
            return re.sub(r"\d{4}$", "****", value)

        return self._mask_all(value)

    def _hash(self, value: str) -> str:
        digest = hmac.new(self._key, value.encode(), hashlib.sha256).hexdigest()
        return f"<HASH:{digest[:12]}>"

    # ------------------------------------------------------------------
    def apply(self, text: str, entities: list[Entity]) -> MaskResult:
        """엔티티 목록을 반영한 처리본을 생성한다.

        오프셋이 밀리지 않도록 뒤에서 앞 순서로 치환한다.
        """
        result = MaskResult(text=text)
        for e in sorted(entities, key=lambda x: x.start, reverse=True):
            strategy = self.policy.get(e.etype, Strategy.MASK)
            if strategy is Strategy.KEEP:
                continue

            if strategy is Strategy.MASK:
                new = self._mask_all(e.text)
            elif strategy is Strategy.PARTIAL:
                new = self._partial(e.etype, e.text)
            elif strategy is Strategy.PSEUDONYM:
                new = self._pseudonym(e.etype, e.text)
                result.pseudonym_map[new] = e.text
            elif strategy is Strategy.HASH:
                new = self._hash(e.text)
            else:  # REMOVE
                new = f"[{e.etype.value} 삭제됨]"

            result.text = result.text[:e.start] + new + result.text[e.end:]
            result.replacements.append(Replacement(
                start=e.start, end=e.end, original=e.text,
                replaced=new, etype=e.etype, strategy=strategy,
            ))

        result.replacements.reverse()
        return result
