"""정답지를 '두 경로가 모두 정답을 읽은' 추출 결과로 바꾼다. 규칙 점수와 테스트에 쓴다."""


def answer_to_extract(answer):
    documents = []
    for number, doc in enumerate(answer["documents"], 1):
        documents.append({
            "doc_id": f"d{number}",
            "file_name": doc["file_name"],
            "type": doc["type"],
            "form_no": doc.get("form_no"),
            "type_confidence": 1.0,
            "flags": doc.get("flags", []),
            "fields": [{"key": f["key"], "path_a": {"value": f["value"]}, "path_b": {"value": f["value"]}}
                       for f in answer["fields"] if f["file_name"] == doc["file_name"]],
        })
    return {"claim_id": answer["case_id"], "claim_type": answer["claim_type"], "documents": documents}
