import re

# 탐지할 개인정보 정규식 패턴 모음
PATTERNS = {
    "RRN": r'\b\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])-[1-4]\d{6}\b',  # 주민등록번호
    "PHONE": r'\b01[016789]-\d{3,4}-\d{4}\b',                             # 전화번호
    "EMAIL": r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',      # 이메일
    "BANK_ACCOUNT": r'\b\d{3,6}-\d{2,6}-\d{3,6}\b',                      # 계좌번호
    "CARD_NUMBER": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',           # 카드번호
    "IP_ADDRESS": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'                    # IP 주소
}

def detect_text(text):
    """텍스트 내 개인정보 위치 및 값 탐지"""
    results = []
    for info_type, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text):
            results.append({
                "type": info_type,
                "value": match.group(),
                "start": match.start(),
                "end": match.end()
            })
    return results

def detect_file(file_path):
    """파일(txt, log, py 등) 읽어서 탐지"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return detect_text(content)
    except Exception as e:
        print(f"파일 읽기 에러 ({file_path}): {e}")
        return []
