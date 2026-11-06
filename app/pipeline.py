"""
메인 파이프라인 (담당: 김진웅)

처리 순서:
    파일 읽기 → 정규식·NER 탐지 → (형식 검사) → 결과 합치기 → 마스킹 → 결과 파일 저장

팀원 모듈은 adapters.py를 통해 호출한다 (모듈 원본은 수정하지 않음).

모듈 간에는 아래 두 형식(dict)으로만 주고받는다.

Segment (파일 읽기 결과, 문단·줄 단위):
    {"seg_id": "line_3", "text": "...", "meta": {"location": "3행", ...}}

Entity (탐지 결과):
    {"seg_id": "line_3", "start": 15, "end": 29, "type": "RRN",
     "text": "990101-1234567", "source": "regex"}
    - start, end: segment["text"][start:end] 기준 (end는 포함 안 함)
    - text: 개인정보 원문 → 확인용으로만 쓰고 로그·이력 파일에 저장 금지

공개 함수
    run_pipeline(path, mode, out_dir, check_only) : 파일 1개 처리
    run_batch(path, mode, out_dir, check_only)    : 파일 또는 폴더 전체 처리
"""
import os
import re
import uuid
from collections import Counter

from fileio.loader import load_file, is_supported
from fileio.writer import write_file
import adapters

# 정형 정보: 정규식 결과를 우선한다
STRUCTURED_TYPES = {"RRN", "PHONE", "EMAIL", "ACCOUNT", "CARD", "IP_ADDRESS"}
ENTITY_KEYS = ("seg_id", "start", "end", "type", "text", "source")
# 결과 기본 저장 위치: 어디서 실행하든 저장소 맨 위 폴더의 output
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT_DIR, "output")
SKIP_DIRS = {"output", "history", "__pycache__", ".git", "venv", ".venv", "node_modules"}


class ModuleOutputError(ValueError):
    """팀원 모듈이 약속한 형식과 다른 값을 돌려줬을 때"""


# ---------------------------------------------------------------- 형식 검사
def validate_entities(entities, segments, module):
    """탐지 모듈 결과가 공통 형식에 맞는지 검사한다.
    오류 메시지에는 원문(text)을 넣지 않는다 (개인정보 노출 방지)."""
    if not isinstance(entities, list):
        raise ModuleOutputError(f"[{module}] 결과는 list여야 합니다 (받은 값: {type(entities).__name__})")

    seg_text = {s["seg_id"]: s["text"] for s in segments}
    for n, e in enumerate(entities, 1):
        where = f"[{module}] {n}번째 결과"
        if not isinstance(e, dict):
            raise ModuleOutputError(f"{where}: dict여야 합니다")
        missing = [k for k in ENTITY_KEYS if k not in e]
        if missing:
            raise ModuleOutputError(f"{where}: 키 없음 {missing} (필수: {list(ENTITY_KEYS)})")
        if e["seg_id"] not in seg_text:
            raise ModuleOutputError(f"{where}: 없는 seg_id '{e['seg_id']}'")
        text = seg_text[e["seg_id"]]
        if not (isinstance(e["start"], int) and isinstance(e["end"], int) and 0 <= e["start"] < e["end"] <= len(text)):
            raise ModuleOutputError(f"{where}: start/end 범위 오류 ({e['start']}, {e['end']}), 문단 길이 {len(text)}")
        if text[e["start"]:e["end"]] != e["text"]:
            raise ModuleOutputError(f"{where}: text가 원문[start:end]와 다릅니다 (seg_id={e['seg_id']}, type={e['type']})")


def validate_masked_segments(new_segments, segments):
    if [s["seg_id"] for s in new_segments] != [s["seg_id"] for s in segments]:
        raise ModuleOutputError("[masking] 마스킹 결과의 개수·순서가 입력과 같아야 합니다")
    for s in new_segments:
        if not isinstance(s["text"], str):
            raise ModuleOutputError(f"[masking] 마스킹 결과가 문자열이 아닙니다 (seg_id={s['seg_id']})")
    return new_segments


# ---------------------------------------------------------------- 결과 합치기
def merge_entities(regex_entities, ner_entities):
    """정규식·NER 결과를 합치고 겹치는 구간을 정리한다.

    규칙:
      1. 위치가 겹치면 하나만 남긴다.
      2. 정형 정보 타입은 정규식 결과 우선.
      3. 그 외에는 더 긴 구간을 남긴다.
    """
    def priority(e):
        is_regex_structured = e["source"] == "regex" and e["type"] in STRUCTURED_TYPES
        return (is_regex_structured, e["end"] - e["start"])

    candidates = sorted(regex_entities + ner_entities, key=priority, reverse=True)
    kept = []
    for e in candidates:
        overlaps = any(
            k["seg_id"] == e["seg_id"] and e["start"] < k["end"] and k["start"] < e["end"]
            for k in kept
        )
        if not overlaps:
            kept.append(e)

    kept.sort(key=lambda e: (_natural_key(e["seg_id"]), e["start"]))
    return kept


