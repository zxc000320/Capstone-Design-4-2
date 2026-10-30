"""
docx 공통 도구 (담당: 김진웅)

loader와 writer가 '같은 순서'로 문단을 훑어야 seg_id가 정확히 맞는다.
그래서 문단 목록을 만드는 함수를 한 곳(iter_paragraphs)에 둔다.

훑는 범위: 본문 문단 → 본문 표(중첩 표 포함) → 각 구역의 머리글·바닥글
"""
from difflib import SequenceMatcher

from docx.text.hyperlink import Hyperlink
from docx.text.run import Run


def _iter_block(container, where):
    """문단과 표(중첩 포함)를 문서 순서대로 훑는다."""
    for para in container.paragraphs:
        yield para, where
    for t, table in enumerate(container.tables):
        for r, row in enumerate(table.rows):
            for c, cell in enumerate(row.cells):
                yield from _iter_block(cell, f"{where} 표{t + 1}({r + 1}행 {c + 1}열)")


def iter_paragraphs(doc):
    """(paragraph, 위치설명) 목록. 병합 셀 때문에 같은 문단이 여러 번 나오면 한 번만 반환."""
    seen = set()
    sources = [(doc, "본문")]
    for s, section in enumerate(doc.sections):
        for part, name in ((section.header, "머리글"), (section.footer, "바닥글")):
            if not part.is_linked_to_previous:  # 이전 구역과 공유하는 머리글은 중복이라 건너뜀
                sources.append((part, f"구역{s + 1} {name}"))

    for container, where in sources:
        for para, loc in _iter_block(container, where):
            # id()를 쓰면 파이썬이 메모리 주소를 재사용해 다른 문단을 중복으로 착각할 수 있음
            # → XML 요소 자체를 저장(살려둠)해서 비교
            if para._p in seen:
                continue
            seen.add(para._p)
            yield para, loc


def _all_runs(para):
    """하이퍼링크 안의 run까지 포함해 순서대로. (run, 소속 하이퍼링크 또는 None)"""
    out = []
    for item in para.iter_inner_content():
        if isinstance(item, Run):
            out.append((item, None))
        elif isinstance(item, Hyperlink):
            out.extend((run, item) for run in item.runs)
    return out


def _unlink(hyperlink):
    """하이퍼링크를 없애고 글자(run)만 남긴다. (mailto: 주소 등에 원문이 남지 않게)"""
    el = hyperlink._hyperlink
    r_id = el.rId
    part = hyperlink.part
    parent = el.getparent()
    for child in list(el):
        el.addprevious(child)
    parent.remove(el)
    # 링크 주소는 본문이 아니라 document.xml.rels에 따로 저장돼 있음 → 거기서도 삭제
    # (다른 곳에서 같은 주소를 쓰고 있으면 drop_rel이 알아서 남겨둠)
    if r_id:
        part.drop_rel(r_id)


def set_paragraph_text(para, new_text):
    """문단 글자를 new_text로 바꾸되, 바뀌지 않은 글자의 서식(굵게·색 등)은 그대로 둔다.

    원리: 원래 글자와 새 글자를 비교(diff)해서 바뀐 구간만 해당 run 안에서 교체한다.
    바뀐 글자는 그 구간이 시작되는 run의 서식을 따른다.
    """
    runs = _all_runs(para)
    old_text = "".join(run.text for run, _ in runs)
    if old_text == new_text:
        return

    if not runs:  # 글자 run이 없는 문단 (거의 없음)
        para.add_run(new_text)
        return

    # 글자 위치 → run 번호
    owner = []
    for idx, (run, _) in enumerate(runs):
        owner.extend([idx] * len(run.text))

    pieces = [""] * len(runs)
    matcher = SequenceMatcher(None, old_text, new_text, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                pieces[owner[i1 + k]] += old_text[i1 + k]
        elif op in ("replace", "delete"):
            pieces[owner[i1]] += new_text[j1:j2]
        else:  # insert
            target = owner[i1 - 1] if i1 > 0 else 0
            pieces[target] += new_text[j1:j2]

    changed_links = set()
    for (run, link), piece in zip(runs, pieces):
        if run.text != piece:
            run.text = piece
            if link is not None:
                changed_links.add(link)

    for link in changed_links:
        _unlink(link)
