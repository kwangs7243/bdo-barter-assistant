# Scroll Collection

## 상태

M3 코드, 자동 테스트와 실제 검은사막 목록의 처음부터 끝까지 수동 스크롤 검증을 완료했다. 상태는 `PASS`다.

실제 검증 결과:

- 종료: `idle_timeout`
- 총 시간: `52.75초`
- 캡처 frame: `150`
- 화면 변화 event: `70`
- OCR viewport: `3`
- 건너뛴 중복 viewport: `62`
- 평균 OCR 시간: `1.4565초`
- 최종 unique row: `15`
- `review_required` row: `7`
- 네트워크 요청: `0`
- 디버그 이미지 저장: 없음

7개 불확실 행은 값이 없는 필드를 억지로 확정하지 않았다. 세 live viewport의 행은 서로 겹치지 않아 실제 병합 provenance는 각 1개였고, 겹침 병합과 false merge 방지는 자동 테스트 결과를 근거로 한다.

## 실행 흐름

1. 게임 물물교환 목록을 맨 위에 둔다.
2. 다음 명령을 실행한다.
3. 3초 countdown 동안 게임으로 돌아간다.
4. 한 화면을 약 2.5초씩 멈추며 목록 끝까지 직접 아래로 스크롤한다.
5. 마지막 화면에서 기본 12초 동안 그대로 두면 자동 종료된다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll --output scroll-result.json
```

게임 창이 여러 개면 M2 `windows --game-only` 결과의 HWND를 지정한다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll `
  --hwnd 0x123456 `
  --output scroll-result.json
```

idle 종료를 기다리지 않고 PowerShell로 돌아와 `Ctrl+C`를 누르면 현재까지 수집한 결과를 정상 출력한다. 프로그램은 게임에 키보드나 마우스 입력을 보내지 않는다.

## 변경 감지와 OCR 최소화

- 캡처 대상은 M2에서 확정한 물물교환 ROI다.
- ROI를 96×48 grayscale로 축소해 평균 절대 픽셀 차이를 계산한다.
- 차이가 기본 임계값 `0.02`를 넘으면 새 viewport 후보로 본다.
- 후보가 `0.6초` 안정된 경우에만 기존 M1 OCR을 한 번 실행한다.
- 이미 OCR한 viewport와 임계값 이내로 같으면 다시 OCR하지 않는다.
- 기본 캡처 주기는 `0.25초`, 변화 없음 자동 종료는 `12초`다.

M1 샘플을 세로로 합성 이동해 측정한 차이는 동일 화면 `0.0`, 2px `0.0092`, 5px `0.0218`, 10px `0.0396`, 30px `0.0672`, 75px `0.0481`이었다. 따라서 기본값은 미세한 2px 차이는 무시하고 5px 이상의 목록 이동은 감지한다. 실제 게임 전체 스크롤 결과에 따라 조정할 수 있도록 모든 시간과 임계값을 옵션으로 노출한다.

현재 OCR은 한 viewport를 처리하는 동안 다음 캡처를 병렬 수행하지 않는다. 중간 viewport 누락을 피하려면 다음 화면으로 이동하기 전에 약 2.5초를 기다린다. 첫 live run은 이 흐름으로 3개 viewport를 수집했다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll `
  --idle-timeout 15 `
  --poll-interval 0.25 `
  --debounce 0.6 `
  --change-threshold 0.02 `
  --output scroll-result.json
```

## 행 병합

- 새 viewport의 prefix와 누적 목록의 suffix가 연속으로 일치할 때만 겹침으로 인정한다.
- 확정된 섬·소모품·획득품·수량 중 하나라도 충돌하면 자동 병합하지 않는다.
- 핵심 이름 3개 또는 핵심 이름 2개와 수량 1개 이상의 일치가 필요하다.
- 중복 관찰은 confidence가 높은 필드를 우선하고, 한쪽만 값이 있으면 그 값을 보존한다.
- 모든 중복 관찰의 raw OCR과 confidence는 `collection_provenance`에 남긴다.
- 애매하면 합치지 않으므로 중복 후보가 남을 수 있으며, 이는 false merge보다 안전한 결과로 취급한다.

최종 행은 게임의 위→아래 순서로 `barter_collected_1...N` ID를 다시 부여한다. 각 행의 M1 `review_required`, 불확실 필드와 후보 정보는 그대로 유지한다.

## 출력 지표

`session`에는 다음이 포함된다.

- `captured_frames`
- `ocr_frames`
- `duplicate_viewports_skipped`
- `change_events`
- `duration_sec`
- `average_ocr_seconds`
- `unique_rows`
- `review_required_rows`
- `stop_reason`

CLI 종료 시 같은 핵심 수치를 PowerShell에 한 줄로 표시한다.

## 디버그와 제한

기본 실행은 이미지를 저장하지 않는다. 다음과 같이 명시한 경우에만 OCR을 수행한 ROI 이미지와 중간 JSON을 `.debug/scroll-session`에 저장한다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll --debug
```

- 마우스 자동 스크롤, 키보드·마우스 입력 전송, global hotkey를 구현하지 않는다.
- 게임 메모리, 패킷, 파일이나 DLL에 접근하지 않는다.
- M3는 사용자가 아래 방향으로 직접 스크롤하는 흐름을 대상으로 한다.
- M3 PASS 이후 M4를 진행할 수 있다.
