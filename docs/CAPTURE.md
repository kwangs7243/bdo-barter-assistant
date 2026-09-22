# Windows Capture

## 상태

M2 구현, 자동 테스트와 실제 검은사막 창 검증을 완료했다. 상태는 `PASS`다.

실제 검증 환경과 결과:

- 프로세스: `BlackDesert64.exe`
- window/client/capture 크기: `1920×1080`
- DPI: `96`, scale factor: `1.0`
- ROI: 기본 M1 정규화 영역 `(464, 404, 987, 490)`
- 검출: 현재 화면의 완전한 행 6개
- OCR pipeline 처리 시간: `1.8557초`
- 네트워크 요청: `0`
- 디버그 캡처 파일: 저장하지 않음

실시간 행 중 2개는 모호한 품목을 자동 확정하지 않고 `review_required`로 남겼다. 이 실시간 목록은 별도 사람이 정답을 만든 Golden 데이터가 아니므로 의미 필드의 전체 정확도 측정으로 사용하지 않는다.

## 방식

- `ctypes` Win32 API로 보이는 top-level window를 열거한다.
- 제목, 프로세스 실행 파일명 또는 명시적 HWND로 창을 선택한다.
- process DPI awareness를 설정한 뒤 `GetWindowRect`, `GetClientRect`, `ClientToScreen`, `GetDpiForWindow`를 구분해 기록한다.
- 화면에 보이는 client area를 Pillow `ImageGrab`으로 메모리에 캡처한다.
- 캡처 프레임에서 client-relative ROI를 잘라 기존 M1 OCR 함수에 전달한다.
- 기본 실행은 이미지를 저장하지 않는다. `--debug-capture`를 지정한 경우만 원본 client 캡처를 저장한다.

## M3 detached barter window

M3 `scan-scroll`은 `Panel_Window_Barter_Search` 제목과 `BlackDesert64.exe` 프로세스를 가진 별도 top-level HWND만 선택한다. 이 창이 없으면 메인 게임창으로 fallback하지 않고 즉시 오류로 종료한다. 이는 detached 전용 scrollbar/coverage 판정을 메인창 ROI에 잘못 적용하는 것을 막는다.

실제 제공 캡처는 detached client `1023×713`, DPI `96`이었다. 첫 client frame에서 complete row를 찾은 뒤 첫 행 위 separator부터 client 하단까지 전체 가시 목록 영역을 bootstrap한다. 제공 캡처의 측정 결과는 `(0,220,1023,493)`이다. 고정 451px 높이나 정확히 6행이라는 가정은 사용하지 않으며, 이후 poll은 이 client-relative 영역만 `capture_client_region()`으로 ImageGrab한다. 다른 UI 배율이나 레이아웃에서 자동 측정이 실패하면 `--region`으로 명시할 수 있다.

detached capture는 M2의 메인창 기본 ROI `(464,404,987,490)`를 재사용하지 않는다. 일반 실행은 이미지를 저장하지 않으며, M3 `--debug`에서 accepted viewport만 저장한다.

`scan-scroll`은 detached ROI를 기존 M1 파이프라인에 넘길 때만 `detached_barter_1023x713` OCR layout profile을 선택한다. M1 reference 이미지의 고정 필드 박스와 매칭 임계값은 변경하지 않는다. 실제 detached 샘플에서 측정한 row-local 필드 박스와 보수적인 수량 glyph 규칙은 `docs/SCROLL_COLLECTION.md`에 기록되어 있다.

최종 live 검증은 detached HWND의 11개 viewport를 top부터 bottom까지 연결해 56행과 `coverage_complete=true`를 출력하고 `bottom_reached`로 자동 종료했다. overlap 0 화면은 거부 후 복구됐으며 메인 게임창 fallback은 허용하지 않는다. 의미 필드 미확정은 `review_required`로 남기며 capture coverage와 별도로 취급한다.

`window_rect`는 테두리와 제목 표시줄을 포함한 화면 좌표이고, `client_rect_screen`은 그 요소를 제외한 실제 게임 표시 영역의 화면 좌표다. ROI는 캡처된 client 이미지의 좌상단을 `(0, 0)`으로 사용한다.

## 실행

후보 창을 확인한다.

```powershell
uv run --offline python -m bdo_barter_assistant windows --game-only
```

후보가 하나면 현재 보이는 행을 읽는다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-window
```

후보가 여러 개면 `windows` 결과의 핸들을 지정한다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-window --hwnd 0x123456
```

제목이나 프로세스명 일부로도 선택할 수 있다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-window --title "검은사막"
uv run --offline python -m bdo_barter_assistant scan-window --process "BlackDesert"
```

## ROI calibration

기본값은 M1의 `1920×1080` 전체화면에서 검증한 `(464, 404, 987, 490)`을 client 크기에 정규화한 영역이다. 위치가 어긋날 때 현재 client 좌표의 ROI를 한 번 저장한다.

```powershell
uv run --offline python -m bdo_barter_assistant scan-window --region 464,404,987,490 --save-calibration
```

기본 저장 위치는 `%LOCALAPPDATA%\BDOBarterAssistant\capture-calibration.json`이다. 이후 `scan-window`가 자동으로 읽는다. 다른 경로는 `--calibration PATH`로 지정한다.

## 제한

- 창은 최소화되지 않고 화면에 정상 표시되어야 한다.
- 다른 창에 가려진 픽셀을 복원하지 않는다.
- 게임 메모리, 패킷, 파일, DLL injection, 키보드·마우스 입력에 접근하지 않는다.
- 스크롤 감지, 여러 프레임 병합, 중복 행 제거는 M2 범위 밖이다.
