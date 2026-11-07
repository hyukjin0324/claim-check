# 미션 2 워크플로우 입력 자료

미션 2는 v0를 낸다. Parse → Classify → Extract ×4 → Merge → Instruct(결정) → 후속 문구 순서로 돌리고, Validate는 최종 제출 전에 넣는다. Validate는 서류가 빠진 칸 규칙을 어떻게 판정하는지 아직 시험하지 못했다.

## 시험 순서

1. `submission/mission2/데이터셋/`의 set01로 Parse → Extract(영수증) → Instruct만 먼저 돌린다.
2. Classify와 Merge를 넣고 set04로 서류 4종을 시험한다.
3. set01~05를 모두 돌려 정답지와 비교한다.
4. 같은 파일을 다시 돌려 `decision`이 그대로인지 본다.

실제 서류는 올리지 않는다. 샘플 문서가 공개될 수 있다.

## Parse

OCR을 켠다. 합쳐진 표를 읽어야 하니 좌표(`coordinates`)도 켠다.

## Classify

| 클래스 | 설명 |
| --- | --- |
| `receipt` | 진료비 계산서·영수증. 항목별 본인부담금·공단부담금·비급여 표와 진료비 총액, 환자부담 총액이 있다. 재발행본도 영수증이다 |
| `itemized_bill` | 진료비 세부산정내역. 항목, 코드, 명칭, 횟수와 계, 끝수처리 조정금액, 합계 줄이 있다 |
| `prescription` | 처방전. 질병분류기호, 처방 의약품, 사용기간이 있다 |
| `evidence` | 통원확인서, 입퇴원확인서, 진단서. 진단명이나 병명이 있다 |
| `Other` | 위에 없는 문서. 카드 전표, 수납대장 등 |

분할은 `낱장 분리`로 둔다. `문서 자동 탐지`는 같은 서식 영수증 2장을 한 문서로 묶어 중복을 놓쳤다. 여러 쪽 세부내역서는 쪽마다 나뉘므로 최종 제출 전에 다시 시험한다.

## Extract

모든 항목의 설명에 "문서에 없으면 추측하지 말고 빈 값"을 넣는다. 금액은 쉼표 없는 정수, 날짜는 `YYYY-MM-DD`다.

**영수증_추출 (`receipt`)**

| 항목 | 유형 | 설명 |
| --- | --- | --- |
| `patient_name` | String | 환자 성명 |
| `provider_name` | String | 상호 |
| `department` | String | 진료과목 |
| `visit_type` | String | 외래, 입원 중 체크된 값 |
| `receipt_no` | String | 영수증번호 |
| `visit_start` | String | 진료 시작일 |
| `visit_end` | String | 진료 종료일 |
| `copay_total` | Number | 합계 행 ① 본인부담금 |
| `insurer_total` | Number | 합계 행 ② 공단부담금 |
| `full_copay_total` | Number | 합계 행 ③ 전액본인부담. 비면 0 |
| `noncovered_total` | Number | 합계 행 ④ 비급여. 비면 0 |
| `cap_excess` | Number | ⑤ 상한액 초과금. 비면 0 |
| `bill_total` | Number | 진료비 총액 |
| `patient_total` | Number | 환자부담 총액 |

**세부내역서_추출 (`itemized_bill`)**

| 항목 | 유형 | 설명 |
| --- | --- | --- |
| `patient_name`, `provider_name` | String | 환자 성명, 요양기관 |
| `grand_copay` | Number | 합계 줄 본인부담금. `계`가 아니다 |
| `grand_insurer` | Number | 합계 줄 공단부담금 |
| `grand_full_copay` | Number | 합계 줄 전액본인부담 |
| `grand_noncovered` | Number | 합계 줄 비급여 |
| `grand_total` | Number | 합계 줄 총액 |

**처방전_추출 (`prescription`)**: `patient_name`, `provider_name`, `issue_date`, `disease_code`(환자가 요구하면 비어 있을 수 있음)

**증빙_추출 (`evidence`)**: `document_type`, `patient_name`, `provider_name`, `disease_name`, `visit_start`, `visit_end`

Number 유형을 Studio에서 고를 수 없으면 String으로 두고 설명에 숫자만 적으라고 쓴다.

