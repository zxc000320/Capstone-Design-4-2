"""엔진 B : 비정형 개인정보 탐지 (NER).

성명·주소·소속처럼 형식이 고정되지 않은 정보는 정규식만으로 잡을 수 없다.
본 모듈은 두 개의 하위 탐지기를 병렬로 돌리는 이중 구조를 취한다.

    LexiconNER  : 성씨 사전 + 행정구역 어휘 + 문맥 단서 기반 규칙 탐지
                  (의존성 없음, 항상 동작, 재현율 우선)
    ModelNER    : 사전학습 한국어 NER 모델 기반 탐지
                  (transformers 설치 시 활성화, 정밀도 우선)

두 탐지기가 같은 스팬을 지목하면 상호 보강(agreement boost)으로 신뢰도를
끌어올리고, 한쪽만 지목하면 해당 탐지기의 기본 신뢰도를 유지한다.
모델을 쓸 수 없는 환경에서도 파이프라인 전체가 동작하도록 설계했다.
"""

from __future__ import annotations

import re
from typing import Iterable, Protocol

from .types import Entity, EntityType

# ======================================================================
# 어휘 자원
# ======================================================================
SURNAMES_2 = ("남궁", "황보", "제갈", "선우", "독고", "사공", "서문", "동방")
SURNAMES_1 = (
    "김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민"
    "진지엄채원천방공현함변염여추노도소석선설마길연위표명기반왕금옥육인맹제모남탁국"
    "여진어은편용"
)

#: 성씨로 시작하지만 사람 이름일 가능성이 낮은 일반 어휘 (오탐 억제)
NAME_STOPWORDS = {
    "이번", "이후", "이전", "이상", "이하", "이내", "이외", "이때", "이날", "이용",
    "이유", "이상은", "한국", "한번", "한달", "한해", "한다", "정보", "정도", "정리",
    "정책", "정부", "김치", "박스", "오늘", "오후", "오전", "조건", "조사", "조직",
    "전체", "전화", "전송", "최근", "최소", "최대", "최초", "안내", "안전", "강의",
    "강사", "강화", "신청", "신규", "신고", "임시", "서비스", "서류", "문서", "문제",
    "유지", "유형", "배포", "표시", "차이", "나이", "주소", "주민", "고객", "남자",
    "노출", "백업", "권한", "장비", "장애", "황색", "구현", "구성", "구분", "민감",
    "진행", "지원", "지급", "엄격", "채용", "원본", "천만", "방법", "공개", "현재",
    "함께", "변경", "여부", "추가", "도구", "소스", "선택", "설정", "마감", "연동",
    "위험", "표준", "명시", "기능", "반영", "왕복", "금지", "옥상", "인증", "제공",
    "모두", "국내", "성명", "성능", "차량", "우선", "구축", "민원", "양식", "손실",
    "배치", "백만", "허용", "유효", "남은", "심사", "노트", "하위", "곽란", "석연",
    "선정", "설명", "마련", "명확", "기준", "반드시", "방식", "공지", "현황", "함수",
    "연락처", "이메일", "문의처", "소속", "조교", "서버", "제품", "서류", "담당",
    "회원", "결제", "환불", "첨부", "발췌", "일련", "번호", "금액", "기간", "대상",
    "조치", "검토", "승인", "요청", "등록", "변환", "저장", "출력", "입력", "확인",
    "관리", "운영", "개발", "설계", "분석", "평가", "보고", "작성", "제출", "수정",
    "전달", "처리", "공유", "완료", "예정", "관련", "참고", "문의", "발송", "회신",
    "통보", "접수", "반려", "취소", "연장", "적용", "해제", "생성", "삭제", "조회",
}

SIDO = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "강원도", "충청북도", "충청남도", "전라북도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)

ORG_SUFFIX = (
    "주식회사", "유한회사", "㈜", "대학교", "대학원", "대학", "고등학교", "중학교",
    "초등학교", "학교", "병원", "의원", "약국", "은행", "증권", "보험", "공사",
    "공단", "재단", "협회", "연구소", "연구원", "센터", "시청", "구청", "군청",
    "도청", "교육청", "경찰서", "소방서", "우체국", "지사", "본부", "사업단",
)

