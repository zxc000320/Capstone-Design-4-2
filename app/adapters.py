"""
모듈 연결 (담당: 김진웅)

팀원 모듈은 수정하지 않고 그대로 호출한다.
이 파일은 각 모듈의 입출력을 파이프라인 공통 형식으로 바꿔주는 역할만 한다.

    regex_detector.detect_text(text) → [{"type", "value", "start", "end"}]   (박주아)
    masking.apply_masking(text, results) → str                              (최동명)
    backup_history.history_manager.record_history(...)                      (김재민)
    pii.ner_engine.NerEngine.detect(text) → [pii.types.Entity]               (이나연)
    pii.fusion (corroborate, propagate_document_level, resolve_overlaps, decide) (이나연)

파이프라인 공통 형식 (Entity):
    {"seg_id", "start", "end", "type", "text", "source"}

모듈 쪽 형식이 바뀌면 이 파일만 맞춰 고치면 된다.
"""
import os
import sys

# 팀원 모듈은 app 폴더 바깥(저장소 맨 위)에 있으므로 그 위치를 import 경로에 추가
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 팀원 파일 옆에 __pycache__ 폴더가 생기지 않게
sys.dont_write_bytecode = True

import regex_detector  # noqa: E402
import masking  # noqa: E402
from backup_history.history_manager import record_history, get_history, LOG_FILE  # noqa: E402

# 타입 이름은 모듈마다 다를 수 있으므로 모듈별로 따로 변환한다.
# 파이프라인 공통 이름: RRN, PHONE, EMAIL, ACCOUNT, CARD, IP_ADDRESS, NAME, ADDRESS

# 정규식 탐지(박주아)가 쓰는 이름 → 파이프라인 이름
DETECTOR_TO_PIPELINE = {
    "BANK_ACCOUNT": "ACCOUNT",
    "CARD_NUMBER": "CARD",
}

# 파이프라인 이름 → 마스킹(최동명) MASK_FUNCTIONS에 등록된 이름
PIPELINE_TO_MASKING = {
    "ACCOUNT": "BANK_ACCOUNT",
    "CARD": "CREDIT_CARD",
    "IP_ADDRESS": "IP",
}


def detect_regex(segments):
    """정규식 탐지: 문단·줄마다 detect_text()를 호출하고 공통 형식으로 변환"""
    entities = []
    for seg in segments:
        for r in regex_detector.detect_text(seg["text"]):
            entities.append({
                "seg_id": seg["seg_id"],
                "start": r["start"],
                "end": r["end"],
                "type": DETECTOR_TO_PIPELINE.get(r["type"], r["type"]),
                "text": r["value"],
                "source": "regex",
            })
    return entities


# ---------------------------------------------------------------- NER (이나연)
# 이나연님 판정 등급 중 마스킹할 등급. "자동처리"는 확실, "검토필요"는 사람 확인 권장.
# 이 프로그램에는 사람이 확인하는 화면이 없으므로, 놓치는 것보다 더 가리는 쪽을 택해 둘 다 마스킹한다.
NER_MASK_DECISIONS = ("자동처리", "검토필요")

# 이나연님 EntityType 이름 → 파이프라인 이름
NER_TO_PIPELINE = {
    "PERSON": "NAME",
    "ADDRESS": "ADDRESS",
    "ORG": "ORG",
    "BIRTH": "BIRTH",
}

# 파이프라인 정형 정보 → 이나연님 EntityType 이름 (주변 방증으로만 사용)
PIPELINE_TO_NER_WITNESS = {
    "RRN": "RRN", "PHONE": "PHONE", "EMAIL": "EMAIL",
    "ACCOUNT": "ACCOUNT", "CARD": "CARD", "IP_ADDRESS": "IP",
}

_ner_engine = None


def _get_ner_engine():
    """NER 엔진은 한 번만 만든다. 사전·규칙 방식만 사용 (AI 모델은 별도 설치가 필요해 끔)."""
    global _ner_engine
    if _ner_engine is None:
        from pii.ner_engine import build_engine
        _ner_engine = build_engine(use_model=False)
    return _ner_engine


