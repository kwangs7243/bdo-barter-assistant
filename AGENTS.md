# AGENTS.md

## Project

이 저장소는 Windows 10에서 실행하는 검은사막 한국 서버 물물교환 로컬 도우미다.

현재 마일스톤은 **M0 Documentation**이다. 사용자가 다음 마일스톤 진행을 명시하기 전에는 Python 기능, OCR 엔진 설치, GUI, 게임 창 캡처를 구현하지 않는다.

## Source of Truth

서로 충돌하는 내용은 다음 순서로 판단한다.

1. 사용자의 최신 명시 지시
2. `SPEC.md`
3. `ARCHITECTURE.md`
4. `docs/*.md`
5. `reference/original/`의 v14.1 HTML

원본 HTML은 참고 구현이며 제품 사양 자체가 아니다. 원본의 UI, Gemini 연동, API 키 기능, 진단 도구를 그대로 보존할 의무는 없다.

## Product Boundaries

- 외부 AI/OCR API를 사용하지 않는다.
- Gemini, OpenAI API, Google Cloud Vision 등 네트워크 OCR 서비스를 추가하지 않는다.
- 게임 메모리 읽기, 패킷 분석, 입력 자동화, 매크로, 자동 플레이 기능을 추가하지 않는다.
- 사용자가 직접 게임에서 물물교환 창을 열고 스크롤하며 실제 교환을 수행한다.
- 재고의 Source of Truth는 로컬 앱이다. Notion이나 외부 서비스에 같은 재고를 중복 관리하지 않는다.
- 계획을 생성하거나 표시한 것만으로 재고를 변경하지 않는다.
- 사용자가 실제 수행 결과를 완료 처리한 뒤, 완료로 확정한 교환만 재고에 반영한다.
- OCR 결과가 불확실하면 자동 확정하지 않고 `검수 필요` 상태로 남긴다.
- 원본 v14.1 스케줄 엔진은 먼저 동등 동작을 재현한다. 검증 전에 임의로 단순화하거나 개선하지 않는다.

## Environment

- Windows 10
- Python 3.11
- uv
- CPU-first
- GPU/CUDA는 실제 필요성이 검증되고 사용자가 승인하기 전까지 도입하지 않는다.

## Architecture Rules

- `src` layout을 사용한다.
- `capture`, `ocr`, `matching`, `barter`, `scheduler`, `inventory`, `storage`, `ui`의 책임을 분리한다.
- OCR 계층은 스케줄을 판단하지 않는다.
- Scheduler 계층은 이미지나 OCR 엔진을 알지 못한다.
- Inventory 계층은 계획 생성 호출만으로 상태를 변경하지 않는다.
- I/O와 계산 로직을 분리하고, 핵심 계산은 재현 가능한 순수 함수로 만든다.
- 품목, 섬 좌표, 항로 보정값은 코드에 흩어 쓰지 않고 `data/`에서 관리한다.
- 새 의존성을 추가할 때 선택 이유, 대안, 로컬 실행 조건을 문서에 기록한다.

## Milestone Gates

- M1 OCR PoC가 샘플 기준을 통과하기 전에는 M2 이후 기능을 구현하지 않는다.
- M5 엔진 이식은 원본 입력/출력 고정 fixture와 회귀 테스트를 먼저 준비한다.
- M6 완료 처리에는 미리보기, 명시적 확정, 중복 적용 방지가 필요하다.
- 현재 마일스톤 밖의 기능을 선행 구현하지 않는다.

## Safety and Verification

- `reference/` 파일은 읽기 전용 원본으로 취급한다.
- 원본 reference를 수정하거나 정규화하지 않는다. 파생 데이터는 `data/`에 별도로 만든다.
- 0은 확인된 0이고, 미입력/미확인은 `null`과 명시적 상태로 구분한다.
- OCR 원문, 정규화 결과, 확신도, 사용자 수정 여부를 추적 가능하게 유지한다.
- 실제 재고 변경은 원자적 완료 기록과 함께 저장하고 같은 완료를 두 번 적용하지 않는다.

