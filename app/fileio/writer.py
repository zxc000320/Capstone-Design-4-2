"""
결과 파일 저장 (담당: 김진웅)

write_file(input_path, segments, doc, out_dir) -> output_path
    - 원본은 절대 덮어쓰지 않고 out_dir에 '원본이름_masked.확장자'로 저장
    - 텍스트: 원래 인코딩·줄바꿈 그대로
    - docx: 바뀐 글자만 교체해서 서식 유지, 마스킹된 하이퍼링크는 링크 제거
"""
import os


def output_path_for(input_path, out_dir):
    name, ext = os.path.splitext(os.path.basename(input_path))
    return os.path.join(out_dir, f"{name}_masked{ext}")


def write_file(input_path, segments, doc, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    output_path = output_path_for(input_path, out_dir)

    if os.path.abspath(output_path) == os.path.abspath(input_path):
        raise ValueError("결과 파일 경로가 원본과 같습니다. 다른 폴더를 지정하세요.")

    if doc is not None:
        _write_docx(segments, doc, output_path)
    else:
        _write_text(segments, output_path)
    return output_path


def _write_text(segments, output_path):
    enc = segments[0]["meta"].get("encoding", "utf-8") if segments else "utf-8"
    # newline="" → 파이썬이 줄바꿈을 바꾸지 않게 (원본 \n / \r\n 그대로)
    with open(output_path, "w", encoding=enc, newline="") as f:
        f.write("\n".join(s["text"] for s in segments))


def _write_docx(segments, doc, output_path):
    from fileio.docx_utils import iter_paragraphs, set_paragraph_text

    paragraphs = [para for para, _ in iter_paragraphs(doc)]
    for s in segments:
        set_paragraph_text(paragraphs[s["meta"]["index"]], s["text"])
    doc.save(output_path)