# ----------------------------------------------------------------------
# 문맥 단서 (가중치)
# ----------------------------------------------------------------------
LABEL_CUES = (  # 앞쪽 라벨 → 강한 근거
    "성명", "이름", "담당자", "작성자", "신청인", "신청자", "수신자", "발신자",
    "보호자", "환자명", "고객명", "회원명", "대표자", "계약자", "예금주", "수취인",
    "학생명", "지원자", "면담자", "상담자", "연락처", "명의자",
)
HONORIFIC_CUES = ("님", "씨", "군", "양", "귀하")     # 뒤쪽 호칭 → 강한 근거
TITLE_CUES = (
    "교수", "박사", "선생", "강사", "원장", "대표", "사장", "부사장", "이사",
    "부장", "차장", "과장", "대리", "주임", "팀장", "실장", "본부장", "연구원",
    "학생", "조교", "간호사", "의사", "변호사", "회계사",
)
JOSA_CUES = ("은", "는", "이", "가", "을", "를", "에게", "께", "와", "과", "의", "도")

_HANGUL = r"[가-힣]"

#: 이름 칸 바로 앞에 붙은 식별 라벨 (구분기호/공백만 사이에 허용)
_RE_ADJACENT_LABEL = re.compile(
    r"(?:" + "|".join(LABEL_CUES) + r")\s*[::\-|]?\s*$"
)


# ======================================================================
# 탐지기 인터페이스
# ======================================================================
class SubDetector(Protocol):
    name: str

    def detect(self, text: str) -> list[Entity]: ...


