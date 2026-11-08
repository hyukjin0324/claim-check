# 최종 데이터셋 인계 (11/8)

## 끝난 것
- `scripts/export_final.py`로 이 폴더에 데이터셋 PDF 29개, `컴학감동_최종제출_answer.json`, `컴학감동_최종제출_유형표.xlsx`를 만들었다. 문서 56건이고, 판정은 심사 진행 18 / 보완 요청 7 / 검토 필요 4
  - 원본: `cases/` 가상 케이스 19건 + 새로 만든 `case_30`(총액 오인쇄, 읽기 오류) + `submission/mission2/시험용/` PDF 9개
  - 뺀 것: case_23(금액칸 잘림, 한계), 흐린문서만, 총액빈칸, 손글씨 신규 촬영
- Studio 제출본 **설정 #13**: `(시험용 보강)` #5의 청구_판정 프롬프트를 옮김(30,000원 이하 문구, 병원·약국 요양기관, reason 양식). 변경은 이 하나뿐
- 29개 업로드, #13으로 **1회** 실행. decision/cause/missing_documents/mismatches **28/29 일치**
  - 틀림: **set04**(case_07, 괄호형 영수증 + 처방전). 기대 심사 진행 / 없음, 결과 검토 필요 / 읽기 오류
  - 정리 노드(지시-1·2·3) 출력에는 인용 표시가 없고, 청구_판정 출력에는 남아 있음
  - 이름·기관은 비교하지 않음

## 남은 일
1. set04 원인 확인: 청구_판정 reason에서 A·B 계산과 추출값을 보고, 괄호형 서식 추출 문제인지 판단. 고칠 수 없으면 한계로 쓰고 데이터셋에 남김
2. #13으로 29개 2회째 실행 → 두 번 모두의 결과로 채점
   - 결과 가져오기: 페이지에서 `POST /api/files/batch-results` body `{fileIds, workflowId, ver:13, configId}` → `results[fileId].results.splitInstructResults['지시-N'][0].content`
3. `score_studio.py`로 채점(이름·기관 포함, 정리 노드 content 기준)
4. 저장소 문서 갱신: TEAM_CONTEXT, docs에 #11~#13, 데이터셋 구성, 채점 결과
5. 설계서(#13, 정리 노드, blank, 한계, 출처 칸), 발표 PDF, 워크플로우 JSON 내보내기
6. 라이브러리 게시: `컴학감동_최종제출_*` 29개만 샘플로 체크. 게시 설정 #13
7. 이 폴더, `scripts/export_final.py`, `answers/case_30.json`, `cases/case_30/` 커밋·푸시(브랜치)
