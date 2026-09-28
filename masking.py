import re

def mask_rrn(rrn_str: str) -> str:
    """주민등록번호 마스킹 (예: 900101-1******)"""
    pattern = r'(\d{6})[-_ ]?([1-4])\d{6}'
    return re.sub(pattern, r'\1-\2******', rrn_str)

if __name__ == "__main__":
    print(mask_rrn("주민번호: 990101-1234567"))