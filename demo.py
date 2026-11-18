"""데모 실행 스크립트.

사용된 번호·성명·주소는 모두 검증 알고리즘만 통과하도록 인위적으로
생성한 가상 데이터다. 실제 개인정보는 테스트에 사용하지 않는다.

    python demo.py
"""

from __future__ import annotations

from pii import PiiPipeline
from pii.fusion import Decision

SAMPLE = """\
[교육생 수강신청서]

성명: 박서준          생년월일: 1992년 3월 15일
주민등록번호: 920315-2045679
연락처: 010-3821-7744    이메일: sjpark@hanbit-edu.co.kr
주소: 경기도 광주시 경충대로 123번길 45 202동 1103호 (우편번호 12771)
소속: 정보통신산업대학교 정보보안학과

환불 계좌: 110-482-773901 (예금주 박서준)
결제 카드: 4532-1234-5678-9014
차량: 12가 3456

담당 조교 김하늘 님이 서류를 검토하였으며, 이후 처리 결과는
이번 주 금요일까지 안내할 예정입니다.
문의처: 주식회사 한빛에듀 (사업자등록번호 124-81-54325), 031-777-1234

--- 첨부 설정파일 발췌 ---
AWS_ACCESS_KEY_ID = "AKIA3F7QZLM2XKPVD9WR"
api_key: "sk_live_9f2a7c41bd83e0a6"
서버 IP: 192.168.10.54
제품 일련번호: 123456-1234567 (개인정보 아님)
"""


def main() -> None:
    # 모델 백엔드가 없는 환경에서도 그대로 동작한다.
    pipe = PiiPipeline(use_model=True)

    report, masked = pipe.process(SAMPLE, source="수강신청서.txt")

    print("=" * 68)
    print(report.to_markdown())

    print()
    print("=" * 68)
    print("■ 검토 대기 항목 (사람 확인 후 적용)")
    for e in report.review:
        print(f"  - {e.etype.value:8s} '{e.text}' "
              f"conf={e.confidence:.2f}  근거={'; '.join(e.evidence)}")

    print()
    print("■ 오탐으로 제외된 항목")
    for e in report.discarded:
        print(f"  - {e.etype.value:8s} '{e.text}' "
              f"conf={e.confidence:.2f}  근거={'; '.join(e.evidence)}")

    print()
    print("=" * 68)
    print("■ 처리본 (자동처리 등급만 반영)")
    print(masked.text)

    print("=" * 68)
    print("■ 가명 매핑 (재식별 키 — 별도 보관 및 접근통제 대상)")
    for alias, origin in masked.pseudonym_map.items():
        print(f"  {alias} ← {origin}")

    print()
    print(f"■ 위험도 점수: {report.risk_score}/100")
    print(f"■ 엔진 정보: {report.engine_info}")


if __name__ == "__main__":
    main()
