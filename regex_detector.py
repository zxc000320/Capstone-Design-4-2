import re

class RegexDetector:
    def __init__(self):
        # 주요 개인정보 정규식 패턴 정의
        self.patterns = {
            # 주민등록번호: 앞 6자리 - 뒤 7자리 (1, 2, 3, 4로 시작)
            "rrn": r'\b\d{6}-[1-4]\d{6}\b',
            
            # 전화번호: 010-XXXX-XXXX 또는 02-XXX-XXXX 등
            "phone": r'\b01[016789]-\d{3,4}-\d{4}\b',
            
            # 이메일주소
            "email": r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
            
            # 계좌번ㄴ호 
            "bank_account": r'\b\d{3,6}-\d{2,6}-\d{3,6}\b'
        }

    def detect(self, text):
        """
        입력된 텍스트에서 정규식 패턴에 해당하는 개인정보를 탐지합니다.
        """
        results = {}
        for info_type, pattern in self.patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                results[info_type] = matches
        return results

# 간단한 동작 테스트
if __name__ == "__main__":
    sample_text = """
    안녕하세요. 홍길동입니다.
    주민등록번호는 980101-1234567 입니다.
    연락처는 010-1234-5678 이며, 이메일은 test@example.com 입니다.
    계좌번호: 123-456-789012
    """
    
    detector = RegexDetector()
    detected_info = detector.detect(sample_text)
    
    print("=== 탐지 결과 ===")
    print(detected_info)