## Instruct(결정)

타입은 "생성하고 결정도 내리기", 값은 `심사 진행`, `보완 요청`, `검토 필요`.

```text
너는 실손보험 보상 담당자의 청구 서류 1차 점검을 돕는다. 앞 단계에서 추출한 값만 쓴다. 문서에 없는 값을 만들지 않는다. 보험금 지급 여부는 판단하지 않는다.

입력은 청구 1건의 서류 묶음이다. 어떤 서류의 추출 결과가 비어 있으면 제출되지 않은 것으로 본다. 영수증이 여러 장이면 모두 살핀다.

아래 순서로 판단하고, 앞 단계에서 걸리면 다음 단계의 결과로 cause를 바꾸지 않는다.

1단계 읽기 점검 (영수증마다)
A = copay_total + insurer_total + full_copay_total + noncovered_total. A가 bill_total과 같은지 본다.
B = copay_total - cap_excess + full_copay_total + noncovered_total. B가 patient_total과 같은지 본다.
빈 full_copay_total, noncovered_total, cap_excess는 0으로 계산한다.
식이 깨지거나 bill_total, patient_total, 환자 이름을 읽지 못했으면 decision은 검토 필요, cause는 읽기 오류다.

2단계 중복
요양기관과 receipt_no가 같은 영수증이 2장 이상이면 decision은 보완 요청, cause는 중복 제출이다. 이후 금액은 한 장만 센다.

3단계 서류 비교 (1단계를 통과한 값끼리)
세부내역서가 있으면 grand_copay, grand_insurer, grand_full_copay, grand_noncovered, grand_total을 영수증 copay_total, insurer_total, full_copay_total, noncovered_total, bill_total과 각각 비교한다.
환자 이름과 요양기관을 서류끼리 비교한다.
다르면 decision은 보완 요청, cause는 서류 불일치다. mismatches에 다른 값의 이름을 적는다. 금액은 본인부담금 합계, 공단부담금 합계, 전액본인부담 합계, 비급여 합계, 진료비 총액 중에서, 그 밖에는 환자 이름, 요양기관으로 적는다.

4단계 필요 서류
영수증이 없으면 decision은 보완 요청, cause는 서류 누락이다. missing_documents에 진료비 영수증을 적는다.
환자부담 합계는 중복을 뺀 영수증 patient_total의 합이다.
처방전 조건: disease_code 값이 있는 prescription 문서가 있다.
증빙 조건: disease_name 값이 있는 evidence 문서가 있다.
진단서 조건: document_type에 진단서가 들어 있고 disease_name 값이 있는 evidence 문서가 있다.

영수증 visit_type이 입원이면 입원 기준만 적용한다.
- 세부내역서가 없으면 missing_documents에 세부내역서를 적는다.
- 환자부담 합계가 500,000원 이하면 증빙 조건이 맞아야 하고, 없으면 진단서를 적는다.
- 환자부담 합계가 500,000원을 넘으면 진단서 조건이 맞아야 하고, 없으면 진단서를 적는다.
- 빠진 서류를 모두 적는다. 적은 서류가 있으면 decision은 보완 요청, cause는 서류 누락이다.

그 밖에는 통원 기준을 적용한다. 아래를 위에서부터 보고, 처음 맞는 한 줄만 적용한다.
1. 영수증 department가 산부인과, 항문외과, 비뇨기과, 비뇨의학과, 피부과 중 하나면 금액과 상관없이 증빙 조건만 본다. 맞으면 통과다. 맞지 않으면 decision은 검토 필요, cause는 서류 누락, missing_documents는 비워 둔다.
2. 환자부담 합계가 100,000원을 넘는데 증빙 조건이 맞지 않으면 decision은 검토 필요, cause는 서류 누락이다. 처방전 조건도 맞지 않으면 missing_documents에 처방전을 적고, 맞으면 비워 둔다. 처방전이 있어도 이 줄을 적용한다. 보완 요청으로 판정하지 않는다.
3. 환자부담 합계가 30,000원을 넘는데 처방전 조건과 증빙 조건이 모두 맞지 않으면 decision은 보완 요청, cause는 서류 누락, missing_documents에 처방전을 적는다.
4. 그 밖에는 통과다.

5단계
1~4단계에서 어떤 판정도 나오지 않았을 때만 decision은 심사 진행, cause는 없음이다.
환자부담 합계 30,000원 이하 통원은 진료과 예외가 아니면 영수증만으로 충분하다.
제출되지 않은 서류는 조건이 맞지 않는 것으로 본다. 제출 여부를 알 수 없다고 판단하지 않는다.
decision이 심사 진행이면 missing_documents와 mismatches는 모두 []다. decision이 보완 요청이고 cause가 서류 누락이면 missing_documents는 비어 있으면 안 된다.

판정을 정하기 전에 reason을 먼저 쓴다. 아래 키 7개를 이 순서로 한 줄에 하나씩 쓴다.
patient_name: <영수증 환자 이름>
provider_name: <영수증 요양기관>
reason: <읽기 점검 결과, 중복 여부, 서류 비교 결과(다른 값 또는 같음), 통원 또는 입원, 환자부담 합계, 처방전 조건 맞음/안 맞음, 증빙 조건 맞음/안 맞음, 적용한 단계와 줄을 이 순서로 먼저 적고 판정 근거 1~2문장. 실제 금액 포함>
decision: <reason에 맞는 값. 심사 진행 | 보완 요청 | 검토 필요>
cause: <없음 | 읽기 오류 | 서류 불일치 | 서류 누락 | 중복 제출>
missing_documents: <JSON 문자열 배열. 예: ["처방전"]. 없으면 []>
mismatches: <JSON 문자열 배열. 예: ["비급여 합계", "진료비 총액"]. 없으면 []>
마지막 줄에 decision 값만 한 번 더 쓴다.
```

