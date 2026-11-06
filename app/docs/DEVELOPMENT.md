# 메인 파이프라인·실행 프로그램 (담당: 김진웅)

## 실행 (Windows)
맨 위 폴더에서 더블클릭:
1. `setup.bat` — 처음 한 번만. `.venv` 폴더를 만들고 필요한 라이브러리를 그 안에 설치
2. `run.bat` — 프로그램(GUI) 실행

명령어로 실행할 때 (맨 위 폴더에서):
```
.venv\Scripts\python app/gui.py                              # GUI
.venv\Scripts\python app/main.py app/samples/sample.txt      # 파일 하나 마스킹
.venv\Scripts\python app/main.py 폴더경로/ --check            # 점검만
.venv\Scripts\python app/tests/run_tests.py                  # 테스트
```
처리본은 맨 위 폴더의 `output/`(또는 `--out`)에 `원본이름_masked.확장자`로 저장되며, 원본은 수정하지 않습니다.
`.venv/`, `output/`은 `.gitignore`에 들어 있어 깃허브에 올라가지 않습니다.

## 폴더 구성
```
저장소/
├─ regex_detector.py   (박주아)  ← 수정하지 않음
├─ masking.py          (최동명)  ← 수정하지 않음
├─ app/                (김진웅)  ← 파이프라인·실행 프로그램 전부
├─ setup.bat, run.bat  설치·실행 (더블클릭)
├─ requirements.txt    필요한 라이브러리 목록
├─ .venv/              설치된 라이브러리 (setup.bat이 생성)
└─ output/             처리 결과 (실행하면 생성)
```
팀원 모듈이 업데이트되면 맨 위 폴더의 파일만 바꾸면 되고, app 폴더는 그대로 둡니다.

## app 폴더 파일
| 파일 | 내용 |
|---|---|
| `main.py` | CLI |
| `gui.py` | GUI (tkinter) |
| `pipeline.py` | 처리 순서 실행, 탐지 결과 병합, 모듈 결과 형식 검사, 폴더 일괄 처리 |
| `adapters.py` | 팀원 모듈 호출 및 입출력 형식 변환 |
| `fileio/` | 파일 읽기·처리본 저장 |
| `tests/` | 파이프라인·연결 코드·파일 입출력 테스트 |

`regex_detector.py`(박주아), `masking.py`(최동명)는 **수정하지 않고 그대로 호출**합니다.

## 처리 순서
```
파일 읽기 → 정규식·NER 탐지 → 형식 검사 → 결과 병합 → 마스킹 → 처리본 저장
```
- NER 탐지, 점검·처리 이력 기록은 해당 모듈이 들어오면 `adapters.py` / `pipeline.py`에 연결 예정

## 모듈 연결 (adapters.py)
팀원 모듈의 현재 입출력을 파이프라인 공통 형식으로 바꿔줍니다. 모듈 형식이 바뀌면 이 파일만 고치면 됩니다.

| 모듈 | 호출하는 함수 | 변환 |
|---|---|---|
| 정규식 탐지 | `detect_text(text)` | 문단·줄마다 호출, `value` → `text`, `seg_id`·`source` 추가 |
| 마스킹 | `apply_masking(text, results)` | 문단·줄마다 호출, 모듈 형식(`value`, 모듈 타입 이름)으로 되돌려 전달 |

타입 이름 변환: `BANK_ACCOUNT` ↔ `ACCOUNT`, `CARD_NUMBER` ↔ `CARD`

## 파이프라인 공통 형식
**Segment** (파일 읽기 결과)
```python
{"seg_id": "line_3", "text": "...", "meta": {"location": "3행", ...}}   # docx는 "para_문단번호"
```

**Entity** (탐지 결과)
```python
{"seg_id": "line_3", "start": 15, "end": 29, "type": "RRN",
 "text": "990101-1234567", "source": "regex"}
```
- `start`, `end`: `segment["text"][start:end]` 기준 (end는 포함 안 함)
- `text`는 개인정보 원문이므로 로그·파일에 저장하지 않음
- 형식이 틀리면 `[모듈 형식 오류] [regex_detector] 3번째 결과: 키 없음 [...]`처럼 표시 (원문은 표시 안 함)

## 결과 병합 규칙
1. 위치가 겹치면 하나만 남김
2. 정형 정보(RRN, PHONE, EMAIL, ACCOUNT, CARD, IP_ADDRESS)는 정규식 결과 우선
3. 그 외에는 더 긴 구간을 남김

## 지원 형식
- docx: 본문·표(중첩 포함)·머리글·바닥글. 바뀐 글자만 교체해 서식 유지, 가려진 하이퍼링크는 링크 주소까지 삭제
- 텍스트 계열: txt, log, md, csv, json, xml, yml, sql, 소스코드(py, java, js, c, cpp 등). 인코딩(utf-8/cp949)·줄바꿈(LF/CRLF) 유지
