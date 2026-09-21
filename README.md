# BDO Barter Assistant

검은사막 한국 서버 물물교환 화면을 로컬에서 읽고, 로컬 재고와 기존 v14.1 계산 규칙을 이용해 출항 계획을 만드는 Windows 10용 도우미 프로젝트다.

현재 상태는 **M0 Documentation 완료**다. 폴더 구조와 설계 문서, 원본 HTML, OCR 샘플만 준비되어 있으며 Python 기능, OCR 엔진, GUI는 아직 구현하지 않았다.

## 목표 사용 흐름

1. 게임에서 물물교환 창을 연다.
2. 로컬 도우미에서 스캔을 시작한다.
3. 사용자가 물물교환 목록을 끝까지 스크롤한다.
4. 도우미가 행을 로컬 OCR로 판독하고 알려진 섬·품목 사전과 대조한다.
5. 불확실한 행만 사용자가 검수한다.
6. 로컬 재고와 v14.1 호환 엔진으로 출항 계획을 생성한다.
7. 사용자가 게임에서 실제 수행한 교환을 완료 처리한다.
8. 완료로 확정된 교환만 로컬 재고에 반영한다.

## 확정 원칙

- 외부 AI/OCR API 없음
- Windows 10, Python 3.11, uv
- 로컬 앱이 물물교환 재고의 Source of Truth
- 계획 생성과 재고 변경 분리
- 낮은 OCR 확신도는 자동 확정하지 않음
- v14.1 엔진 동등 재현 후 개선 검토
- 게임 메모리, 패킷, 자동 입력·조작은 범위 밖

## 문서 안내

- [SPEC.md](SPEC.md): 제품 범위와 요구사항
- [ARCHITECTURE.md](ARCHITECTURE.md): 구성요소 경계와 데이터 흐름
- [ROADMAP.md](ROADMAP.md): 마일스톤과 통과 조건
- [DECISIONS.md](DECISIONS.md): 확정 결정과 미결정 사항
- [docs/OCR_POC.md](docs/OCR_POC.md): M1 OCR 검증 계획
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md): 상태와 JSON 모델 초안
- [docs/REFERENCE_ENGINE.md](docs/REFERENCE_ENGINE.md): 원본 HTML 조사 결과

## 현재 폴더

```text
bdo-barter-assistant/
├─ AGENTS.md
├─ README.md
├─ SPEC.md
├─ ARCHITECTURE.md
├─ ROADMAP.md
├─ DECISIONS.md
├─ pyproject.toml
├─ docs/
├─ reference/
│  ├─ original/
│  └─ samples/
├─ src/bdo_barter/
│  ├─ capture/
│  ├─ ocr/
│  ├─ matching/
│  ├─ barter/
│  ├─ scheduler/
│  ├─ inventory/
│  ├─ ui/
│  └─ storage/
├─ data/
└─ tests/fixtures/
```

## 다음 단계

다음 작업은 [M1 OCR PoC](docs/OCR_POC.md) 하나만 수행한다. OCR 엔진은 아직 확정하지 않았으며, 제공된 두 샘플에서 정확도·검수 흐름·완전 로컬 실행 가능성을 실제로 비교한 뒤 선택한다.

