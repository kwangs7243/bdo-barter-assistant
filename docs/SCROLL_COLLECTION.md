# Scroll Collection

## 상태

M3는 실제 분리 물교창의 처음부터 끝까지 live 검증을 통과했다. 상태는 `PASS (2026-09-22)`다.

최종 live 검증은 detached client `1023×713`, DPI 96, list viewport `(0,220,1023,493)`에서 수행했다. 11개 viewport가 `[0,1,1,1,1,1,1,1,1,1,1]` overlap으로 연결되어 56행을 수집했다. 중간에 overlap 0인 화면 1개는 거부했고, 사용자가 한 화면 위로 복귀한 뒤 anchor 손실 없이 이어졌다. 동일 화면 1개는 duplicate로 건너뛰었다. 첫 scrollbar top, 마지막 bottom과 모든 accepted transition overlap이 확인되어 `coverage_complete=true`였고 `bottom_reached`로 자동 종료했다. 총 시간은 88.562초, 평균 OCR은 viewport당 1.5923초, 네트워크 요청은 0회였다.

행 coverage와 OCR 의미 필드 완성도는 구분한다. 이번 live 결과는 56행 중 island 45, remaining count 54, from item 45, req amount 44, to item 39, yield amount 19를 값으로 복원했고 54행을 `review_required`로 보존했다. 샤샤 섬으로 보이는 행도 raw `사사심`과 null island로 남았으며, 그 밖에도 island 미확정 10행이 더 있다. 이는 M3 coverage 실패가 아니라 detached OCR 후속 개선·검수 대상이며, 사람이 확인하지 않은 값을 자동 확정하지 않았다.

## 캡처 대상

`scan-scroll`은 다음 순서로 창을 선택한다.

1. 제목 `Panel_Window_Barter_Search` + 프로세스 `BlackDesert64.exe`인 detached barter HWND
2. detached HWND가 없으면 즉시 오류 종료
3. `--hwnd`, `--title`, `--process`를 주더라도 detached HWND만 허용

시작 시 stderr에 선택된 제목, HWND, client 크기와 mode를 출력한다. 제공된 detached 캡처는 client `1023×713`, DPI `96`이었다.

detached 창은 첫 client frame을 한 번 캡처해 complete row와 그 위 separator를 찾고, 해당 위치부터 client 하단까지 전체 가시 목록 viewport를 사용한다. 제공 캡처에서 자동 측정된 영역은 `(0,220,1023,493)`이다. 상단·하단 partial row는 정상 입력이며 동적 segmentation에서 제외한다. 특정 scroll phase에서 정확히 6행을 맞추는 고정 451px 높이는 사용하지 않는다. M2 메인창 ROI `(464,404,987,490)`도 detached 창에 적용하지 않는다. 자동 측정이 실패하면 `--region x,y,width,height`를 사용한다.

## Detached OCR layout calibration

detached client 캡처는 M1 샘플과 행 높이는 같지만 열 폭이 `1023×70`으로 다르므로 `detached_barter_1023x713` 레이아웃 프로파일을 사용한다. 실제 `barter_detached_1023x713.png`에서 다음 좌표를 측정했다(좌표 원점은 complete row 좌상단).

- island: `(70,0)-(230,34)`
- remaining count: `(70,24)-(240,68)`
- from item: `(340,0)-(660,36)`
- to item: `(680,0)-(1015,42)`
- amount glyphs: request `(326,42)-(335,57)`, yield `(701,42)-(711,57)`

M1 reference 프로파일은 기본값으로 유지된다. detached 수량은 아이콘 아트와 겹치는 작은 숫자를 잘못 확정하지 않도록 깨끗한 단일 `1`만 자동 인식하고, `5/10/100` 등 폭이 넓은 숫자는 `null`과 `review_required`로 남긴다. 샘플 6행에서 detached 프로파일은 complete row 6개, island 6/6, remaining 6/6, from item 3/6, to item 5/6, req amount 3/6, yield amount 4/6을 기록했다. 이 수치는 새 Golden 정답이 아니라 레이아웃 보정 전후의 관찰 지표다.

## 실행 흐름

1. 게임에서 물교창을 별도 창으로 분리한다.
2. detached 목록을 맨 위에 둔다.
3. 명령을 실행한다.
4. `[SCAN #N] accepted` log 또는 beep를 확인한다.
5. 이전 화면의 complete row가 최소 1행 남도록 약 4~5행 아래로 스크롤한다.
6. 스크롤 관성이 완전히 멈춘 뒤 accepted 신호를 기다린다. 기본 판정에는 최소 8 frame과 0.7초가 필요하다.
7. OCR 완료를 기다리지 않고 다음 위치로 이동한다.
8. 목록 끝까지 반복한다. 마지막 accepted 화면의 scrollbar가 bottom이면 결과 큐를 마무리하고 자동 종료한다. 이때만 `coverage_complete=true`가 된다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll --output scroll-result.json
```

창이 여러 개라면 detached HWND를 명시할 수 있다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll `
  --hwnd 0x123456 `
  --output scroll-result.json
```

