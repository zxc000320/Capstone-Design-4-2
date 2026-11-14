import re

# 1. 주민등록번호 및 외국인등록번호 마스킹 (앞 7자리 유지, 뒤 6자리 마스킹)
def mask_rrn(rrn_str: str) -> str:
    pattern_with_sep = r'(?<!\d)(\d{6})([-_ ]?)([1-8])\d{6}(?!\d)'
    return re.sub(pattern_with_sep, r'\1\2\3******', rrn_str)

# 2. 전화번호 마스킹 (국번 뒤 4자리 마스킹)
def mask_phone(phone_str: str) -> str:
    if '-' in phone_str:
        parts = phone_str.rsplit('-', 1)
        return parts[0] + '-' + '*' * len(parts[1])
    if len(phone_str) >= 4:
        return phone_str[:-4] + '****'
    return '*' * len(phone_str)

# 3. 이메일 주소 마스킹 (ID 앞 3자리 유지, 나머지 마스킹, 도메인 유지)
def mask_email(email_str: str) -> str:
    if '@' not in email_str:
        return '*' * len(email_str)
    user_id, domain = email_str.split('@', 1)
    if len(user_id) > 3:
        masked_id = user_id[:3] + '*' * (len(user_id) - 3)
    else:
        masked_id = user_id[0] + '*' * (len(user_id) - 1) if len(user_id) > 1 else '*'
    return f"{masked_id}@{domain}"

# 4. 계좌번호 마스킹 (마지막 하이픈 뒤 또는 앞 6자리 외 마스킹)
def mask_bank_account(account_str: str) -> str:
    if '-' in account_str:
        parts = account_str.rsplit('-', 1)
        return parts[0] + '-' + '*' * len(parts[1])
    if len(account_str) > 6:
        return account_str[:6] + '*' * (len(account_str) - 6)
    return '*' * len(account_str)

# 5. 신용카드번호 마스킹 (9~12번째 3번째 구획 4자리 마스킹)
def mask_credit_card(card_str: str) -> str:
    if '-' in card_str:
        parts = card_str.split('-')
        if len(parts) == 4:
            parts[2] = '*' * len(parts[2])
            return '-'.join(parts)
    digits = re.sub(r'\D', '', card_str)
    if len(digits) == 16:
        return digits[:8] + '****' + digits[12:]
    return '*' * len(card_str)

# 6. IP 주소 마스킹 (3, 4번째 옥텟 마스킹)
def mask_ip(ip_str: str) -> str:
    parts = ip_str.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.***.***"
    return '*' * len(ip_str)

# 7. 성명 마스킹 (2자: 성 외 마스킹 / 3자 이상: 가운데 마스킹)
def mask_name(name_str: str) -> str:
    name_str = name_str.strip()
    length = len(name_str)
    if length <= 1:
        return '*'
    elif length == 2:
        return name_str[0] + '*'
    else:
        return name_str[0] + '*' * (length - 2) + name_str[-1]

# 8. 주소 마스킹 (시/군/구 이하 상세 주소 마스킹)
def mask_address(addr_str: str) -> str:
    tokens = addr_str.split()
    if len(tokens) > 2:
        return f"{tokens[0]} {tokens[1]} *****"
    return '*' * len(addr_str)


# 탐지 키값(type)과 마스킹 함수 매핑 딕셔너리
MASK_FUNCTIONS = {
    "RRN": mask_rrn,
    "PHONE": mask_phone,
    "EMAIL": mask_email,
    "BANK_ACCOUNT": mask_bank_account,
    "CREDIT_CARD": mask_credit_card,
    "IP": mask_ip,
    "NAME": mask_name,
    "ADDRESS": mask_address,
}


# 탐지 모듈 결과를 받아 마스킹을 적용하는 핵심 함수 (역순 치환 방식)
def apply_masking(text: str, detection_results: list) -> str:
    sorted_results = sorted(detection_results, key=lambda x: x["start"], reverse=True)
    
    masked_text = text
    for item in sorted_results:
        info_type = item["type"]
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
    print("=== 마스킹 개별 함수 테스트 결과 ===")
    print("주민번호:", mask_rrn("990101-1234567"))
    print("외국인번호:", mask_rrn("050101-5678901"))
    print("전화번호:", mask_phone("010-1234-5678"))
    print("이메일:", mask_email("abcdef@domain.com"))
    print("계좌번호:", mask_bank_account("110-123-456789"))
    print("신용카드:", mask_credit_card("1234-5678-9012-3456"))
    print("IP주소:", mask_ip("192.168.0.1"))
    print("성명(3자):", mask_name("홍길동"))
    print("성명(2자):", mask_name("홍길"))
    print("주소:", mask_address("서울특별시 강남구 테헤란로 123"))
