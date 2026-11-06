"""
모듈 연결 (담당: 김진웅)

팀원 모듈은 수정하지 않고 그대로 호출한다.
이 파일은 각 모듈의 입출력을 파이프라인 공통 형식으로 바꿔주는 역할만 한다.

    regex_detector.detect_text(text) → [{"type", "value", "start", "end"}]   (박주아)
    masking.apply_masking(text, results) → str                              (최동명)
    backup_history.history_manager.record_history(...)                      (김재민)

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

# 모듈 타입 이름 → 파이프라인 타입 이름
TYPE_FROM_MODULE = {
    "BANK_ACCOUNT": "ACCOUNT",
    "CARD_NUMBER": "CARD",
}
TYPE_TO_MODULE = {v: k for k, v in TYPE_FROM_MODULE.items()}


def detect_regex(segments):
    """정규식 탐지: 문단·줄마다 detect_text()를 호출하고 공통 형식으로 변환"""
    entities = []
    for seg in segments:
        for r in regex_detector.detect_text(seg["text"]):
            entities.append({
                "seg_id": seg["seg_id"],
                "start": r["start"],
                "end": r["end"],
                "type": TYPE_FROM_MODULE.get(r["type"], r["type"]),
                "text": r["value"],
                "source": "regex",
            })
    return entities


def detect_ner(segments):
    """NER 탐지 (이나연) — 모듈이 아직 없어 빈 결과. 모듈이 들어오면 여기서 연결."""
    return []


def apply_masking(segments, entities):
    """마스킹: 문단·줄마다 apply_masking()을 호출. 모듈이 쓰는 형식(value, 타입 이름)으로 되돌려 넘긴다.

    반환: 마스킹된 segments (순서·seg_id는 입력과 동일)
    """
    by_seg = {}
    for e in entities:
        by_seg.setdefault(e["seg_id"], []).append({
            "type": TYPE_TO_MODULE.get(e["type"], e["type"]),
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
