import re

# 1. 주민등록번호 및 외국인등록번호 마스킹 (성별 코드 1~8 대응)
def mask_rrn(rrn_str: str) -> str:
    """
    주민등록번호 및 외국인등록번호 마스킹 (뒷자리 6자리 별표 처리)
    - 성별 코드(1~8) 대응
    - 하이픈(-), 언더바(_), 공백, 구분자 없는 경우 모두 원본 포맷 유지
    """
    pattern_with_sep = r'(?<!\d)(\d{6})([-_ ]?)([1-8])\d{6}(?!\d)'
    return re.sub(pattern_with_sep, r'\1\2\3******', rrn_str)


# 2. 계좌번호 마스킹
def mask_bank_account(account_str: str) -> str:
    """
    계좌번호 마스킹 (뒷자리 별표 처리)
    - 하이픈이 있는 경우: 마지막 하이픈 뒤의 숫자를 별표 처리 (예: 110-123-******)
    - 구분자가 없는 경우: 앞 6자리 남기고 나머지 별표 처리
    """
    if '-' in account_str:
        parts = account_str.rsplit('-', 1)
        return parts[0] + '-' + '*' * len(parts[1])
    
    if len(account_str) > 6:
        return account_str[:6] + '*' * (len(account_str) - 6)
    
    return '*' * len(account_str)


# 3. 탐지 키값(type)과 마스킹 함수 매핑 딕셔너리
MASK_FUNCTIONS = {
    "RRN": mask_rrn,
    "BANK_ACCOUNT": mask_bank_account,
}


# 4. 탐지 모듈 결과를 받아 마스킹을 적용하는 핵심 함수
def apply_masking(text: str, detection_results: list) -> str:
    """
    탐지 결과 리스트를 받아 텍스트를 마스킹 처리된 결과로 변환
    ('text' 키와 기존 'value' 키를 모두 지원하는 하이브리드 처리)
    """
    sorted_results = sorted(detection_results, key=lambda x: x["start"], reverse=True)
    
    masked_text = text
    for item in sorted_results:
        info_type = item["type"]
        
        # 'text' 키가 있으면 사용하고, 없으면 기존 'value' 키를 사용 (호환성 보장)
        val = item.get("text") or item.get("value", "")
        
        start = item["start"]
        end = item["end"]
        
        if info_type in MASK_FUNCTIONS:
            replacement = MASK_FUNCTIONS[info_type](val)
        else:
            replacement = "*" * len(val)
            
        masked_text = masked_text[:start] + replacement + masked_text[end:]
        
    return masked_text


if __name__ == "__main__":
    test_cases = [
        "주민번호: 990101-1234567",
        "외국인번호: 050101-5678901",
        "구분자없음: 9901012234567",
        "계좌번호: 110-123-456789"
    ]
    
    print("=== 마스킹 테스트 결과 ===")
    for text in test_cases:
        print(f"원본: {text} -> 마스킹: {mask_rrn(text)}")