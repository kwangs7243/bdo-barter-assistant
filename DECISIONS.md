# Decision Log

상태 표기: `Accepted`는 현재 확정, `Deferred`는 해당 마일스톤까지 보류다.

## D001 — 외부 AI/OCR API를 사용하지 않는다

- 상태: Accepted
- 결정: OCR과 이미지 처리는 로컬 PC에서 수행한다.
- 이유: 호출 비용, 네트워크 의존, 개인정보 전송을 피한다.
- 영향: 로컬 모델 파일을 설치할 수는 있으나 실행 중 외부 API 호출은 금지한다.

## D002 — 재고 Source of Truth는 로컬 앱이다

- 상태: Accepted
- 결정: 물물교환 재고를 Notion이나 별도 클라우드에 중복 관리하지 않는다.
- 이유: 실제 수행 직후 한 곳에서만 갱신해 불일치를 줄인다.

## D003 — 계획 생성은 재고를 변경하지 않는다

- 상태: Accepted
- 결정: 실제 수행을 사용자가 완료 확정한 뒤에만 재고 delta를 적용한다.
- 이유: 계획과 게임 내 행동은 다를 수 있다.

## D004 — OCR 불확실성을 숨기지 않는다

- 상태: Accepted
- 결정: 낮은 확신도나 경합 후보는 `review_required`로 남긴다.
- 이유: 틀린 자동 확정은 잘못된 계획과 재고 변경으로 전파된다.

## D005 — v14.1 엔진은 먼저 동등 재현한다

- 상태: Accepted
- 결정: 원본의 관찰 가능한 동작을 회귀 테스트로 재현한 뒤 개선을 논의한다.
- 이유: 무근거 재설계로 검증된 튜닝과 예외 처리를 잃지 않기 위해서다.

## D006 — 게임 내부 접근과 자동조작은 범위 밖이다

- 상태: Accepted
- 결정: 메모리, 패킷, 키보드·마우스 자동 입력, 자동 플레이를 구현하지 않는다.
- 이유: 이 제품은 화면 기반 의사결정 보조 도구다.

## D007 — Python 3.11 + uv, CPU-first

- 상태: Accepted
- 결정: 개발 기준은 Python 3.11과 uv이며 초기 OCR 검증은 CPU를 우선한다.
- 이유: 대상 PC에서 설치 복잡도를 낮추고 실제 충분성을 먼저 측정한다.

## D008 — OCR 엔진은 M0에서 고정하지 않는다

- 상태: Accepted
- 결정: 특정 OCR 라이브러리나 모델은 후보일 뿐이며 M1 측정으로 선택한다.
- 이유: 게임의 작은 한글 UI는 실제 샘플 정확도가 선택의 핵심이다.

## D009 — 캡처는 기본적으로 메모리에서 처리한다

- 상태: Accepted
- 결정: 일반 실행 중 PNG/JPG를 계속 저장하지 않는다.
- 이유: 불필요한 디스크 쓰기와 개인정보 잔존을 줄인다. 디버그 저장은 명시적 opt-in만 허용한다.

## D010 — 0과 미확인을 구분한다

- 상태: Accepted
- 결정: 확인된 수량 0은 `quantity: 0`, 미입력은 `quantity: null`과 `input_status: unconfirmed`로 표현한다.
- 이유: 미입력을 재고 없음으로 오판하면 스케줄 우선순위가 왜곡된다.

## D011 — 원본 reference는 수정하지 않는다

- 상태: Accepted
- 결정: 원본 HTML과 샘플 이미지는 읽기 전용으로 보존하고 파생 데이터는 `data/`에 만든다.
- 이유: 이식 결과를 원본과 재검증할 기준이 필요하다.

## D012 — 로컬 저장 형식

- 상태: Deferred to M4
- 후보: SQLite, versioned JSON
- 결정 기준: 원자성, 이력, 백업, 배포 복잡도, schema migration 테스트 가능성

## D013 — 캡처 영역 탐지 방식

