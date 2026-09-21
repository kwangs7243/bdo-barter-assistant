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
