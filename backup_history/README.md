# History Module

점검 및 처리 이력을 관리하는 모듈입니다.

`backup_history`는 기존 import 경로를 유지하기 위한 폴더 이름입니다.
별도 백업 및 복구 기능은 제공하지 않습니다.
이 모듈은 원본과 처리본을 수정하지 않고, 전달받은 처리 결과만 기록합니다.
원본을 덮어쓰지 않고 별도 처리본을 생성하는 작업은 메인 파이프라인에서 수행합니다.

## 주요 기능

- 개인정보 탐지 및 처리 결과 이력 저장
- 마스킹 처리본 경로 기록
- 개인정보 탐지 건수 기록
- 처리 성공/실패 상태 기록
- 저장된 점검 이력 조회

이력은 프로그램 실행 디렉터리 기준 `logs/history.jsonl`에 UTF-8 JSONL 형식으로
한 줄씩 누적됩니다. `logs` 폴더가 없으면 자동으로 생성합니다.

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

### 메인 파이프라인 연동

처리본 저장까지 완료한 다음 위 예시처럼 `status="success"`로 기록합니다.
탐지 또는 처리본 저장에 실패하면 다음처럼 실패 이력을 남길 수 있습니다.

```python
record_history(
    original_file="sample.txt",
    output_path="output/sample_masked.txt",
    detection_count=2,
    processing_type="masking",
    status="failed",
    error_message="처리본 저장 실패",
)
```

실패 이력의 `output_path`는 저장을 시도한 경로이며, 파일의 존재를 보장하지 않습니다.
`detection_count`는 호출하는 쪽에서 집계한 탐지 건수를 전달합니다.
오류 메시지에는 탐지된 개인정보 원문이나 문서 전체를 넣지 않습니다.
이력 파일 자체에 쓰지 못한 경우에는 예외가 발생하므로 호출하는 쪽에서 처리합니다.

## get_history()

저장된 점검 이력을 조회합니다.

### 반환

- 저장된 이력 목록
- 저장된 이력이 없으면 빈 리스트 `[]`

기록한 순서대로 반환합니다. 파일 내 빈 줄은 무시하지만,
손상된 JSON 행이 있으면 예외가 발생합니다.

## 테스트

다음 명령으로 이력관리 모듈 테스트를 실행할 수 있습니다.

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

각 테스트는 별도의 임시 폴더를 사용하므로 기존 `logs` 폴더를 수정하거나 삭제하지 않습니다.
성공 및 실패 이력, 빈 이력, 여러 건의 누적 저장·조회,
이력 기록 전후 원본·처리본 파일 보존을 확인합니다.
