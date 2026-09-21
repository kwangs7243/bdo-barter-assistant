# Roadmap

마일스톤은 앞 단계의 통과 조건을 충족한 뒤에만 진행한다.

## M0 — Repository / Documentation

상태: **완료 (2026-09-22)**

- [x] 프로젝트 폴더 구조
- [x] 제품 사양과 아키텍처 경계
- [x] 데이터 모델 초안
- [x] OCR PoC 계획과 고정 샘플 정답
- [x] 원본 HTML 엔진 조사
- [x] Python 3.11 + uv 최소 메타데이터
- [x] 원본 HTML 및 전체화면/크롭 샘플 보존

통과 조건: 요청된 파일이 존재하고, reference hash가 기록값과 일치하며, Python 구현물이 없다.

## M1 — OCR PoC

상태: **완료 / PASS (2026-09-22)**

- [x] 크롭 샘플 6행 분할
- [x] Windows 로컬 OCR 전처리 접근 비교
- [x] HTML 파생 섬/품목 후보 매칭
- [x] 행별 원문, 정규화값, 확신도, 대안 후보 출력
- [x] 가림 입력의 `review_required` 처리와 오답 자동 확정 0개 확인
- [x] 외부 네트워크 OCR/API 호출 없음
- [x] 전체화면의 명시적 영역 crop에서 동일 6행 확인

통과 조건은 `docs/OCR_POC.md`를 따른다. **M1 통과 전 M2 이후 구현 금지.**

## M2 — Window Capture

상태: **완료 / PASS (2026-09-22)**

- [x] Windows top-level 창 열거와 제목·프로세스·HWND 선택
- [x] DPI-aware client rect 계산과 desktop 기반 메모리 캡처
- [x] window-relative ROI 및 1회 calibration 저장
- [x] 기존 M1 OCR pipeline과 normalized JSON 연결
- [x] 일반 모드 파일 미저장, 디버그 캡처 opt-in
- [x] M1 회귀 포함 자동 테스트 14개 통과
- [x] 실제 실행 중인 검은사막 창에서 `scan-window` 검증

실제 `BlackDesert64.exe` 창의 1920×1080 client area를 DPI 96에서 메모리 캡처해 기존 OCR pipeline으로 6행을 출력했다. 디버그 이미지는 저장하지 않았고 네트워크 요청은 0회였다.

## M3 — Scroll Collection

상태: **완료 / PASS (2026-09-22)**

- [x] ROI grayscale 차이 기반 viewport 변경 감지
- [x] poll + debounce 후 변경 화면에만 OCR 실행
- [x] 겹치는 행의 순서 보존 병합과 confidence 개선
- [x] 충돌·불확실 행의 보수적 `review_required` 유지
- [x] countdown, 조정 가능한 idle timeout, `Ctrl+C` 종료
- [x] 기본 메모리 처리와 명시적 `--debug` 저장
- [x] M1/M2 회귀 포함 자동 테스트 24개 통과
- [x] 실제 게임에서 목록 처음부터 끝까지 수동 스크롤 검증

실제 게임에서 52.75초 동안 150 frame을 캡처하고 안정된 3개 viewport만 OCR했다. 중복 viewport 62개를 건너뛰어 최종 15행을 순서대로 수집했으며 7행은 `review_required`로 보존했다. live viewport 사이에 공통 행은 없었으므로 실제 겹침 병합은 발생하지 않았고, 해당 동작은 자동 테스트로 검증했다.

## M4 — Local Inventory

- 최초 재고 입력
- 확인된 0과 미입력 구분
- 로컬 영구 저장, schema version, 백업/복구
- 수정 이력과 snapshot revision

## M5 — v14.1 Engine Port

- `masterData`, 좌표, 항로 보정, 튜닝값의 파생 데이터 생성
- 일반 쾌속/균형 엔진 이식
- 7단 2지역/3지역 엔진 이식
- 원본 입력/출력 회귀 fixture와 동등성 보고서

## M6 — Completion / Inventory Delta

- 계획과 실제 수행 수량 분리
- 완료 전 delta 미리보기
- 명시적 확정 후 원자적 재고 반영
- 일부 수행, 취소, 중복 완료 방지
- 완료 감사 기록

## M7 — UI

- 스캔, 검수, 재고, 계획, 완료를 하나의 흐름으로 연결
- 오류·불확실성·오래된 계획 표시
- 기술 용어를 최소화한 한국어 UI

## M8 — Windows Packaging

- Windows 10 배포물
- 로컬 OCR 모델 포함/최초 다운로드 정책 결정
- 새 PC 설치 및 오프라인 실행 검증
- 백업·업데이트·제거 절차 문서화
