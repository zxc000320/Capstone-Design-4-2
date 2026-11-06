"""
파일 읽기 (담당: 김진웅)

load_file(path) -> (segments, doc)
    segments: [{"seg_id": str, "text": str, "meta": dict}, ...]
    doc: docx면 Document 객체(저장할 때 서식 유지용), 텍스트 파일이면 None

지원 형식
    - docx: 본문·표(중첩 포함)·머리글·바닥글을 문단 단위로
    - 텍스트 계열(문서·로그·소스코드·데이터): 줄 단위, 줄바꿈 방식·인코딩 그대로 보존
"""
import os

DOCX_EXTS = {".docx"}
TEXT_EXTS = {
    # 문서·로그
    ".txt", ".log", ".md", ".csv", ".tsv",
    # 설정·데이터
    ".json", ".xml", ".yml", ".yaml", ".ini", ".conf", ".cfg", ".properties", ".env", ".sql",
    # 소스코드
    ".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".go", ".rb", ".php", ".kt", ".swift", ".rs", ".sh", ".bat", ".ps1", ".html", ".css",
}
SUPPORTED = DOCX_EXTS | TEXT_EXTS

# 한글 텍스트 파일은 utf-8 아니면 cp949(EUC-KR 확장)가 대부분
ENCODINGS = ("utf-8", "cp949")


def is_supported(path):
    return os.path.splitext(path)[1].lower() in SUPPORTED


def load_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        raise ValueError(f"지원하지 않는 형식입니다: {ext or '(확장자 없음)'}")
    if ext in DOCX_EXTS:
        return _load_docx(path)
    return _load_text(path)


def _read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw[:8192]:
        raise ValueError("텍스트 파일이 아닌 것 같습니다 (바이너리 데이터 포함)")
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 알 수 없습니다 (지원: {', '.join(ENCODINGS)})")


def _load_text(path):
    content, enc = _read_text(path)
    # split("\n")만 하면 Windows 줄바꿈(\r\n)의 \r이 각 줄 끝에 남아 저장 시 그대로 복원된다
    lines = content.split("\n")
    segments = [
        {"seg_id": f"line_{i + 1}", "text": line,
         "meta": {"line_no": i + 1, "encoding": enc, "location": f"{i + 1}행"}}
        for i, line in enumerate(lines)
    ]
    return segments, None


def _load_docx(path):
    from docx import Document
    from fileio.docx_utils import iter_paragraphs

    doc = Document(path)
    segments = [
        {"seg_id": f"para_{i + 1}", "text": para.text, "meta": {"index": i, "location": loc}}
        for i, (para, loc) in enumerate(iter_paragraphs(doc))
    ]
    return segments, doc
