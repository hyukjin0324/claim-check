# JSON 형식과 판정 코드 사용법

스키마는 `schema/`, 실제 예시는 `examples/case_07.*.json`에 있다.

## 누가 무엇을 쓰나

| 역할 | 파일 | 형식 |
| --- | --- | --- |
| ① 데이터·정답지 | `answers/case_NN.json` | `schema/answer.schema.json` |
| ② 추출 | `outputs/extract/case_NN.json` | `schema/extract_output.schema.json` |
| ③ 검증 규칙 | `outputs/judge/case_NN.json` | `schema/judge_output.schema.json` |
| ④ 채점·리포트 | 위 파일을 읽음 | 정답지는 `file_name`, 판정 결과는 `doc_id`로 서류를 찾는다. `documents`에 둘의 대응이 있다 |

필드 키 목록은 `schema/fields.json`에 있다. 금액은 쉼표 없는 정수, 날짜는 `YYYY-MM-DD`, 값이 없으면 `null`이다.

## ②가 만들 추출 결과

```json
{
  "claim_id": "case_07",
  "claim_type": "outpatient",
  "documents": [{
    "doc_id": "d1",
    "file_name": "case_07_doc1_receipt",
    "type": "receipt",
    "form_no": "7",
    "type_confidence": 0.97,
    "flags": [],
    "fields": [{
      "key": "copay_total",
      "path_a": {"value": 4200, "block_id": "d1_cell_19", "ocr_confidence": 0.97},
      "path_b": {"value": 4800, "quote": "4,800"}
    }]
  }]
}
```

- 경로 B는 경로 A의 OCR을 쓰지 않고 원본 파일을 따로 읽는다. 같은 OCR을 쓰면 두 경로를 비교하는 의미가 없다.
- 찾지 못한 값은 추측하지 말고 `null`로 둔다.
- 잘린 문서는 `flags`에 `CROPPED`, 종류가 애매한 문서는 `UNKNOWN_DOC`을 넣는다.
- 영수증의 진료과는 `department` 키로 뽑는다. D4 판단에 쓴다.

## 실행

```bash
python3 -m judge outputs/extract/case_01.json -o outputs/judge/case_01.json
```

②의 결과가 없으면 `fixtures/`의 가짜 추출 결과로 시험한다.

| 파일 | 내용 | 나오는 결론 |
| --- | --- | --- |
| `fake_agree` | 두 경로 값이 모두 같음 | `proceed` |
| `fake_checksum` | 본인부담금이 다르고 검산식으로 고름 | `proceed` |
| `fake_unstable` | 공단부담금이 쓰이는 식의 다른 칸도 흔들림 | `needs_review` |

## 판정 점수와 테스트

```bash
python3 scripts/score_rules.py
```

```bash
python3 -m unittest discover tests
```

`score_rules.py`는 정답 값을 두 경로에 똑같이 넣고 판정 규칙만 채점한다. OCR과 추출의 정확도는 재지 않는다. 또 지금 정답지는 판정 코드와 같은 규칙으로 만든 초안이라, 만점이어도 규칙 해석이 옳다는 증거는 아니다. 실제 서류를 넣어 다시 확인해야 한다.

정답지 값을 바꾸면 `scripts/generate_case_drafts.py`를 고친 뒤 다시 실행한다. 판정 결과 형식이나 예시가 바뀌면 `python3 scripts/make_examples.py`로 예시를 다시 만든다.

필요 서류 금액 기준과 OCR 신뢰도 기준은 `config/required_docs.json`에서 바꾼다.
