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


class _RecordMasking:
    """마스킹 모듈 대신 끼워서, 연결 코드가 무엇을 넘기는지 기록"""
    def __enter__(self):
        self.calls, self.original = [], adapters.masking.apply_masking
        def fake(text, results):
            self.calls.append((text, results))
            return "MASKED"
        adapters.masking.apply_masking = fake
        return self

    def __exit__(self, *a):
        adapters.masking.apply_masking = self.original


def test_masking_called_with_module_format():
    segs = _seg("주민 990101-1234567, 계좌 110-123-456789")
    ents = merge_entities(adapters.detect_regex(segs), [])
    with _RecordMasking() as rec:
        out = adapters.apply_masking(segs, ents)
    (text, results), = rec.calls
    assert text == segs[0]["text"]
    # 모듈이 쓰는 형식(value 키, 모듈 타입 이름)으로 넘겨야 함
    assert sorted(r["type"] for r in results) == ["BANK_ACCOUNT", "RRN"], results
    for r in results:
        assert r["value"] == text[r["start"]:r["end"]]
    assert out == [{**segs[0], "text": "MASKED"}]


def test_masking_skips_segments_without_entities():
    segs = _seg("개인정보 없음") + _seg("전화 010-1234-5678", "line_2")
    ents = merge_entities(adapters.detect_regex(segs), [])
    with _RecordMasking() as rec:
        out = adapters.apply_masking(segs, ents)
    assert [t for t, _ in rec.calls] == ["전화 010-1234-5678"]   # 탐지 없는 줄은 모듈을 부르지 않음
    assert [s["text"] for s in out] == ["개인정보 없음", "MASKED"]


def test_every_type_has_masking_rule():
    """파이프라인의 모든 타입이 마스킹 모듈의 규칙 이름으로 연결되는지
    (실패하면 마스킹 쪽 이름이 바뀐 것 → adapters.PIPELINE_TO_MASKING 수정)"""
    rules = set(adapters.masking.MASK_FUNCTIONS)
    missing = [t for t in ["RRN", "PHONE", "EMAIL", "ACCOUNT", "CARD", "IP_ADDRESS", "NAME", "ADDRESS"]
               if adapters.PIPELINE_TO_MASKING.get(t, t) not in rules]
    assert not missing, f"마스킹 규칙과 연결되지 않은 타입: {missing}"


def test_card_and_ip_use_masking_rules():
    segs = _seg("카드 1234-5678-9012-3456 IP 192.168.0.15")
    out = adapters.apply_masking(segs, merge_entities(adapters.detect_regex(segs), []))[0]["text"]
    expected = ("카드 " + adapters.masking.MASK_FUNCTIONS["CREDIT_CARD"]("1234-5678-9012-3456")
                + " IP " + adapters.masking.MASK_FUNCTIONS["IP"]("192.168.0.15"))
    assert out == expected, out


def test_masked_output_hides_full_values():
    """규칙이 무엇이든 원래 번호가 통째로 남아 있으면 안 됨"""
    text = "주민 990101-1234567 전화 010-1234-5678 계좌 110-123-456789 메일 hong@example.com"
    segs = _seg(text)
    out = adapters.apply_masking(segs, merge_entities(adapters.detect_regex(segs), []))[0]["text"]
    for raw in ["990101-1234567", "010-1234-5678", "110-123-456789", "hong@example.com"]:
        assert raw not in out, out


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