# ======================================================================
# 1) 사전·규칙 기반 탐지기
# ======================================================================
class LexiconNER:
    """의존성 없는 규칙 기반 한국어 개체명 탐지기."""

    name = "ner_lexicon"

    def __init__(self) -> None:
        sn1 = re.escape("".join(sorted(set(SURNAMES_1))))
        sn2 = "|".join(SURNAMES_2)
        self._re_person = re.compile(
            rf"(?<!{_HANGUL})(?:(?:{sn2})|[{sn1}]){_HANGUL}{{1,2}}(?!{_HANGUL})"
        )
        self._re_address = re.compile(
            r"(?:" + "|".join(sorted(SIDO, key=len, reverse=True)) + r")"
            r"(?:\s*[가-힣]{1,10}(?:시|군|구))?"
            r"(?:\s*[가-힣]{1,10}(?:읍|면|동|리))?"
            r"(?:\s*[가-힣A-Za-z0-9]{1,15}(?:대로|로|길))?"
            r"(?:\s*\d{1,5}(?:-\d{1,5})?(?:번길\s*\d{1,5}(?:-\d{1,5})?)?)?"
            r"(?:\s*\d{1,4}동)?(?:\s*\d{1,5}호)?"
        )
        self._re_roadonly = re.compile(
            r"(?<![가-힣])[가-힣A-Za-z0-9]{2,15}(?:대로|로|길)\s*\d{1,5}(?:-\d{1,5})?"
            r"(?:\s*\d{1,4}동)?(?:\s*\d{1,5}호)?"
        )
        suffix_alt = "|".join(sorted(ORG_SUFFIX, key=len, reverse=True))
        # 접미형: '정보통신산업대학교', '서울대병원'
        self._re_org = re.compile(
            rf"[가-힣A-Za-z0-9]{{2,20}}(?:{suffix_alt})"
        )
        # 접두형: '주식회사 한빛에듀', '㈜한빛에듀', '(주)한빛에듀'
        self._re_org_prefix = re.compile(
            r"(?:주식회사|유한회사|㈜|\(주\))\s?[가-힣A-Za-z0-9]{2,20}"
        )
        self._re_birth = re.compile(
            r"(?<![0-9])(?:19|20)\d{2}\s*[년./-]\s*\d{1,2}\s*[월./-]\s*\d{1,2}\s*일?"
        )

    # ------------------------------------------------------------------
    def detect(self, text: str) -> list[Entity]:
        out: list[Entity] = []
        out += self._detect_person(text)
        out += self._detect_address(text)
        out += self._detect_org(text)
        out += self._detect_birth(text)
        return out

    # ------------------------------------------------------------------
    def _detect_person(self, text: str) -> list[Entity]:
        result: list[Entity] = []
        for m in self._re_person.finditer(text):
            token = m.group(0)
            if token in NAME_STOPWORDS or token[:2] in NAME_STOPWORDS:
                continue

            conf, evidence = 0.38, ["사전:성씨 일치"]
            raw_right = text[m.end():m.end() + 8]
            # 창이 넓으면 앞 어절의 라벨이 엉뚱한 토큰까지 끌어올린다.
            left = text[max(0, m.start() - 10):m.start()].rstrip()
            right = raw_right.lstrip()
            has_label = any(cue in left for cue in LABEL_CUES)
            # 라벨이 구분기호만 사이에 두고 바로 앞에 붙은 경우
            # (예: "성명: 박서준") 는 서식상 이름 칸이 확실하다.
            adjacent_label = bool(_RE_ADJACENT_LABEL.search(left))

            # 뒤에 콜론이 붙으면 사람 이름이 아니라 양식의 필드 라벨일 확률이
            # 압도적으로 높다(연락처:, 이메일:, 소속: 등). 오탐의 최대 원인.
            if raw_right[:2].lstrip().startswith((":", "：")) and not has_label:
                conf -= 0.32
                evidence.append("억제:필드 라벨 형태")

            if has_label:
                conf += 0.32
                evidence.append("문맥:식별 라벨 인접")
            if right[:1] in HONORIFIC_CUES or right[:2] in HONORIFIC_CUES:
                conf += 0.26
                evidence.append("문맥:호칭 후행")
            if any(right.startswith(t) or left.endswith(t) for t in TITLE_CUES):
                conf += 0.18
                evidence.append("문맥:직함 인접")
            if right[:2] in JOSA_CUES or right[:1] in JOSA_CUES:
                conf += 0.06
                evidence.append("문맥:조사 후행")
            if adjacent_label:
                conf = max(conf, 0.88)
                evidence.append("문맥:식별 라벨 직결")
            if len(token) == 2:
                conf -= 0.06  # 2음절은 일반명사 충돌 가능성이 높음
            if token[-1] in ("를", "을", "은", "로", "와", "과", "의", "도"):
                conf -= 0.14  # 조사가 어절 끝에 붙은 일반 어절일 가능성
                evidence.append("억제:조사 결합 어절 추정")

            result.append(Entity(
                start=m.start(), end=m.end(), text=token,
                etype=EntityType.PERSON, confidence=min(conf, 0.95),
                engines={self.name}, evidence=evidence,
            ))
        return result

    def _detect_address(self, text: str) -> list[Entity]:
        result: list[Entity] = []
        for m in self._re_address.finditer(text):
            raw = m.group(0).strip()
            if len(raw) < 6:
                continue
            depth = sum(bool(re.search(p, raw)) for p in
                        (r"(시|군|구)\b|[가-힣](시|군|구)", r"(읍|면|동|리)",
                         r"(대로|로|길)", r"\d"))
            conf = min(0.40 + depth * 0.14, 0.94)
            result.append(Entity(
                start=m.start(), end=m.start() + len(raw), text=raw,
                etype=EntityType.ADDRESS, confidence=conf,
                engines={self.name},
                evidence=[f"사전:행정구역 체인(깊이 {depth})"],
            ))
        covered = [(e.start, e.end) for e in result]
        for m in self._re_roadonly.finditer(text):
            if any(s <= m.start() < e for s, e in covered):
                continue
            result.append(Entity(
                start=m.start(), end=m.end(), text=m.group(0).strip(),
                etype=EntityType.ADDRESS, confidence=0.58,
                engines={self.name}, evidence=["사전:도로명 단독 표기"],
            ))
        return result

    def _detect_org(self, text: str) -> list[Entity]:
        result: list[Entity] = []
        for m in self._re_org_prefix.finditer(text):
            raw = m.group(0).strip()
            result.append(Entity(
                start=m.start(), end=m.start() + len(raw), text=raw,
                etype=EntityType.ORG, confidence=0.82,
                engines={self.name}, evidence=["사전:법인 접두 표기"],
            ))
        covered = [(e.start, e.end) for e in result]
        for m in self._re_org.finditer(text):
            if any(s0 <= m.start() < e0 for s0, e0 in covered):
                continue
            raw = m.group(0).strip()
            result.append(Entity(
                start=m.end() - len(raw), end=m.end(), text=raw,
                etype=EntityType.ORG, confidence=0.70,
                engines={self.name}, evidence=["사전:기관 접미사"],
            ))
        return result

    def _detect_birth(self, text: str) -> list[Entity]:
        result = []
        for m in self._re_birth.finditer(text):
            left = text[max(0, m.start() - 12):m.start()]
            conf = 0.34
            evidence = ["사전:날짜 표기"]
            if any(c in left for c in ("생년월일", "생일", "출생", "생년")):
                conf = 0.90
                evidence.append("문맥:출생 관련 라벨")
            result.append(Entity(
                start=m.start(), end=m.end(), text=m.group(0),
                etype=EntityType.BIRTH, confidence=conf,
                engines={self.name}, evidence=evidence,
            ))
        return result


# ======================================================================
# 2) 사전학습 모델 기반 탐지기
# ======================================================================
#: 한국어 NER 모델의 라벨 → 내부 유형 매핑 (KLUE / NAVER 계열 공통)
MODEL_LABEL_MAP = {
    "PS": EntityType.PERSON, "PER": EntityType.PERSON, "PERSON": EntityType.PERSON,
    "LC": EntityType.ADDRESS, "LOC": EntityType.ADDRESS, "LOCATION": EntityType.ADDRESS,
    "OG": EntityType.ORG, "ORG": EntityType.ORG, "ORGANIZATION": EntityType.ORG,
    "DT": EntityType.BIRTH, "DAT": EntityType.BIRTH, "DATE": EntityType.BIRTH,
}


