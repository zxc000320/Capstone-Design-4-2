import re

def mask_rrn(rrn_str: str) -> str:
    """
    주민등록번호 및 외국인등록번호 마스킹 (뒷자리 6자리 별표 처리)
    - 성별 코드(1~8) 대응
    - 하이픈(-), 언더바(_), 공백, 구분자 없는 경우 모두 원본 포맷 유지
    """
    pattern_with_sep = r'(?<!\d)(\d{6})([-_ ]?)([1-8])\d{6}(?!\d)'
    return re.sub(pattern_with_sep, r'\1\2\3******', rrn_str)

if __name__ == "__main__":
    test_cases = [
        "주민번호: 990101-1234567",
        "외국인번호: 050101-5678901",
        "구분자없음: 9901012234567",
        "공백구분: 990101 1234567"
    ]
    
    print("=== 마스킹 모듈 테스트 결과 ===")
    for text in test_cases:
        print(f"원본: {text} -> 마스킹: {mask_rrn(text)}")