- 상태: Accepted for M2
- 결정: M1에서 검증한 1920×1080 영역을 client-relative 비율로 변환해 기본값으로 사용한다. 실제 UI 배율에서 어긋나면 명시적 client ROI를 1회 저장하고 이후 창 크기에 비례 적용한다.
- 이유: 단일 샘플만으로 패널 자동 탐지를 일반화하지 않으면서 매 실행마다 영역을 지정하는 문제를 피한다.
- 영향: 게임 UI 배율이나 레이아웃 자체가 바뀌면 calibration을 다시 해야 한다.

## D014 — GUI와 패키징 도구

- 상태: Deferred to M7/M8
- 결정 기준: Windows 10 호환, 배포 크기, 로컬 OCR 통합, 유지보수성

## D015 — M1 OCR은 Windows 로컬 OCR과 필드 분리를 사용한다

- 상태: Accepted for M1
- 결정: Windows 10의 `Windows.Media.Ocr.OcrEngine` 한국어 인식기를 adapter 뒤에서 호출하고, 행과 의미 필드를 먼저 분리한 뒤 텍스트를 4배 확대해 읽는다.
- 이유: 제공 샘플에서 별도 대형 모델 없이 6개 Golden 행의 섬·품목·횟수를 모두 복원했고 평균 처리 시간이 약 1.82초였다.
- 영향: Windows 한국어 OCR 언어 팩이 필요하다. 최종 배포 엔진 확정은 더 많은 실제 표본과 설치 환경을 검증한 뒤 다시 판단한다.

## D016 — M1 전체화면 검증은 명시적 영역 지정을 사용한다

- 상태: Accepted for M1
- 결정: 전체화면 샘플은 `x,y,width,height` 영역을 명시적으로 받아 목록 crop을 만든다. 자동 패널 탐지는 M2로 미룬다.
- 이유: 명시적 영역 `464,404,987,490`에서 크롭 샘플과 같은 6행을 6/6로 판독했다. 한 장의 고정 샘플만으로 자동 탐지 일반화를 확정하지 않는다.

## D017 — M2는 보이는 client area의 desktop capture를 사용한다

- 상태: Accepted for M2
- 결정: Win32 API는 `ctypes`로 창 열거, client-to-screen 좌표와 DPI를 얻고 실제 픽셀은 기존 Pillow의 `ImageGrab`으로 메모리에 캡처한다.
- 이유: 새 의존성 없이 창 테두리를 제외한 화면 픽셀을 얻을 수 있고, 게임에서 검은 화면이 될 수 있는 `PrintWindow` 우회에 의존하지 않는다.
- 영향: 최소화되거나 다른 창에 완전히 가려진 게임은 지원하지 않는다. 화면에 표시된 실제 `BlackDesert64.exe` 창에서 client area 캡처와 OCR 연결을 검증했다.

## D018 — M3 viewport 변화는 축소 grayscale 평균 차이로 판정한다

- 상태: Superseded by D020/D021
- 결정: M3 초기 구현은 96×48 grayscale 평균 차이 하나를 motion과 duplicate 판정에 함께 사용했다.
- 이유: 추가 CV 의존성 없이 변경 후보를 찾기 위한 초기 기준이었다.
- 영향: stale frame과 과도한 중복 제거가 live 누락으로 이어져 현재 안정화 설계에서는 motion/duplicate threshold와 최신 안정 frame 판정을 분리한다.

## D019 — M3 행 병합은 false merge 방지를 우선한다

- 상태: Superseded for scroll collection by D023; OCR-observation merge fallback으로 유지
- 결정: 기존 목록 suffix와 새 viewport prefix의 연속 공통 행만 병합한다. 확정된 필드가 충돌하면 병합하지 않으며, 핵심 이름 3개가 일치하거나 핵심 이름 2개와 수량 필드 1개 이상이 일치해야 같은 행으로 본다.
- 이유: 일부 중복 행이 남는 것보다 서로 다른 실제 교환을 조용히 하나로 합치는 오류가 더 위험하다.
- 영향: 병합할 때 더 높은 confidence와 null이 아닌 값을 우선하고 모든 raw 관찰을 provenance로 남긴다. 애매한 겹침은 별도 `review_required` 행으로 유지될 수 있다.
- 검증: 자동 겹침 fixture는 12개 관찰을 순서가 유지된 9개 행으로 병합했다. 첫 live scroll의 3개 viewport에는 공통 행이 없어 live 병합은 발생하지 않았다.

