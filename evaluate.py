"""성능 평가 하니스.

캡스톤 보고서에 들어갈 정량 지표(유형별 탐지율·오탐 건수·처리 시간)를
재현 가능한 방식으로 산출한다. 정답 라벨은 labels/*.json 에 스팬 단위로
적어 두고, 규칙을 고칠 때마다 이 스크립트를 돌려 변화를 추적한다.

    python evaluate.py

GitHub Actions 에 등록하면 PR 마다 지표 변동이 자동으로 남는다.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pii import PiiPipeline
from pii.types import EntityType

IOU_MATCH = 0.5  # 정답과 이 비율 이상 겹치면 정탐으로 인정


@dataclass
class Gold:
    text: str
    spans: list[tuple[int, int, str]]  # (start, end, 유형명)


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    if inter == 0:
        return 0.0
    return inter / (max(a[1], b[1]) - min(a[0], b[0]))


def load_gold(path: Path) -> list[Gold]:
    """정답 라벨 로드. 파일이 없으면 내장 샘플을 사용한다."""
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Gold(d["text"], [tuple(s) for s in d["spans"]]) for d in data]
    return BUILTIN_GOLD


def _span(text: str, needle: str, etype: EntityType) -> tuple[int, int, str]:
    i = text.index(needle)
    return (i, i + len(needle), etype.value)


_T1 = "성명: 박서준 / 주민등록번호 920315-2045679 / 연락처 010-3821-7744"
_T2 = "경기도 광주시 경충대로 123번길 45 에 거주하며 이메일은 sjpark@hanbit-edu.co.kr 입니다."
_T3 = "제품 일련번호 123456-1234567 은 개인정보가 아니며 테스트 계정 010-0000-0000 도 제외 대상입니다."

BUILTIN_GOLD: list[Gold] = [
    Gold(_T1, [_span(_T1, "박서준", EntityType.PERSON),
               _span(_T1, "920315-2045679", EntityType.RRN),
               _span(_T1, "010-3821-7744", EntityType.PHONE)]),
    Gold(_T2, [_span(_T2, "경기도 광주시 경충대로 123번길 45", EntityType.ADDRESS),
               _span(_T2, "sjpark@hanbit-edu.co.kr", EntityType.EMAIL)]),
    Gold(_T3, []),  # 전부 오탐이어야 하는 음성 샘플
]


def evaluate(gold_set: list[Gold], include_review: bool = True) -> dict:
    pipe = PiiPipeline(use_model=False)
    tp: defaultdict[str, int] = defaultdict(int)
    fp: defaultdict[str, int] = defaultdict(int)
    fn: defaultdict[str, int] = defaultdict(int)
    elapsed = 0.0

    for gold in gold_set:
        t0 = time.perf_counter()
        report = pipe.scan(gold.text)
        elapsed += time.perf_counter() - t0

        preds = report.actionable if include_review else report.auto
        matched_gold: set[int] = set()

        for p in preds:
            hit = None
            for gi, (gs, ge, gt) in enumerate(gold.spans):
                if gi in matched_gold or gt != p.etype.value:
                    continue
                if _iou((p.start, p.end), (gs, ge)) >= IOU_MATCH:
                    hit = gi
                    break
            if hit is None:
                fp[p.etype.value] += 1
            else:
                matched_gold.add(hit)
                tp[p.etype.value] += 1

        for gi, (_, _, gt) in enumerate(gold.spans):
            if gi not in matched_gold:
                fn[gt] += 1

    rows = []
    for etype in sorted(set(tp) | set(fp) | set(fn)):
        t, f, n = tp[etype], fp[etype], fn[etype]
        prec = t / (t + f) if t + f else 0.0
        rec = t / (t + n) if t + n else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        rows.append((etype, t, f, n, prec, rec, f1))

    total_tp, total_fp, total_fn = sum(tp.values()), sum(fp.values()), sum(fn.values())
    micro_p = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    micro_r = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if micro_p + micro_r else 0.0

    return {
        "rows": rows,
        "micro": (micro_p, micro_r, micro_f1),
        "docs": len(gold_set),
        "ms_per_doc": round(elapsed / max(len(gold_set), 1) * 1000, 2),
    }


def render(result: dict) -> str:
    lines = [
        "## 탐지 성능 평가",
        "",
        "| 유형 | 정탐 | 오탐 | 미탐 | 정밀도 | 재현율 | F1 |",
        "|---|---|---|---|---|---|---|",
    ]
    for etype, t, f, n, p, r, f1 in result["rows"]:
        lines.append(f"| {etype} | {t} | {f} | {n} | "
                     f"{p:.3f} | {r:.3f} | {f1:.3f} |")
    mp, mr, mf = result["micro"]
    lines += [
        f"| **전체(micro)** | | | | **{mp:.3f}** | **{mr:.3f}** | **{mf:.3f}** |",
        "",
        f"- 평가 문서 수: {result['docs']}건",
        f"- 문서당 평균 처리 시간: {result['ms_per_doc']}ms",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    gold = load_gold(Path(__file__).parent / "labels" / "gold.json")
    print(render(evaluate(gold)))
