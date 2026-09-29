# Backup and History Module

원본 파일 백업 및 점검·처리 이력을 관리하는 모듈입니다.

## 주요 기능

- 처리 전 원본 파일 백업
- 백업 실패 및 파일 미존재 예외 처리
- 개인정보 탐지 및 처리 결과 이력 저장
- 저장된 점검 이력 조회

## backup_file()

원본 파일을 `backups` 디렉터리에 백업합니다.

### 입력

- `file_path`: 백업할 원본 파일 경로

### 반환

- 생성된 백업 파일의 경로

### 예시

```python
from backup_history.backup_manager import backup_file

backup_path = backup_file("sample.txt")
print(backup_path)
```

원본 파일이 존재하지 않으면 `FileNotFoundError`가 발생합니다.

## record_history()

파일의 점검 및 처리 결과를 기록합니다.

### 입력

- `original_file`: 원본 파일 경로
- `backup_path`: 백업 파일 경로
- `detection_count`: 개인정보 탐지 건수
- `processing_type`: 처리 방식
- `status`: 처리 상태
- `error_message`: 오류 메시지 (선택)

### 반환

- 기록된 이력 정보

## get_history()

저장된 점검 이력을 조회합니다.

### 반환

- 저장된 이력 목록
- 저장된 이력이 없으면 빈 리스트 `[]`

## 테스트

다음 명령으로 백업 및 이력관리 모듈 테스트를 실행할 수 있습니다.

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```