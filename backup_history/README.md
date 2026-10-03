# History Module

점검 및 처리 이력을 관리하는 모듈입니다.

## 주요 기능

- 개인정보 탐지 및 처리 결과 이력 저장
- 마스킹 처리본 경로 기록
- 개인정보 탐지 건수 기록
- 처리 성공/실패 상태 기록
- 저장된 점검 이력 조회

## record_history()

파일의 점검 및 처리 결과를 기록합니다.

### 입력

- `original_file`: 원본 파일 경로
- `output_path`: 마스킹 처리본 저장 경로
- `detection_count`: 개인정보 탐지 건수
- `processing_type`: 처리 방식
- `status`: 처리 상태
- `error_message`: 오류 메시지 (선택)

### 반환

- 기록된 이력 정보

### 예시

```python
from backup_history.history_manager import record_history

history = record_history(
    "sample.txt",
    "output/sample_masked.txt",
    2,
    "masking",
    "success"
)
```

## get_history()

저장된 점검 이력을 조회합니다.

### 반환

- 저장된 이력 목록
- 저장된 이력이 없으면 빈 리스트 `[]`

## 테스트

다음 명령으로 이력관리 모듈 테스트를 실행할 수 있습니다.

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```