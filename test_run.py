from regex_detector import detect_text
from masking import apply_masking

# 테스트용 문장 (주민번호, 계좌번호 포함)
sample_text = """
[고객 문의 내역]
- 주민등록번호: 990101-1234567
- 환불 계좌번호: 110-123-456789
"""

print("=== 1. 원본 텍스트 ===")
print(sample_text)

# 1단계: 탐지
detection_results = detect_text(sample_text)

# 2단계: 마스킹 적용
masked_text = apply_masking(sample_text, detection_results)

print("=== 2. 최종 마스킹 결과 ===")
print(masked_text)