def detect_ner(segments, regex_entities=()):
    """NER 탐지: 이나연님 엔진과 판정 규칙을 그대로 사용

    1. 문단·줄마다 NerEngine.detect()로 이름·주소 등 후보를 찾는다.
    2. 같은 문단의 정규식 탐지 결과를 '주변 방증'으로 넘겨 신뢰도를 보강한다 (corroborate).
    3. 문서 전체에서 확정된 표현은 다른 위치에도 같은 판정을 적용한다 (propagate_document_level).
    4. 문단마다 겹침을 정리하고 판정(decide)해서 NER_MASK_DECISIONS 등급만 넘긴다.
    정규식 방증은 신뢰도 계산에만 쓰고, 정형 정보 자체는 정규식 결과(박주아)를 그대로 쓴다.
    """
    from pii.fusion import (FusionConfig, corroborate, decide,
                            propagate_document_level, resolve_overlaps)
    from pii.types import Entity as NerEntity, EntityType

    engine = _get_ner_engine()
    cfg = FusionConfig()

    witnesses_by_seg = {}
    for e in regex_entities:
        name = PIPELINE_TO_NER_WITNESS.get(e["type"])
        if name:
            witnesses_by_seg.setdefault(e["seg_id"], []).append(NerEntity(
                start=e["start"], end=e["end"], text=e["text"], etype=EntityType[name],
                confidence=0.9, engines={"regex"}))

    pools, ner_ids = {}, set()
    for seg in segments:
        found = engine.detect(seg["text"])
        if not found:
            continue
        ner_ids.update(id(x) for x in found)
        pools[seg["seg_id"]] = corroborate(witnesses_by_seg.get(seg["seg_id"], []) + found)

    propagate_document_level([x for pool in pools.values() for x in pool])

    entities = []
    for seg_id, pool in pools.items():
        for x in resolve_overlaps(pool):
            if id(x) not in ner_ids or decide(x, cfg).value not in NER_MASK_DECISIONS:
                continue
            entities.append({
                "seg_id": seg_id,
                "start": x.start,
                "end": x.end,
                "type": NER_TO_PIPELINE.get(x.etype.name, x.etype.name),
                "text": x.text,
                "source": "ner",
                "score": round(x.confidence, 3),
            })
    return entities


def apply_masking(segments, entities):
    """마스킹: 문단·줄마다 apply_masking()을 호출. 모듈이 쓰는 형식(value, 타입 이름)으로 되돌려 넘긴다.

    반환: 마스킹된 segments (순서·seg_id는 입력과 동일)
    """
    by_seg = {}
    for e in entities:
        by_seg.setdefault(e["seg_id"], []).append({
            "type": PIPELINE_TO_MASKING.get(e["type"], e["type"]),
            "value": e["text"],
            "start": e["start"],
            "end": e["end"],
        })

    new_segments = []
    for seg in segments:
        results = by_seg.get(seg["seg_id"])
        text = masking.apply_masking(seg["text"], results) if results else seg["text"]
        new_segments.append({**seg, "text": text})
    return new_segments


def save_history(input_path, output_path, detection_count, check_only, status, error=None):
    """이력 기록: 김재민님 record_history()를 그 모듈의 README에 적힌 규칙대로 호출

    - 처리 방식: 마스킹은 "masking", 점검만은 "check"
    - 상태: "success" 또는 "failed"
    - 오류 메시지에는 개인정보 원문을 넣지 않는다 (파이프라인 오류 메시지는 원문을 포함하지 않음)
    이력은 실행 위치 기준 logs/history.jsonl에 쌓인다 (run.bat은 저장소 맨 위에서 실행)
    """
    return record_history(
        original_file=input_path,
        output_path=output_path,
        detection_count=detection_count,
        processing_type="check" if check_only else "masking",
        status=status,
        error_message=error,
    )


def load_history():
    """이력 조회: 김재민님 get_history() 그대로 호출 (기록한 순서대로 반환)"""
    return get_history()


def history_file_path():
    """이력 파일 위치 (실행 위치 기준 logs/history.jsonl)"""
    return os.path.abspath(str(LOG_FILE))