신뢰성 우선 기본값을 직접 명시하려면:

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll `
  --poll-interval 0.1 `
  --stable-frames 8 `
  --stable-duration 0.7 `
  --motion-threshold 0.02 `
  --output scroll-result.json
```

프로그램은 마우스·키보드 입력을 보내지 않는다. scrollbar bottom을 확인하면 자동 종료하며, 그 전에 중단하려면 `Ctrl+C`를 누르면 현재까지 큐에 등록된 결과를 정상적으로 마무리한다. 분리창이 중간에 닫혀도 `window_unavailable`로 종료하고 이미 수집한 부분 결과는 보존하되 `coverage_complete=false`로 남긴다.

## 안정 frame 판정

- poll 기본값은 `0.1초`다.
- 매 poll마다 최신 ROI frame의 96×48 grayscale fingerprint와 horizontal separator 위치를 보관한다.
- 최근 8개 frame에서 pixel motion이 threshold 이하이고 separator 개수와 y 좌표가 ±1px 이내로 0.7초 이상 유지될 때만 최신 frame을 accepted 후보로 삼는다.
- separator geometry가 이동 중이면 scroll inertia로 보고 안정화 이력을 다시 시작한다. stale/mid-scroll frame은 queue에 넣지 않는다.
- 기본 `motion_threshold`는 `0.02`다.

separator는 scrollbar를 제외한 넓은 row content 구간의 grayscale 평균과 dark-pixel 비율로 매 frame 검출한다. 연속된 두 separator 사이 높이가 60~80px일 때만 complete row로 만든다. 따라서 위 separator가 없는 상단 partial row와 아래 separator가 없는 하단 partial row는 collection과 visual fingerprint에서 제외된다.

첫 accepted viewport는 scrollbar thumb가 top이어야 한다. 그 다음부터는 이전 accepted complete rows의 suffix와 현재 complete rows의 prefix가 시각 fingerprint로 최소 1행 겹쳐야 한다. 겹침이 0이면 beep 없이 거부하고 `scroll up slightly`를 출력하며 collection anchor를 바꾸지 않는다. 마지막 accepted viewport의 thumb가 track 하단에 도달하면 end coverage를 인정하고 자동 종료한다. 실제 493px viewport는 panel 하단 border가 있어 thumb bottom `479`를 track 끝으로 측정한다.

## 로그와 OCR queue

로그는 stderr, JSON은 output file 또는 stdout으로 분리한다.

```text
[M3] capture target | title=Panel_Window_Barter_Search | hwnd=0x... | client=1023x713 | mode=detached_barter_window
[SCAN #1] accepted | complete_rows=6 | overlap=0 | added=6 | queued=1
[OCR  #1] rows=6 | overlap=0 | added=6 | total=6 | review=4 | first=일리야 섬 | last=타라무라 섬
```

accepted 시 beep 1회를 내며 이는 관성 종료, 안정 separator geometry, complete-row segmentation과 안전한 overlap 연결을 모두 통과했으므로 다음 위치로 이동해도 된다는 뜻이다. OCR worker는 queue 순서대로 기존 M1 `scan_barter_frame()`을 호출하고, capture loop는 OCR 처리 중에도 계속 실행된다.

## 행 병합

- 동적 segmentation으로 얻은 complete row image만 fingerprint한다.
- 이전 전체 수집 suffix와 새 viewport prefix의 시각 fingerprint가 연속으로 일치하는 최대 길이를 overlap으로 사용한다.
- OCR 값은 row identity의 primary source로 사용하지 않는다.
- overlap 0인 viewport는 append하지 않고 거부한다.
- partial row는 segmentation 단계에서 제외한다.
- 모든 중복 관찰의 raw OCR과 confidence는 `collection_provenance`에 남긴다.

## Debug

기본 실행은 이미지를 저장하지 않는다. `--debug`를 지정하면 accepted viewport만 저장한다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-scroll --debug
```

각 viewport JSON에는 capture timestamp, motion scores, 안정 frame/시간, separator positions, complete row 수, scrollbar 상태, queue index, visual overlap/added rows와 OCR 결과를 기록한다.

## 출력 지표와 제한

`session`에는 `captured_frames`, `accepted_viewports`, `rejected_viewports`, `rejected_overlap_zero`, `rejected_not_at_top`, `ocr_frames`, `queued_viewports`, `duplicate_viewports_skipped`, `change_events`, `duration_sec`, `average_ocr_seconds`, `unique_rows`, `review_required_rows`, `stop_reason`이 포함된다. `coverage`에는 `start_at_top`, `every_transition_has_overlap`, `end_at_bottom`, `coverage_complete`, `visual_rows_collected`, `accepted_viewport_overlaps`가 포함된다. `coverage_complete`는 top 시작, 모든 accepted 전환 overlap, bottom 종료가 모두 확인된 경우에만 true다.

M3는 자동 스크롤, GUI, overlay, inventory, scheduler, game memory, packet, DLL injection, 외부 API를 구현하지 않는다. M3 coverage는 PASS지만 의미 필드의 `review_required`는 후속 검수·OCR 개선 대상으로 남는다. M4는 별도 지시 전까지 시작하지 않는다.
