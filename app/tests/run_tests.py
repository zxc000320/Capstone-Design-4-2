"""
테스트 (담당: 김진웅) — 실행:  python app/tests/run_tests.py

파이프라인·연결 코드·파일 입출력만 테스트한다.
팀원 모듈 자체의 탐지·마스킹 규칙은 각 담당자가 테스트한다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapters
from pipeline import merge_entities, validate_entities


def _seg(text, seg_id="line_1"):
    return [{"seg_id": seg_id, "text": text, "meta": {}}]


# ---------- 연결 코드 (adapters.py) ----------
def test_regex_output_converted_to_common_format():
    segs = _seg("주민번호: 990101-1234567")
    ents = adapters.detect_regex(segs)
    assert ents == [{"seg_id": "line_1", "start": 6, "end": 20, "type": "RRN",
                     "text": "990101-1234567", "source": "regex"}], ents
    validate_entities(ents, segs, "regex_detector")   # 공통 형식 검사 통과


def test_type_names_converted():
    types = {e["type"] for e in adapters.detect_regex(_seg("계좌 110-123-456789 카드 1234-5678-9012-3456"))}
    assert "ACCOUNT" in types and "CARD" in types
    assert "BANK_ACCOUNT" not in types and "CARD_NUMBER" not in types


def test_masking_called_with_module_format():
    segs = _seg("주민 990101-1234567, 계좌 110-123-456789")
    ents = merge_entities(adapters.detect_regex(segs), [])
    out = adapters.apply_masking(segs, ents)
    assert out[0]["text"] == "주민 990101-1******, 계좌 110-123-******", out
    assert out[0]["seg_id"] == "line_1"


def test_masking_skips_segments_without_entities():
    segs = _seg("개인정보 없음") + _seg("전화 010-1234-5678", "line_2")
    out = adapters.apply_masking(segs, merge_entities(adapters.detect_regex(segs), []))
    assert [s["text"] for s in out] == ["개인정보 없음", "전화 *************"]


# ---------- 결과 합치기 (pipeline.py) ----------
def test_merge_removes_overlap():
    # 같은 번호가 전화번호·계좌번호로 동시에 잡혀도 하나만 남음
    ents = merge_entities(adapters.detect_regex(_seg("연락처 010-1234-5678")), [])
    assert [e["type"] for e in ents] == ["PHONE"], ents


def test_merge_prefers_regex_for_structured():
    regex = [{"seg_id": "s", "start": 0, "end": 13, "type": "PHONE", "text": "x", "source": "regex"}]
    ner = [{"seg_id": "s", "start": 0, "end": 20, "type": "ADDRESS", "text": "x", "source": "ner"}]
    assert merge_entities(regex, ner) == regex


from test_fileio import *  # noqa: E402,F401,F403  파일 입출력·파이프라인 테스트


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  통과  {name}")
        except Exception as e:
            failed += 1
            print(f"  실패  {name}  {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)