## 결과 비교

| 파일 | 기대 decision | 기대 cause | 목록 키 |
| --- | --- | --- | --- |
| set01 | 심사 진행 | 없음 | 모두 `[]` |
| set02 | 심사 진행 | 없음 | 모두 `[]` |
| set03 | 보완 요청 | 서류 누락 | `missing_documents: ["처방전"]` |
| set04 | 보완 요청 | 서류 불일치 | `mismatches: ["비급여 합계", "진료비 총액"]` |
| set05 | 보완 요청 | 중복 제출 | 모두 `[]` |
| 10만 원 초과, 영수증만 | 검토 필요 | 서류 누락 | `missing_documents: ["처방전"]` |
| 10만 원 초과, 처방전 있음 | 검토 필요 | 서류 누락 | 모두 `[]` |
| 입원, 영수증만 | 보완 요청 | 서류 누락 | `missing_documents: ["세부내역서", "진단서"]` |
| 입원 고액, 확인서만 | 보완 요청 | 서류 누락 | `missing_documents: ["진단서"]` |
| 피부과, 증빙 없음 | 검토 필요 | 서류 누락 | 모두 `[]` |
| 입원 정상, 입원 소액 확인서, 비뇨의학과 증빙 있음 | 심사 진행 | 없음 | 모두 `[]` |

## 예외 시험 기대값

| 경우 | 기대 decision | 기대 cause | 목록 키 |
| --- | --- | --- | --- |
| 기타 문서만 있음 | 보완 요청 | 서류 누락 | `missing_documents: ["진료비 영수증"]` |
| 정상 영수증 + 기타 문서 | 심사 진행 | 없음 | 모두 `[]`. 기타 문서는 판정에 쓰지 않음 |
| 여러 쪽 세부내역서, 금액 일치 | 심사 진행 | 없음 | 모두 `[]` |
| 여러 쪽 세부내역서, 합계 불일치 | 보완 요청 | 서류 불일치 | `mismatches`에 다른 값 |
| 영수증 검산이 깨짐 | 검토 필요 | 읽기 오류 | 모두 `[]` |

프롬프트 규칙은 `judge/`의 일부만 옮겼다. 날짜, 처방전 사용기간은 최종 제출 때 넣는다.

## 후속 문구

판정 뒤 `보완 요청`이면 고객 안내문을, `검토 필요`면 담당자 확인 메모를 만든다. 채점 키에는 넣지 않는다.