def _natural_key(seg_id):
    """line_2가 line_10보다 앞에 오도록 숫자는 숫자로 비교"""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", seg_id)]


# ---------------------------------------------------------------- 파일 1개
def run_pipeline(input_path, mode="mask", out_dir=DEFAULT_OUT, check_only=False):
    """파일 1개를 처리한다.

    check_only=True: 탐지·점검만 하고 결과 파일은 만들지 않는다
    mode: 현재 "mask"만 지원 (마스킹 모듈에 가명처리가 추가되면 확장)
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {input_path}")
    if mode != "mask":
        raise ValueError(f"알 수 없는 mode: {mode}")

    doc_id = uuid.uuid4().hex[:12]

    # 1. 파일 읽기
    segments, doc = load_file(input_path)

    # 2. 탐지 + 형식 검사
    regex_entities = adapters.detect_regex(segments)
    validate_entities(regex_entities, segments, "regex_detector")
    ner_entities = adapters.detect_ner(segments)
    validate_entities(ner_entities, segments, "ner_detector")

    # 3. 결과 합치기
    entities = merge_entities(regex_entities, ner_entities)

    # 4. 마스킹 (점검 모드에서도 미리보기용으로 실행)
    new_segments = validate_masked_segments(adapters.apply_masking(segments, entities), segments)

    # 5. 결과 파일 저장 (원본 덮어쓰기 금지)
    # TODO: 점검·처리 이력 기록은 이력관리 모듈(김재민)이 들어오면 여기서 연결
    output_path = None
    if not check_only:
        output_path = write_file(input_path, new_segments, doc, out_dir)

    # 점검 결과: 어디에 무엇이 있었는지 (원문 대신 마스킹된 문장으로 보여줌)
    found_segs = {e["seg_id"] for e in entities}
    types_by_seg = {}
    for e in entities:
        types_by_seg.setdefault(e["seg_id"], []).append(e["type"])
    findings = [
        {"location": s["meta"].get("location", s["seg_id"]), "types": types_by_seg[s["seg_id"]],
         "preview": p["text"].strip()}
        for s, p in zip(segments, new_segments) if s["seg_id"] in found_segs
    ]

    return {
        "doc_id": doc_id,
        "input_path": input_path,
        "output_path": output_path,
        "total": len(entities),
        "counts": dict(Counter(e["type"] for e in entities)),
        "findings": findings,
    }


# ---------------------------------------------------------------- 폴더
def collect_files(path, out_dir=DEFAULT_OUT):
    """처리할 파일 목록. 폴더면 하위 폴더까지 지원 형식만 모은다.
    결과 폴더·이력 폴더·이미 마스킹된 파일(_masked)은 건너뛴다."""
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise FileNotFoundError(f"파일이나 폴더를 찾을 수 없습니다: {path}")

    out_abs = os.path.abspath(out_dir)
    files = []
    for root, dirs, names in os.walk(path):
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not d.startswith(".")
                         and os.path.abspath(os.path.join(root, d)) != out_abs)
        for name in sorted(names):
            full = os.path.join(root, name)
            if is_supported(full) and not os.path.splitext(name)[0].endswith("_masked"):
                files.append(full)
    return files


def run_batch(path, mode="mask", out_dir=DEFAULT_OUT, check_only=False, on_progress=None, files=None):
    """파일 또는 폴더를 처리한다. 파일 하나가 실패해도 나머지는 계속 진행.

    on_progress(i, n, file_path, result_or_None, error_or_None): 진행 상황 콜백 (GUI용)
    files: 처리할 파일 목록 (GUI에서 일부만 선택한 경우). 없으면 path 안의 지원 파일 전부
    반환: {"results": [...], "errors": [(file_path, message), ...]}
    """
    if files is None:
        files = collect_files(path, out_dir)
    base = path if os.path.isdir(path) else os.path.dirname(path)
    results, errors = [], []

    for i, f in enumerate(files, 1):
        # 폴더 구조를 결과 폴더에도 그대로 유지
        rel_dir = os.path.relpath(os.path.dirname(f), base) if base else ""
        target_dir = os.path.normpath(os.path.join(out_dir, rel_dir))
        try:
            r = run_pipeline(f, mode=mode, out_dir=target_dir, check_only=check_only)
            results.append(r)
            err = None
        except ModuleOutputError:
            raise  # 모듈 형식 오류는 모든 파일에서 똑같이 나므로 바로 중단
        except Exception as e:
            r, err = None, f"{type(e).__name__}: {e}"
            errors.append((f, err))
        if on_progress:
            on_progress(i, len(files), f, r, err)

    return {"results": results, "errors": errors}