## D020 — M3는 detached barter HWND를 우선 캡처한다

- 상태: Accepted for M3
- 결정: 제목이 `Panel_Window_Barter_Search`이고 프로세스가 `BlackDesert64.exe`인 top-level HWND만 M3 캡처 대상으로 선택한다. 분리창이 없으면 메인 게임창으로 fallback하지 않고 즉시 오류로 종료한다.
- 이유: 분리 물교창은 1023×713 client area로 물교 목록만 직접 캡처할 수 있어 메인 1920×1080 ROI의 누락 위험과 캡처 비용을 줄인다.
- 영향: detached client 첫 프레임에서 complete row separator로 list ROI를 bootstrap하고, 이후에는 client-relative ROI만 ImageGrab한다. 자동 입력과 게임 내부 접근은 하지 않는다.

## D021 — M3는 최신 안정 frame과 분리된 중복 임계값을 사용한다

- 상태: Superseded by D023
- 결정: poll 기본값 0.1초, 최근 3개 frame이 motion threshold 이하일 때 최신 frame을 accepted viewport로 큐에 넣는다. motion threshold 기본값은 0.02, duplicate threshold 기본값은 0.005로 별도 관리한다.
- 이유: 마지막 큰 변화 시점의 stale/mid-scroll frame을 OCR하는 문제를 제거하고, 서로 다른 viewport를 중복으로 버리는 위험을 낮춘다.
- 영향: OCR queue 전 `segment_complete_rows()`로 0개/비정상 geometry만 거부한다. accepted 시 beep/log를 내고 OCR worker는 캡처 loop를 막지 않는다.

## D022 — detached OCR은 별도 layout profile로 보정한다

- 상태: Accepted for M3 calibration
- 결정: `Panel_Window_Barter_Search`의 row-local 좌표는 M1 reference 고정 박스와 분리한 `detached_barter_1023x713` 프로파일로 처리한다. M1 기본 프로파일과 matching threshold는 변경하지 않는다.
- 이유: 실제 detached client 캡처는 행 높이는 같지만 열 폭이 1023px이고 item/icon 및 수량 glyph 위치가 달랐다. 공통 박스를 유지하면 획득품 첫 행과 수량이 누락되어 review가 증가했다.
- 안전장치: 작은 detached 수량 glyph는 단일 `1`만 자동 확정하고 폭이 넓은 숫자는 null/review로 남긴다. 실제 전체 목록 live 재검증 전에는 M3 PASS로 승격하지 않는다.

## D023 — M3 coverage는 동적 행 geometry와 시각적 연속성으로 증명한다

- 상태: Accepted and live validated for M3
- 결정: detached client에서 첫 complete row 위 separator부터 panel 하단까지 전체 가시 list viewport를 캡처한다. 넓은 row content band에서 separator를 동적으로 찾고, 연속 separator 사이 정상 높이의 complete row만 사용한다. 최근 8개 frame과 최소 0.7초 동안 separator y 좌표가 ±1px 이내일 때만 안정 frame으로 인정한다.
- 연속성: 이전 complete-row fingerprint suffix와 현재 prefix가 최소 1행 겹쳐야 accepted한다. OCR 문자열은 row identity의 primary source로 사용하지 않는다. 첫 viewport의 scrollbar top, 모든 accepted transition overlap, 마지막 viewport의 scrollbar bottom이 모두 확인될 때만 `coverage_complete=true`다.
- 이유: 실제 스크롤은 row snap이 아니라 연속 pixel scroll이어서 고정 `(0,222,1023,451)` ROI가 scroll phase에 따라 하단 complete row를 자르고, OCR 기반 병합이 누락을 감추었다.
- 영향: 제공된 서로 다른 phase 캡처에서 separator와 complete row를 각각 6 bands/5 rows, 8 bands/6 rows로 검출했다. 최종 live run은 11개 viewport, 56행, accepted overlap `[0,1,1,1,1,1,1,1,1,1,1]`, 중간 overlap 0 거부·복구, scrollbar top/bottom과 `coverage_complete=true`를 확인했다. OCR 의미 필드의 `review_required`는 coverage와 별도 문제로 유지한다.
