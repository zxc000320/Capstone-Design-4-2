"""엔진 A : 정형 개인정보 탐지 (패턴 + 검증).

형식이 고정된 정보를 담당한다. 정규식으로 후보를 넓게 잡은 뒤
validators 모듈로 좁히는 2단 구조이며, 검증 통과 여부에 따라
신뢰도를 크게 벌려 놓아 융합 단계에서 자동 처리 대상과
사람 검토 대상이 자연스럽게 갈리도록 설계했다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .types import Entity, EntityType
from .validators import VALIDATORS, frn_legacy_checksum


@dataclass(frozen=True)
class Rule:
    name: str
    etype: EntityType
    pattern: re.Pattern
    base: float          # 검증 미적용 시 기본 신뢰도
    validated: float     # 검증 통과 시 신뢰도
    validator: str | None = None
    require_validation: bool = False  # 검증 실패 시 탐지 자체를 버릴지
    cues: tuple[str, ...] = ()        # 선행 문맥 단서(있으면 신뢰도 가산)
    cue_bonus: float = 0.35


# 자리 구분자로 하이픈, 점, 공백, 무구분을 모두 허용한다.
_SEP = r"[-.\s]?"

RULES: tuple[Rule, ...] = (
    Rule("주민등록번호", EntityType.RRN,
         re.compile(rf"(?<![0-9])\d{{6}}{_SEP}[1-4]\d{{6}}(?![0-9])"),
         base=0.55, validated=0.99, validator="RRN"),

    Rule("외국인등록번호", EntityType.FRN,
         re.compile(rf"(?<![0-9])\d{{6}}{_SEP}[5-8]\d{{6}}(?![0-9])"),
         base=0.50, validated=0.92, validator="FRN"),

    Rule("사업자등록번호", EntityType.BRN,
         re.compile(r"(?<![0-9])\d{3}-\d{2}-\d{5}(?![0-9])"),
         base=0.60, validated=0.95, validator="BRN"),

    Rule("법인등록번호", EntityType.CRN,
         re.compile(r"(?<![0-9])\d{6}-\d{7}(?![0-9])"),
         base=0.35, validated=0.90, validator="CRN",
         require_validation=True),

    Rule("신용카드번호", EntityType.CARD,
         re.compile(rf"(?<![0-9])(?:\d{{4}}{_SEP}){{3}}\d{{4}}(?![0-9])"),
         base=0.30, validated=0.96, validator="CARD",
         require_validation=True),

    Rule("계좌번호", EntityType.ACCOUNT,
         re.compile(r"(?<![0-9])\d{2,6}-\d{2,6}-\d{2,8}(?![0-9-])"),
         base=0.45, validated=0.45,
         cues=("계좌", "예금주", "입금", "환불", "송금", "은행")),

    Rule("휴대전화번호", EntityType.PHONE,
         re.compile(rf"(?<![0-9])01[016789]{_SEP}\d{{3,4}}{_SEP}\d{{4}}(?![0-9])"),
         base=0.70, validated=0.94, validator="PHONE"),

    Rule("유선전화번호", EntityType.PHONE,
         re.compile(r"(?<![0-9])0(?:2|[3-6][1-5])-\d{3,4}-\d{4}(?![0-9])"),
         base=0.65, validated=0.90, validator="PHONE"),

    Rule("이메일", EntityType.EMAIL,
         re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
         base=0.93, validated=0.93),

    Rule("여권번호", EntityType.PASSPORT,
         re.compile(r"(?<![A-Za-z0-9])[MSRODmsrod]\d{8}(?![A-Za-z0-9])"),
         base=0.65, validated=0.65,
         cues=("여권", "passport", "출입국")),

    Rule("운전면허번호", EntityType.DRIVER,
         re.compile(r"(?<![0-9])\d{2}-\d{2}-\d{6}-\d{2}(?![0-9])"),
         base=0.85, validated=0.85),

    Rule("우편번호", EntityType.ZIPCODE,
         re.compile(r"(?<![0-9])\d{5}(?![0-9])"),
         base=0.20, validated=0.20,
         cues=("우편번호", "우편", "zip", "ZIP")),

    Rule("차량번호", EntityType.PLATE,
         re.compile(r"(?<![0-9])\d{2,3}[가-힣]\s?\d{4}(?![0-9])"),
         base=0.72, validated=0.72,
         cues=("차량", "차번호", "번호판", "주차")),

    Rule("IP주소", EntityType.IP,
         re.compile(r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])"),
         base=0.40, validated=0.75, validator="IP",
         cues=("IP", "아이피", "서버", "접속", "호스트")),

    # --- 기술 자격증명 (소스코드/설정파일 대상) ---
    Rule("AWS 액세스키", EntityType.CREDENTIAL,
         re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
         base=0.97, validated=0.97),

    Rule("GitHub 토큰", EntityType.CREDENTIAL,
         re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
         base=0.97, validated=0.97),

    Rule("개인키 블록", EntityType.CREDENTIAL,
         re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
         base=0.99, validated=0.99),

    Rule("JWT", EntityType.CREDENTIAL,
         re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
         base=0.90, validated=0.90),

    Rule("하드코딩 시크릿", EntityType.CREDENTIAL,
         re.compile(r"""(?i)(?:api[_-]?key|secret|passwd|password|token)"""
                    r"""\s*[:=]\s*["']([^"']{8,})["']"""),
         base=0.80, validated=0.80),
)


# ----------------------------------------------------------------------
# 더미/예시 데이터 억제 목록 (오탐의 상당 비중을 차지)
# ----------------------------------------------------------------------
_DUMMY_PATTERNS = (
    re.compile(r"^0{3,}"),                       # 000-0000-0000
    re.compile(r"^(\d)\1{5,}"),                  # 111111-1111111
    re.compile(r"^(1234|0000|9999)"),
    re.compile(r"(?i)(example|test|sample|dummy|your)[._-]?"),
)
_DUMMY_LITERALS = {
    "000000-0000000", "123456-1234567", "010-0000-0000",
    "010-1234-5678", "0.0.0.0", "127.0.0.1", "255.255.255.255",
}


def _is_dummy(text: str) -> bool:
    stripped = text.strip()
    if stripped in _DUMMY_LITERALS:
        return True
    compact = stripped.replace("-", "").replace(" ", "").replace(".", "")
    return any(p.search(stripped) or p.search(compact) for p in _DUMMY_PATTERNS)


# ----------------------------------------------------------------------
def detect(text: str) -> list[Entity]:
    """정형 개인정보를 탐지해 Entity 목록을 반환한다."""
    found: list[Entity] = []

    for rule in RULES:
        for m in rule.pattern.finditer(text):
            # 캡처 그룹이 있는 규칙(하드코딩 시크릿)은 값 부분만 취한다.
            span = m.span(1) if rule.pattern.groups else m.span(0)
            raw = text[span[0]:span[1]]

            evidence = [f"규칙:{rule.name}"]
            validated = False
            conf = rule.base

            fn = VALIDATORS.get(rule.validator) if rule.validator else None
            if fn is not None:
                if fn(raw):
                    validated = True
                    conf = rule.validated
                    evidence.append("검증:통과")
                    if rule.etype is EntityType.FRN and frn_legacy_checksum(raw):
                        evidence.append("검증:구규칙 검사숫자 일치")
                elif rule.require_validation:
                    continue  # 검증 실패 시 후보에서 제외
                else:
                    conf = max(0.22, rule.base - 0.32)
                    evidence.append("검증:실패(신뢰도 감점)")

            if rule.cues:
                left = text[max(0, span[0] - 18):span[0]]
                if any(cue in left for cue in rule.cues):
                    conf = min(conf + rule.cue_bonus, 0.96)
                    evidence.append("문맥:선행 라벨 일치")

            if _is_dummy(raw):
                conf = min(conf, 0.12)
                evidence.append("억제:더미/예시 데이터 추정")

            found.append(Entity(
                start=span[0], end=span[1], text=raw, etype=rule.etype,
                confidence=conf, engines={"regex"},
                validated=validated, evidence=evidence,
            ))

    return found
