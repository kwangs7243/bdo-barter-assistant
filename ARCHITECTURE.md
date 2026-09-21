# Architecture

## 1. 시스템 경계

이 앱은 게임 화면을 읽고 계획을 제안하는 로컬 보조 도구다. 게임 프로세스 내부 상태나 네트워크 패킷에 접근하지 않으며 입력을 대신하지 않는다.

```text
Game Window
  ↓ 사용자가 연 물교창의 화면 영역
Capture
  ↓ Image Frame (메모리)
OCR
  ↓ Raw OCR Tokens
Matching
  ↓ Normalized Barter Rows + Confidence
Barter Review
  ↓ Confirmed Barter List
Scheduler ← Inventory Snapshot + User Config + Reference Data
  ↓ Sortie Plan (read-only proposal)
Completion Review
  ↓ Confirmed Execution
Inventory
  ↓ Atomic Inventory Delta + Audit Record
Storage
```

## 2. 구성요소 책임

### `capture`

- Win32 top-level window를 열거하고 제목·프로세스·HWND로 대상 선택
- DPI-aware screen 좌표로 변환한 client area를 데스크톱에서 메모리 캡처
- client-relative 물물교환 ROI와 window/client rect, DPI, 캡처 크기 메타데이터 제공
- 일반 모드에서 캡처 파일을 영구 저장하지 않음
- OCR, 품목명, 스케줄 규칙을 알지 못함
- 축소 grayscale ROI의 평균 픽셀 차이로 viewport 변경 여부만 판정

### `ocr`

- 이미지 전처리 후보 적용
- 지정 영역에서 원문 토큰과 위치, 엔진 확신도 반환
- 품목을 최종 확정하거나 스케줄을 판단하지 않음
- 구체 엔진은 adapter 뒤에 숨김

### `matching`

- OCR 원문을 섬/품목 후보 사전과 비교
- 열 위치, 단계, 수량 형식과 문자열 유사도를 결합
- 정규화 후보, 확신도, 대안 후보 목록 제공
- 임계값 미달을 `review_required`로 표시

### `barter`

- 교환 행의 유효성 검사와 정규화
- viewport의 suffix/prefix 공통 행을 이용한 스크롤 순서 보존과 중복 제거
- 중복 관찰 중 더 신뢰도 높은 필드와 raw provenance 보존
- 사용자 검수·수정 상태 관리
- OCR 세부 구현과 스케줄 점수 계산을 알지 못함

### `scheduler`

- 확정 교환 목록, 재고 snapshot, 설정, 참조 데이터를 입력으로 받음
- 쾌속/균형 출항 계획을 결정적으로 계산
- 계획을 반환할 뿐 재고나 파일을 직접 변경하지 않음
- M5에서 원본 v14.1 동등 동작을 회귀 fixture로 잠금

### `inventory`

- 확정 재고와 입력 상태 관리
- 계획과 실제 수행 차이를 반영한 delta 계산
- 완료 명령의 유효성, 음수 재고 정책, 중복 적용 방지 담당
- OCR 이미지와 스케줄 내부 점수를 알지 못함

### `storage`

- 로컬 영구 저장과 schema version 관리
- 원자적 저장, 백업/복구, 완료 이력 제공
- 저장 형식은 M4에서 결정

### `ui`

- 사용자의 스캔, 검수, 설정, 계획, 완료 흐름 연결
- 도메인 규칙을 UI 이벤트 내부에 구현하지 않음
- 상태 변경 전 미리보기와 명시적 확인 제공

## 3. 의존 방향

```text
ui ───────────────┐
capture → ocr → matching → barter → scheduler
                         │             ↑
                         │        inventory snapshot
                         └─────────────┘
inventory ─────────────────────────→ storage
barter/scheduler config ───────────→ storage
reference-derived data ────────────→ matching + scheduler
```

허용하지 않는 역방향 예:

- Scheduler가 화면을 캡처하거나 OCR 호출
- OCR이 재고를 수정
- UI가 재고 delta를 직접 계산
- 계획 생성이 Storage에 재고 변경을 기록

## 4. 상태 구분

다음 상태는 별도로 보존한다.

1. `raw_capture`: 일시적인 이미지 프레임
2. `ocr_observation`: OCR 원문과 위치·확신도
3. `barter_candidate`: 후보 매칭 결과
4. `confirmed_barter_list`: 사용자 검수가 끝난 교환 목록
5. `inventory_snapshot`: 계산 시점의 확정 재고
6. `sortie_plan`: 해당 snapshot으로 만든 제안
7. `completion_record`: 실제 수행으로 확정한 항목
8. `inventory_transaction`: 완료로 인해 적용된 delta

계획에는 사용한 inventory revision을 기록한다. 이후 재고가 바뀌면 오래된 계획임을 표시하고 자동으로 완료 처리하지 않는다.

## 5. 원본 엔진 이식 전략

M5에서는 새 알고리즘을 먼저 설계하지 않는다.

1. 원본 HTML에서 데이터와 계산 입력을 고정 fixture로 추출한다.
2. 원본 함수의 관찰 가능한 출력을 기록한다.
3. Python에 데이터 모델과 순수 계산 단위를 이식한다.
4. 동일 입력의 출항, 순서, 실행 횟수, 교섭력, 무게가 동등한지 비교한다.
5. 알려진 원본 예외나 버그는 호환 모드 테스트로 먼저 보존한다.
6. 개선은 호환 구현 완료 후 별도 결정으로 분리한다.

## 6. 오류 처리 원칙

- OCR 애매함: 자동 보정 대신 검수
- 알 수 없는 섬/품목: 원문 보존, 미확정 상태
- 일부 행 누락: 스캔 결과를 완성으로 오인하지 않도록 coverage 표시
- 저장 실패: 메모리 상태를 성공으로 표시하지 않고 이전 정상본 유지
- 완료 충돌: 사용자가 최신 재고와 delta를 다시 확인
- 원본 데이터 누락: 추측하지 않고 `future_information_input` 또는 미지원으로 표시

## 7. 현재 구현 범위

- M1: 저장 이미지 또는 메모리 프레임을 같은 OCR 파이프라인으로 정규화한다.
- M2: 화면에 보이는 Windows client area를 `ctypes`와 Pillow `ImageGrab`으로 캡처한다.
- 기본 ROI는 검증된 1920×1080 M1 영역을 client 크기에 정규화해 적용하며, 명시적 ROI를 1회 저장해 대체할 수 있다.
- 최소화되었거나 완전히 가려진 창의 우회 캡처, 입력 자동화, 스크롤 수집은 지원하지 않는다.
- M2는 실제 `BlackDesert64.exe` HWND에서 1920×1080 client area 캡처와 기존 OCR pipeline 연결을 검증했다.
- M3는 변경 후 안정된 viewport만 OCR하고 겹치는 행을 보수적으로 병합하는 `scan-scroll` CLI를 실제 게임의 전체 목록 수동 스크롤로 검증했다.
