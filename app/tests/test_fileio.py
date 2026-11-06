"""
파일 입출력·파이프라인 테스트 (담당: 김진웅) — run_tests.py가 함께 실행
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

import pipeline
from pipeline import run_pipeline, run_batch, validate_entities, ModuleOutputError


class _Tmp:
    def __enter__(self):
        self.cwd = os.getcwd()
        self.dir = tempfile.mkdtemp()
        os.chdir(self.dir)          # 실행 중 생기는 파일이 임시 폴더에 생기게
        return self.dir

    def __exit__(self, *a):
        os.chdir(self.cwd)
        shutil.rmtree(self.dir)


def _add_hyperlink(para, url, text):
    r_id = para.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    link.append(run)
    para._p.append(link)


def _make_docx(path):
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("주민번호는 ")
    p.add_run("990101-").bold = True          # 개인정보가 서식 경계에 걸쳐 있음
    p.add_run("1234567").italic = True
    p.add_run(" 입니다.").bold = True
    p2 = doc.add_paragraph("메일: ")
    _add_hyperlink(p2, "mailto:hong@example.com", "hong@example.com")
    table = doc.add_table(rows=2, cols=2)
    a = table.cell(0, 0).merge(table.cell(0, 1))  # 병합 셀
    a.text = "연락처 010-1234-5678"
    inner = table.cell(1, 0).add_table(rows=1, cols=1)   # 중첩 표
    inner.cell(0, 0).text = "카드 1234-5678-9012-3456"
    doc.sections[0].header.paragraphs[0].text = "작성자 IP 192.168.0.15"
    doc.add_paragraph("개인정보 없는 문단")
    doc.save(path)


def test_docx_keeps_format_and_covers_all_parts():
    with _Tmp() as d:
        src = os.path.join(d, "doc.docx")
        _make_docx(src)
        r = run_pipeline(src, out_dir=os.path.join(d, "out"))
        assert r["counts"] == {"RRN": 1, "EMAIL": 1, "PHONE": 1, "CARD": 1, "IP_ADDRESS": 1}, r["counts"]

        out = Document(r["output_path"])
        p = out.paragraphs[0]
        assert p.text == "주민번호는 990101-1****** 입니다."
        runs = [(x.text, bool(x.bold), bool(x.italic)) for x in p.runs]
        assert runs == [("주민번호는 ", False, False), ("990101-", True, False),
                        ("1******", False, True), (" 입니다.", True, False)], runs

        # 하이퍼링크: 글자는 가려지고 mailto 링크는 제거
        assert out.paragraphs[1].text == "메일: " + "*" * len("hong@example.com")
        assert not out.paragraphs[1].hyperlinks

        assert out.tables[0].cell(0, 0).text == "연락처 *************"
        assert out.tables[0].cell(1, 0).tables[0].cell(0, 0).text == "카드 *******************"
        assert out.sections[0].header.paragraphs[0].text == "작성자 IP ************"
        assert out.paragraphs[-1].text == "개인정보 없는 문단"

        # docx 내부 파일 전체(링크 주소 저장소 포함)에 원문이 남아 있지 않아야 함
        import zipfile
        with zipfile.ZipFile(r["output_path"]) as z:
            blob = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
        for raw in ["1234567", "hong@example.com", "010-1234-5678", "1234-5678-9012-3456", "192.168.0.15"]:
            assert raw not in blob, f"결과 docx 안에 원문이 남음: {raw}"


def test_text_keeps_crlf_and_encoding():
    with _Tmp() as d:
        src = os.path.join(d, "legacy.log")
        with open(src, "wb") as f:
            f.write("사용자 990101-1234567 로그인\r\n정상 종료\r\n".encode("cp949"))
        r = run_pipeline(src, out_dir=os.path.join(d, "out"))
        with open(r["output_path"], "rb") as f:
            raw = f.read()
        assert raw == "사용자 990101-1****** 로그인\r\n정상 종료\r\n".encode("cp949"), raw


def test_source_code_file():
    with _Tmp() as d:
        src = os.path.join(d, "config.py")
        with open(src, "w", encoding="utf-8") as f:
            f.write('ADMIN_PHONE = "010-9876-5432"\nDEBUG = True\n')
        r = run_pipeline(src, out_dir=os.path.join(d, "out"))
        with open(r["output_path"], encoding="utf-8") as f:
            assert f.read() == 'ADMIN_PHONE = "*************"\nDEBUG = True\n'


def test_check_only_writes_no_file():
    with _Tmp() as d:
        src = os.path.join(d, "a.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("없음\n전화 010-1234-5678\n")
        r = run_pipeline(src, out_dir=os.path.join(d, "out"), check_only=True)
        assert r["output_path"] is None and not os.path.exists(os.path.join(d, "out"))
        assert r["findings"] == [{"location": "2행", "types": ["PHONE"], "preview": "전화 *************"}]


def test_batch_folder():
    with _Tmp() as d:
        src = os.path.join(d, "in")
        os.makedirs(os.path.join(src, "sub"))
        for rel, body in [("a.txt", "010-1234-5678"), ("sub/b.log", "990101-1234567"),
                          ("a_masked.txt", "이미 처리됨"), ("image.png", "x")]:
            with open(os.path.join(src, rel), "w", encoding="utf-8") as f:
                f.write(body)
        with open(os.path.join(src, "bad.txt"), "wb") as f:
            f.write(b"\x00\x01binary")
        out = os.path.join(d, "out")
        s = run_batch(src, out_dir=out)
        assert sorted(os.path.relpath(r["output_path"], out) for r in s["results"]) == \
            ["a_masked.txt", os.path.join("sub", "b_masked.log")]
        assert len(s["errors"]) == 1 and s["errors"][0][0].endswith("bad.txt")


def test_validation_catches_bad_module():
    segs = [{"seg_id": "line_1", "text": "010-1234-5678", "meta": {}}]
    good = {"seg_id": "line_1", "start": 0, "end": 13, "type": "PHONE", "text": "010-1234-5678", "source": "regex"}
    validate_entities([good], segs, "x")
    for bad, msg in [({**good, "text": "x"}, "다릅니다"),
                     ({k: v for k, v in good.items() if k != "text"} | {"value": "x"}, "키 없음"),
                     ({**good, "end": 99}, "범위"),
                     ({**good, "seg_id": "p9"}, "seg_id")]:
        try:
            validate_entities([bad], segs, "x")
            raise AssertionError(f"검사 통과하면 안 됨: {msg}")
        except ModuleOutputError as e:
            assert msg in str(e), e
            assert "010-1234-5678" not in str(e)   # 오류 메시지에 원문 노출 금지


def test_batch_stops_on_module_error():
    original = pipeline.adapters.detect_ner
    pipeline.adapters.detect_ner = lambda segs: [{"value": "x"}]
    try:
        with _Tmp() as d:
            with open(os.path.join(d, "a.txt"), "w", encoding="utf-8") as f:
                f.write("hello")
            try:
                run_batch(d, out_dir=os.path.join(d, "out"))
                raise AssertionError("ModuleOutputError가 나야 함")
            except ModuleOutputError as e:
                assert "ner_detector" in str(e)
    finally:
        pipeline.adapters.detect_ner = original


def test_batch_records_history():
    import json
    with _Tmp() as d:
        src = os.path.join(d, "in")
        os.makedirs(src)
        with open(os.path.join(src, "a.txt"), "w", encoding="utf-8") as f:
            f.write("전화 010-1234-5678\n주민 990101-1234567\n")
        with open(os.path.join(src, "bad.txt"), "wb") as f:
            f.write(b"\x00\x01binary")
        out = os.path.join(d, "out")

        s = run_batch(src, out_dir=out)                    # 마스킹
        assert s["history_errors"] == []
        run_batch(src, out_dir=out, check_only=True)       # 점검만

        log_path = os.path.join(d, "logs", "history.jsonl")   # 실행 위치 기준 logs/
        with open(log_path, encoding="utf-8") as f:
            raw = f.read()
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        summary = [(r["original_filename"], r["processing_type"], r["status"], r["detection_count"],
                    r["output_path"] is not None) for r in rows]
        assert summary == [
            ("a.txt", "masking", "success", 2, True),
            ("bad.txt", "masking", "failed", 0, False),
            ("a.txt", "check", "success", 2, False),
            ("bad.txt", "check", "failed", 0, False),
        ], summary
        assert rows[1]["error_message"].startswith("ValueError")
        # 이력 파일에 개인정보 원문이 남지 않아야 함
        for raw_value in ["010-1234-5678", "990101-1234567", "1234567"]:
            assert raw_value not in raw


def test_history_failure_does_not_stop_processing():
    original = pipeline.adapters.save_history
    def broken(*a, **k):
        raise OSError("디스크 가득 참")
    pipeline.adapters.save_history = broken
    try:
        with _Tmp() as d:
            with open(os.path.join(d, "a.txt"), "w", encoding="utf-8") as f:
                f.write("010-1234-5678")
            s = run_batch(d, out_dir=os.path.join(d, "out"))
            assert len(s["results"]) == 1 and s["results"][0]["output_path"]
            assert s["history_errors"] and "디스크 가득 참" in s["history_errors"][0]
    finally:
        pipeline.adapters.save_history = original


def test_load_history_for_viewer():
    import adapters
    with _Tmp() as d:
        assert adapters.load_history() == []
        with open(os.path.join(d, "a.txt"), "w", encoding="utf-8") as f:
            f.write("010-1234-5678")
        run_batch(d, out_dir=os.path.join(d, "out"))
        h = adapters.load_history()
        assert len(h) == 1 and h[0]["status"] == "success" and h[0]["detection_count"] == 1
        assert adapters.history_file_path().endswith(os.path.join("logs", "history.jsonl"))
