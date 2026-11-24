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
    # 기관·금융 기관명에 자주 쓰여 이름으로 오인되는 어휘
    "연락", "국민", "한글", "우리", "하나", "신한", "기업", "농협", "수협",
    "새마을", "한국", "대한", "서울", "경기", "부산", "대구", "광주", "제주",
    "고객센터", "상담", "안심", "보안", "정산", "청구", "납부", "가입", "해지",
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
#: 이름 어절에 바로 붙는 호칭. 붙어 있으면 이름임이 사실상 확정된다.
HONORIFIC_SUFFIXES = ("귀하", "님", "씨", "군", "양")

#: 이름 다음 어절 전체가 호칭인 경우 ("남궁민수 고객님", "김하늘 님께")
HONORIFIC_WORDS = (
    "님", "씨", "귀하", "고객님", "회원님", "환자분", "환자님", "선생님",
    "교수님", "원장님", "대표님", "사장님", "팀장님", "부장님", "과장님",
    "차장님", "주임님", "실장님", "의원님", "학부모님", "보호자님", "본인",
)

#: 이름 뒤에 붙을 수 있는 조사. 긴 것부터 맞춰본다.
PARTICLES = (
    "께서는", "에게서", "께서", "에게", "이가", "에서", "으로", "부터", "까지",
    "은", "는", "이", "가", "을", "를", "의", "와", "과", "도", "께", "만",
    "에", "로",
)
TITLE_CUES = (
    "교수", "박사", "선생", "강사", "원장", "대표", "사장", "부사장", "이사",
    "부장", "차장", "과장", "대리", "주임", "팀장", "실장", "본부장", "연구원",
    "학생", "조교", "간호사", "의사", "변호사", "회계사",
)
_HANGUL = r"[가-힣]"

#: 이름 칸 바로 앞에 붙은 식별 라벨. 라벨 뒤에 조사나 구분기호가 하나 오는
#: 것까지만 허용한다("성명:", "예금주는"). 창을 넓게 잡으면 라벨이 엉뚱한
#: 뒷 어절까지 끌어올려 "담당자 이영희님께 연락"의 '연락'을 이름으로 만든다.
_RE_ADJACENT_LABEL = re.compile(
    r"(?:" + "|".join(LABEL_CUES) + r")(?:은|는|이|가|의|을|를)?\s*[::\-|]?\s*$"
)

#: 한글 어절 하나
_RE_HANGUL_RUN = re.compile(r"[가-힣]+")
_SN1_SET = frozenset(SURNAMES_1)

#: 어절에서 이름을 떼고 남은 꼬리의 종류. 선호 순위를 함께 둔다.
_KIND_RANK = {"honorific": 3, "none": 2, "particle": 1}


def _suffix_kind(suf: str) -> str | None:
    """이름 뒤에 남은 꼬리를 분류한다. 해석할 수 없으면 None."""
    if not suf:
        return "none"
    for h in HONORIFIC_SUFFIXES:
        if suf == h:
            return "honorific"
        if suf.startswith(h) and suf[len(h):] in PARTICLES:
            return "honorific"
    if suf in PARTICLES:
        return "particle"
    return None