class ModelNER:
    """transformers 토큰 분류 파이프라인 어댑터.

    모델·라이브러리가 없으면 available=False 로 남고 빈 결과를 돌려준다.
    파이프라인 전체가 모델 가용성에 의존하지 않도록 하기 위한 장치다.
    """

    name = "ner_model"

    def __init__(self, model_id: str = "KPF/KPF-bert-ner",
                 min_score: float = 0.60) -> None:
        self.model_id = model_id
        self.min_score = min_score
        self.available = False
        self._pipe = None
        self._load()

    def _load(self) -> None:
        try:
            from transformers import pipeline  # type: ignore

            self._pipe = pipeline(
                "token-classification",
                model=self.model_id,
                aggregation_strategy="simple",
            )
            self.available = True
        except Exception:  # 라이브러리 미설치 / 모델 다운로드 실패 등
            self.available = False

    def detect(self, text: str) -> list[Entity]:
        if not self.available or self._pipe is None:
            return []
        try:
            raw = self._pipe(text)
        except Exception:
            return []

        out: list[Entity] = []
        for item in raw:
            label = str(item.get("entity_group", "")).upper()
            label = label.split("-")[-1]
            etype = MODEL_LABEL_MAP.get(label)
            score = float(item.get("score", 0.0))
            if etype is None or score < self.min_score:
                continue
            start, end = int(item["start"]), int(item["end"])
            out.append(Entity(
                start=start, end=end, text=text[start:end],
                etype=etype, confidence=min(score, 0.96),
                engines={self.name},
                evidence=[f"모델:{self.model_id}({label}, {score:.2f})"],
            ))
        return out


# ======================================================================
# 3) 이중 탐지 조정기
# ======================================================================
AGREEMENT_BONUS = 0.22   # 두 탐지기가 합치했을 때 신뢰도 가산
IOU_THRESHOLD = 0.60     # 동일 스팬으로 간주할 중첩 비율


def _iou(a: Entity, b: Entity) -> float:
    inter = max(0, min(a.end, b.end) - max(a.start, b.start))
    if inter == 0:
        return 0.0
    union = max(a.end, b.end) - min(a.start, b.start)
    return inter / union


class NerEngine:
    """LexiconNER + ModelNER 를 병렬 실행하고 합치 결과를 보강한다."""

    def __init__(self, use_model: bool = True, model_id: str | None = None) -> None:
        self.lexicon = LexiconNER()
        self.model = ModelNER(model_id) if (use_model and model_id) \
            else (ModelNER() if use_model else None)

    @property
    def model_available(self) -> bool:
        return bool(self.model and self.model.available)

    # ------------------------------------------------------------------
    def detect(self, text: str) -> list[Entity]:
        lex = self.lexicon.detect(text)
        mod = self.model.detect(text) if self.model else []
        return self._reconcile(lex, mod)

    # ------------------------------------------------------------------
    def _reconcile(self, lex: list[Entity], mod: list[Entity]) -> list[Entity]:
        """두 탐지기 결과를 대조해 합치/단독 판정을 부여한다."""
        merged: list[Entity] = []
        used_mod: set[int] = set()

        for a in lex:
            partner_idx, best = None, 0.0
            for i, b in enumerate(mod):
                if i in used_mod or b.etype is not a.etype:
                    continue
                score = _iou(a, b)
                if score > best:
                    partner_idx, best = i, score

            if partner_idx is not None and best >= IOU_THRESHOLD:
                b = mod[partner_idx]
                used_mod.add(partner_idx)
                # 더 넓은 스팬을 채택하고 신뢰도는 최댓값 + 합치 보너스
                start, end = min(a.start, b.start), max(a.end, b.end)
                merged.append(Entity(
                    start=start, end=end, text=a.text if a.length >= b.length else b.text,
                    etype=a.etype,
                    confidence=min(max(a.confidence, b.confidence) + AGREEMENT_BONUS, 0.99),
                    engines=a.engines | b.engines,
                    evidence=a.evidence + b.evidence + ["교차:사전-모델 합치"],
                ))
            else:
                merged.append(a)

        for i, b in enumerate(mod):
            if i not in used_mod:
                merged.append(b)

        return merged


def build_engine(use_model: bool = True, model_id: str | None = None) -> NerEngine:
    """NER 엔진 생성 헬퍼."""
    return NerEngine(use_model=use_model, model_id=model_id)


__all__ = ["LexiconNER", "ModelNER", "NerEngine", "build_engine",
           "SubDetector", "Iterable"]
