"""
실행 진입점 (CLI) — 담당: 김진웅

사용 예:
    python app/main.py app/samples/sample.txt         # 마스킹
    python app/main.py 폴더경로/ --out result/         # 폴더 전체 처리
    python app/main.py 폴더경로/ --check               # 점검만 (결과 파일 안 만듦)

GUI로 실행하려면: python app/gui.py
"""
import argparse
import sys

from pipeline import run_batch, ModuleOutputError, DEFAULT_OUT

TYPE_NAMES = {
    "RRN": "주민번호", "PHONE": "전화번호", "EMAIL": "이메일", "ACCOUNT": "계좌번호",
    "CARD": "카드번호", "IP_ADDRESS": "IP주소", "NAME": "이름", "ADDRESS": "주소",
}


def describe_counts(counts):
    if not counts:
        return "없음"
    return ", ".join(f"{TYPE_NAMES.get(t, t)} {n}" for t, n in counts.items())


def main(argv=None):
    parser = argparse.ArgumentParser(description="개인정보 자동 탐지·마스킹 프로그램")
    parser.add_argument("input", help="처리할 파일 또는 폴더")
    parser.add_argument("--out", default=DEFAULT_OUT, help="결과 저장 폴더 (기본: 맨 위 폴더의 output)")
    parser.add_argument("--check", action="store_true", help="점검만 하고 결과 파일은 만들지 않음")
    parser.add_argument("-q", "--quiet", action="store_true", help="파일별 상세 내용 생략")
    args = parser.parse_args(argv)

    def on_progress(i, n, path, result, error):
        if error:
            print(f"[{i}/{n}] 실패  {path}\n        {error}")
            return
        line = f"[{i}/{n}] {result['total']}건  {path}"
        if result["output_path"]:
            line += f"  →  {result['output_path']}"
        print(line)
        if result["total"] and not args.quiet:
            print(f"        {describe_counts(result['counts'])}")
            if args.check:
                for f in result["findings"]:
                    types = ", ".join(TYPE_NAMES.get(t, t) for t in f["types"])
                    print(f"        - {f['location']} [{types}] {f['preview']}")

    try:
        summary = run_batch(args.input, out_dir=args.out,
                            check_only=args.check, on_progress=on_progress)
    except ModuleOutputError as e:
        print(f"[모듈 형식 오류] {e}")
        return 2
    except Exception as e:
        print(f"[오류] {e}")
        return 1

    results, errors = summary["results"], summary["errors"]
    if not results and not errors:
        print("처리할 파일이 없습니다.")
        return 1

    total = {}
    for r in results:
        for t, n in r["counts"].items():
            total[t] = total.get(t, 0) + n
    print("\n" + "=" * 50)
    print(f"{'점검' if args.check else '처리'} 완료: 파일 {len(results)}개, "
          f"개인정보 {sum(total.values())}건 ({describe_counts(total)})")
    if errors:
        print(f"실패: {len(errors)}개 (위 목록 참고)")
    for h in summary.get("history_errors", []):
        print(f"[경고] 이력 기록 실패 — {h}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