def _parse_name(word: str) -> tuple[str, str, bool] | None:
    """한글 어절을 (이름, 꼬리종류, 복성여부)로 분해한다.

    이름 뒤에 호칭이나 조사가 붙어 있어도 이름만 떼어낸다. 단순 경계
    검사만 하면 '이영희님께'처럼 호칭이 붙은 순간 이름을 통째로 놓친다.
    """
    cands: list[tuple[str, str, bool]] = []
    for sn in SURNAMES_2:
        if word.startswith(sn):
            for glen in (2, 1):
                if len(word) >= len(sn) + glen:
                    name = word[:len(sn) + glen]
                    kind = _suffix_kind(word[len(name):])
                    if kind:
                        cands.append((name, kind, True))
    if word[0] in _SN1_SET:
        for glen in (2, 1):
            if len(word) >= 1 + glen:
                name = word[:1 + glen]
                kind = _suffix_kind(word[len(name):])
                if kind:
                    cands.append((name, kind, False))
    if not cands:
        return None
    # 호칭이 붙은 해석 > 꼬리 없는 해석 > 조사만 붙은 해석, 복성 우선
    return max(cands, key=lambda c: (_KIND_RANK[c[1]], c[2], len(c[0])))


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
        self._re_address = re.compile(
            r"(?:" + "|".join(sorted(SIDO, key=len, reverse=True)) + r")"
            # 시/군/구는 두 단계까지 이어진다('성남시 분당구'). 한 단계만
            # 허용하면 주소가 중간에서 끊겨 '분당구'가 그대로 노출된다.
            r"(?:\s*[가-힣]{1,10}(?:시|군|구)){0,2}"
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
        orgs = self._detect_org(text)
        # 기관명 안쪽에 걸린 이름 후보는 버린다. 그대로 두면 유형 우선순위에서
        # 성명이 소속기관을 이겨, 가리지 않아야 할 기관명이 가려진다.
        persons = [p for p in self._detect_person(text)
                   if not any(o.start <= p.start and p.end <= o.end for o in orgs)]
        out: list[Entity] = []
        out += persons
        out += self._detect_address(text)
        out += orgs
        out += self._detect_birth(text)
        return out

    # ------------------------------------------------------------------
    def _detect_person(self, text: str) -> list[Entity]:
        """어절 단위로 이름을 찾는다.

        점수는 '직접 근거'에서만 나온다. 호칭이 붙었는지, 바로 앞 칸이
        식별 라벨인지, 직함이 붙었는지가 전부다. 근처에 전화번호가 있다는
        사실만으로는 이름이 되지 않는다(은행명 '국민'이 계좌번호 옆에
        있다고 사람이 되지는 않는다).
        """
        result: list[Entity] = []
        for m in _RE_HANGUL_RUN.finditer(text):
            word = m.group(0)
            parsed = _parse_name(word)
            if parsed is None:
                continue
            name, kind, compound = parsed
            if name in NAME_STOPWORDS or name[:2] in NAME_STOPWORDS:
                continue

            start_i = m.start()
            end_i = start_i + len(name)
            conf, evidence = 0.40, ["사전:성씨 일치"]

            raw_right = text[m.end():m.end() + 10]
            left = text[max(0, start_i - 12):start_i].rstrip()
            next_word = raw_right.strip().split(" ")[0] if raw_right.strip() else ""
            adjacent_label = bool(_RE_ADJACENT_LABEL.search(left))

            # 어절에 호칭이 바로 붙음: '이영희님께', '김가상님'
            if kind == "honorific":
                conf += 0.48
                evidence.append("문맥:호칭 결합")
            # 다음 어절 전체가 호칭: '남궁민수 고객님', '김하늘 님께'
            elif next_word and (
                next_word in HONORIFIC_WORDS
                or any(next_word.startswith(h) and
                       _suffix_kind(next_word[len(h):]) is not None
                       for h in HONORIFIC_WORDS)
            ):
                conf += 0.40
                evidence.append("문맥:호칭 어절 후행")

            if compound:
                conf += 0.10          # 남궁·황보 등 복성은 일반명사와 겹치지 않음
                evidence.append("사전:복성")

            if any(next_word.startswith(t) for t in TITLE_CUES) or \
               any(left.endswith(t) for t in TITLE_CUES):
                conf += 0.25
                evidence.append("문맥:직함 인접")

            if len(name) == 2:
                conf -= 0.06          # 2음절은 일반명사와 충돌하기 쉽다

            # 뒤에 콜론이 붙으면 이름이 아니라 양식의 필드 이름이다.
            if raw_right.lstrip()[:1] in (":", "：") and not adjacent_label:
                conf -= 0.35
                evidence.append("억제:필드 라벨 형태")

            if adjacent_label:
                conf = max(conf, 0.90)
                evidence.append("문맥:식별 라벨 직결")

            result.append(Entity(
                start=start_i, end=end_i, text=name,
                etype=EntityType.PERSON,
                confidence=max(min(conf, 0.95), 0.02),
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
