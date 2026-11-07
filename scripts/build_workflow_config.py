"""Studio에 가져올 워크플로우 설정 파일을 만든다. 프롬프트는 docs/mission2-workflow.md에서 읽는다.

실행: python3 scripts/build_workflow_config.py
제출용 JSON은 이 파일이 아니라 Studio의 '워크플로우 설정 내보내기'로 받는다.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "submission" / "mission2" / "studio_import.json"
NAME = "컴학감동_미션2_실손보험 청구 서류 검증"
BLANK = " 문서에 없으면 추측하지 말고 빈 값."
ZERO = " 칸이 비어 있으면 0."
MONEY = " 쉼표 없는 정수(원)."
BOUNDARY = "[문서 경계] 입력은 청구 1건의 서류 묶음이며 앞 단계에서 문서별로 나뉜다. 이 문서에 적힌 값만 읽는다. 값을 계산하거나 다른 서류에서 가져오지 않는다."


def text(description):
    return {"type": "string", "description": description + BLANK}


def money(description, blank_zero=False):
    return {"type": "number", "description": description + MONEY + (ZERO if blank_zero else BLANK)}


COMMON = {"patient_name": text("환자 성명."), "provider_name": text("요양기관명 또는 상호.")}
SCHEMAS = {
    "receipt": ("영수증_추출", {
        **COMMON,
        "department": text("진료과목."),
        "visit_type": text("맨 위 체크된 진료 구분. 외래 또는 입원."),
        "receipt_no": text("영수증번호."),
        "visit_start": text("진료 시작일. YYYY-MM-DD."),
        "visit_end": text("진료 종료일. YYYY-MM-DD."),
        "copay_total": money("합계 행 ① 본인부담금."),
        "insurer_total": money("합계 행 ② 공단부담금."),
        "full_copay_total": money("합계 행 ③ 전액본인부담.", True),
        "noncovered_total": money("합계 행 ④ 비급여.", True),
        "cap_excess": money("⑤ 상한액 초과금.", True),
        "bill_total": money("진료비 총액 또는 약제비 총액."),
        "patient_total": money("환자부담 총액."),
    }),
    "itemized_bill": ("세부내역서_추출", {
        **COMMON,
        "grand_copay": money("맨 아래 '합계' 줄의 본인부담금. '계' 줄이 아니다."),
        "grand_insurer": money("맨 아래 '합계' 줄의 공단부담금."),
        "grand_full_copay": money("맨 아래 '합계' 줄의 전액본인부담.", True),
        "grand_noncovered": money("맨 아래 '합계' 줄의 비급여.", True),
        "grand_total": money("맨 아래 '합계' 줄의 총액."),
    }),
    "prescription": ("처방전_추출", {
        **COMMON,
        "issue_date": text("발급 연월일. YYYY-MM-DD."),
        "disease_code": text("질병분류기호. 비어 있으면 빈 값."),
    }),
    "evidence": ("증빙_추출", {
        **COMMON,
        "document_type": text("서류 제목. 예: 통원확인서, 진단서."),
        "disease_name": text("진단명 또는 병명."),
        "visit_start": text("진료 또는 입원 시작일. YYYY-MM-DD."),
        "visit_end": text("진료 또는 퇴원일. YYYY-MM-DD."),
    }),
}
CLASSES = [
    ("receipt", "진료비 또는 약제비 계산서·영수증. 항목별 본인부담금·공단부담금·비급여 표와 진료비 총액, 환자부담 총액이 있다. 재발행본도 영수증이다."),
    ("itemized_bill", "진료비 세부산정내역. 항목, 일자, 코드, 명칭, 횟수 표와 계, 끝수처리 조정금액, 합계 줄이 있다."),
    ("prescription", "처방전. 질병분류기호, 처방 의약품 표, 사용기간이 있다."),
    ("evidence", "통원확인서, 입퇴원확인서, 진료확인서, 진단서. 진단명이나 병명이 있다."),
    ("Other", "위에 없거나 읽을 수 없는 문서. 예: 카드 전표, 본인부담금 수납대장, 빈 페이지."),
]
OTHER_PROMPT = "이 문서는 청구 점검 대상 서류로 분류되지 않았다. 문서에 없는 값을 만들지 않는다. 한 줄로 쓴다: 문서 종류=<보이는 종류>, 이유=<분류되지 않은 이유>, 할 일=<무시 또는 담당자 확인>."
CLASSIFY, MERGE, DECIDE, OTHER = "청구서류-분류", "병합-1", "청구_판정", "미분류_안내"
REQUEST, MEMO = "보완_요청_문구", "담당자_확인_메모"
REQUEST_PROMPT = f"앞선 판정 [[{DECIDE}]] 결과가 보완 요청인 건이다. 고객에게 보낼 안내문을 쓴다. 문서에 없는 값을 만들지 않는다. 구성: 빠지거나 맞지 않는 서류와 값 / 다시 보내 주실 서류 / 제출 기한은 '담당자 지정'. 200자 이내, 존댓말. 보험금 지급 여부는 말하지 않는다."
MEMO_PROMPT = f"앞선 판정 [[{DECIDE}]] 결과가 검토 필요인 건이다. 담당자 확인 메모를 쓴다. 문서에 없는 값을 만들지 않는다. 구성: 검토 이유 / 원본에서 볼 서류와 칸 / 담당자가 정할 것. 200자 이내."


def prompt():
    document = (ROOT / "docs" / "mission2-workflow.md").read_text(encoding="utf-8")
    return re.search(r"```text\n(.*?)```", document, re.S).group(1).strip()


def build():
    edges = [{"source": {"nodeType": "parse"}, "target": {"nodeType": "classify", "name": CLASSIFY}}]
    for key, (name, _) in SCHEMAS.items():
        edges.append({"source": {"nodeType": "classify", "name": CLASSIFY}, "target": {"nodeType": "extract", "name": name}, "condition": {"conditionName": key}})
    edges.append({"source": {"nodeType": "classify", "name": CLASSIFY}, "target": {"nodeType": "instruct", "name": OTHER}, "condition": {"conditionName": "Other"}})
    for name, _ in SCHEMAS.values():
        edges.append({"source": {"nodeType": "extract", "name": name}, "target": {"nodeType": "merge", "name": MERGE}})
    edges.append({"source": {"nodeType": "merge", "name": MERGE}, "target": {"nodeType": "instruct", "name": DECIDE}})
    for value, name in (("보완 요청", REQUEST), ("검토 필요", MEMO)):
        edges.append({"source": {"nodeType": "instruct", "name": DECIDE}, "target": {"nodeType": "instruct", "name": name}, "condition": {"conditionName": value}})
    for number, edge in enumerate(edges):
        edge["id"] = f"e{number}"
    return {
        "kind": "studio.agent-config-draft",
        "agentConfig": {
            "agent_name": NAME,
            "pipelineType": "instruct",
            "documentParseConfiguration": {
                "modelName": "document-parse", "mode": "standard", "ocrMode": "force", "lang": "", "chartRecognition": False,
                "coordinates": True, "mergeMultipageTables": False, "outputFormats": ["html", "text"], "base64Encoding": ["figure"],
                "customName": "청구서류-파싱",
            },
            "documentClassifyConfiguration": {
                "modelName": "",
                "schema": {"type": "json_schema", "json_schema": {"name": "document-classify", "schema": {
                    "type": "string", "oneOf": [{"const": c, "description": d} for c, d in CLASSES]}}},
                "customName": CLASSIFY, "split": True, "splitCriteria": [{"criterion": "CONTINUITY", "description": ""}],
            },
            "informationExtractConfiguration": {
                "modelName": "",
                "schemas": [{"type": "json_schema", "json_schema": {"name": name, "schema": {"type": "object", "properties": properties}},
                             "mode": "standard", "modelName": "", "userSystemPrompt": BOUNDARY} for name, properties in SCHEMAS.values()],
                "categorySchemaMapping": {key: value[0] for key, value in SCHEMAS.items()},
                "location": True,
            },
            "instructConfiguration": {
                "nodes": [
                    {"name": DECIDE, "modelName": "", "prompt": prompt(), "enumEnabled": True, "enumValues": ["심사 진행", "보완 요청", "검토 필요"]},
                    {"name": REQUEST, "modelName": "", "prompt": REQUEST_PROMPT},
                    {"name": MEMO, "modelName": "", "prompt": MEMO_PROMPT},
                    {"name": OTHER, "modelName": "", "prompt": OTHER_PROMPT},
                ],
                "connectionMapping": {
                    REQUEST: {"targetType": "instruct", "instructNodeName": DECIDE},
                    MEMO: {"targetType": "instruct", "instructNodeName": DECIDE},
                    OTHER: {"targetType": "classify", "classifyClassName": "Other"},
                },
            },
            "pipelineEdges": edges,
        },
    }


OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUTPUT)
