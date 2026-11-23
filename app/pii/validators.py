"""형식 검증 모듈 (1차 오탐 제거 계층).

정규식은 '형태가 비슷한 것'을 모두 잡아낸다. 제품 코드, 일련번호,
날짜 조합이 주민등록번호 형태로 보이는 경우가 실제로 빈번하다.
여기서 체크섬·날짜 유효성으로 걸러내면 오탐률이 크게 떨어진다.
"""

from __future__ import annotations

import datetime as _dt
import re

_DIGITS = re.compile(r"\D")


def _only_digits(value: str) -> str:
    return _DIGITS.sub("", value)


# ----------------------------------------------------------------------
# 주민등록번호 / 외국인등록번호
# ----------------------------------------------------------------------
_RRN_WEIGHTS = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)


def _valid_birth_part(d: str) -> bool:
    """앞 6자리가 실제 달력상 존재하는 날짜인지 확인."""
    yy, mm, dd = int(d[0:2]), int(d[2:4]), int(d[4:6])
    gender = int(d[6])
    century = {1: 1900, 2: 1900, 3: 2000, 4: 2000,
               5: 1900, 6: 1900, 7: 2000, 8: 2000,
               9: 1800, 0: 1800}.get(gender)
    if century is None:
        return False
    try:
        _dt.date(century + yy, mm, dd)
    except ValueError:
        return False
    return True


def validate_rrn(value: str) -> bool:
    """주민등록번호 검증: 길이 + 날짜 유효성 + 검사숫자."""
    d = _only_digits(value)
    if len(d) != 13:
        return False
    if not _valid_birth_part(d):
        return False
    total = sum(int(d[i]) * _RRN_WEIGHTS[i] for i in range(12))
    return (11 - total % 11) % 10 == int(d[12])


def validate_frn(value: str) -> bool:
    """외국인등록번호 검증.

    2020년 10월 이후 발급분은 검사숫자 규칙이 폐지되었으므로,
    구 규칙 통과 또는 성별코드(5~8) 형식 충족 중 하나만 만족해도
    '형식 유효'로 판정한다. 대신 신뢰도는 호출부에서 낮게 부여한다.
    """
    d = _only_digits(value)
    if len(d) != 13:
        return False
    if d[6] not in "5678":
        return False
    if not _valid_birth_part(d):
        return False
    total = sum(int(d[i]) * _RRN_WEIGHTS[i] for i in range(12))
    legacy = ((11 - total % 11) % 10 + 2) % 10 == int(d[12])
    return True if legacy else True  # 형식 충족만으로 통과(구규칙은 가점 요소)


def frn_legacy_checksum(value: str) -> bool:
    """구 외국인등록번호 검사숫자 통과 여부(신뢰도 가점용)."""
    d = _only_digits(value)
    if len(d) != 13:
        return False
    total = sum(int(d[i]) * _RRN_WEIGHTS[i] for i in range(12))
    return ((11 - total % 11) % 10 + 2) % 10 == int(d[12])


# ----------------------------------------------------------------------
# 사업자등록번호 / 법인등록번호
# ----------------------------------------------------------------------
_BRN_WEIGHTS = (1, 3, 7, 1, 3, 7, 1, 3, 5)


def validate_brn(value: str) -> bool:
    """사업자등록번호 10자리 검사숫자 검증."""
    d = _only_digits(value)
    if len(d) != 10:
        return False
    total = sum(int(d[i]) * _BRN_WEIGHTS[i] for i in range(9))
    total += (int(d[8]) * 5) // 10
    return (10 - total % 10) % 10 == int(d[9])


def validate_crn(value: str) -> bool:
    """법인등록번호 13자리 검사숫자 검증(가중치 1,2 교대)."""
    d = _only_digits(value)
    if len(d) != 13:
        return False
    total = sum(int(d[i]) * (1 if i % 2 == 0 else 2) for i in range(12))
    return (10 - total % 10) % 10 == int(d[12])


# ----------------------------------------------------------------------
# 신용카드 (Luhn)
# ----------------------------------------------------------------------
def validate_luhn(value: str) -> bool:
    """Luhn 알고리즘 기반 카드번호 검증."""
    d = _only_digits(value)
    if not 13 <= len(d) <= 19:
        return False
    total, parity = 0, len(d) % 2
    for idx, ch in enumerate(d):
        n = int(ch)
        if idx % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# ----------------------------------------------------------------------
# 기타
# ----------------------------------------------------------------------
def validate_phone(value: str) -> bool:
    """국내 전화번호 자릿수 및 국번 유효성 간이 검증."""
    d = _only_digits(value)
    if d.startswith("82"):
        d = "0" + d[2:]
    if len(d) not in (9, 10, 11):
        return False
    if d.startswith("01"):
        return len(d) in (10, 11) and d[1] == "1" and d[2] in "016789"
    return d.startswith("0")


def validate_ipv4(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 and (p == "0" or not p.startswith("0"))
                   for p in parts)
    except ValueError:
        return False


#: 유형별 검증 함수 레지스트리. regex_engine 에서 참조한다.
VALIDATORS = {
    "RRN": validate_rrn,
    "FRN": validate_frn,
    "BRN": validate_brn,
    "CRN": validate_crn,
    "CARD": validate_luhn,
    "PHONE": validate_phone,
    "IP": validate_ipv4,
}
