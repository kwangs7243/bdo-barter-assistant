# OCR PoC — M1 Result

## 1. 판정

**M1 PASS (2026-09-22)**

제공된 크롭 이미지와 전체화면 이미지의 수동 지정 영역에서 완전히 보이는 6개 행을 모두 구조화했다. Golden Data의 섬, 남은 횟수, 소모 품목, 요구 수량, 획득 품목, 획득 수량은 각 6/6 일치했고 잘못 자동 확정한 필드는 0개였다.

M1은 고정 샘플 PoC다. 게임 실시간 캡처, 자동 영역 탐지, 스크롤 수집, GUI, 스케줄러와 재고 기능은 구현하지 않았다.

## 2. 고정 테스트 자료

| 파일 | 용도 | 크기 | SHA-256 |
|---|---|---:|---|
| `reference/samples/barter_fullscreen.png` | 전체화면에서 명시적 목록 영역을 잘라내는 입력 | 1920×1080 | `FAD64ACA99886139AFB9B45A89A4076372A62A51B7D36742326B837D13DFDF6D` |
| `reference/samples/barter_cropped.png` | 행 분할과 필드 OCR의 기준 입력 | 987×490 | `041A30100BDF9E5D2E1BF4EEFEC3BFB97379B5A10F20C019CAEC1ADE8E2B52B1` |

크롭 하단의 일부 행은 제외하고 완전히 보이는 첫 6개 행만 판정했다.

## 3. Golden Data

| 순서 | 섬 | 남은 횟수 | 소모 품목 | 요구 수량 | 획득 품목 | 획득 수량 |
|---:|---|---:|---|---:|---|---:|
| 1 | 일리야 섬 | 5 | 황금빛 선인장 꽃다발 | 1 | 발레노스 고래 조각상 | 1 |
| 2 | 오스트라 섬 | 10 | 오색 구슬 | 1 | 걸쭉한 괴생물 혈액 | 2 |
| 3 | 아지르 섬 | 0 | 해상 기사단의 투구 | 1 | 조각상의 눈물 | 1 |
| 4 | 칸베라 섬 | 10 | 섬마을 도시락 | 1 | 종유석 파편 | 2 |
| 5 | 아라킬 섬 | 10 | 크론성 금주화 | 1 | 해골 장식 찻잔 | 2 |
| 6 | 타라무라 섬 | 10 | 해적선 돛대 | 1 | 반달 조리용 칼 | 3 |

정답은 `tests/fixtures/golden_rows.json`에만 두며 런타임 스캔 코드는 이 파일을 읽지 않는다.

## 4. 선택한 방식

- OCR 엔진: Windows 10 로컬 `Windows.Media.Ocr.OcrEngine`, 한국어 `ko`
- 행 분리: 목록 오른쪽의 조용한 32픽셀 구간에서 어두운 가로 구분선을 탐지
- 필드 분리: 섬, 남은 횟수, 소모 품목, 획득 품목을 고정 레이아웃 좌표로 각각 crop
- 전처리: 텍스트 필드를 bicubic 4배 확대
- 수량: 아이콘 위의 작은 흰색 숫자 영역을 별도 이진 글리프로 판독
- 사전: v14.1 HTML의 `masterData.name` 118개와 `rawData` 키 100개를 코드로 추출
- 매칭: RapidFuzz 문자열 점수와 한글 자모 분해 점수를 사용하고, 점수 0.78 이상이면서 2순위와 0.05 이상 차이 날 때만 자동 확정
- 불확실성: Windows OCR이 필드 confidence를 제공하지 않으므로 `ocr_confidence`는 `null`이며 임의 숫자를 만들지 않는다.

작은 수량 글리프 판독은 이번 샘플에서 관측된 1·2·3만 확정한다. 다른 모양은 추측하지 않고 `null`과 `review_required`로 남긴다.

## 5. 비교한 접근

| 접근 | 섬 | 남은 횟수 | 소모품 | 획득품 | 검수 행 | 오답 자동 확정 | 결과 |
|---|---:|---:|---:|---:|---:|---:|---|
| 패널 전체를 한 번에 Windows OCR | 행/열 순서가 섞이고 섬 1개가 누락됨 | 일부 인식 | 텍스트는 다수 인식 | 텍스트는 다수 인식 | 행 구조화 불가 | 판정 불가 | 실패 |
| 필드 분리, 확대 없음 | 0/6 | 0/6 | 0/6 | 4/6 | 6 | 0 | 실패 |
| 필드 분리, 2배 확대 | 4/6 | 6/6 | 6/6 | 6/6 | 2 | 0 | 부족 |
| 필드 분리, 4배 확대 | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0 | 선택 |

전체 패널 OCR은 한글 자체는 상당 부분 읽었지만 열 순서가 합쳐져 행 단위 데이터로 안전하게 연결할 수 없었다. 4배 확대 필드 OCR이 가장 단순하면서 6행을 모두 복원했다.

Tesseract 실행 파일은 현재 PC에 설치되어 있지 않았다. Windows 내장 OCR이 합격 기준을 충족했으므로 대형 런타임과 모델을 요구하는 EasyOCR/PaddleOCR는 추가 설치하지 않았다. 이는 무거운 후보를 무작정 모두 설치하지 않는다는 M1 원칙에 따른 것이다.

## 6. 실제 측정 결과

실행 환경은 Python 3.11.15, CPU, Windows 로컬 OCR이다. 모든 명령은 `uv --offline`으로 실행했다.

### 크롭 이미지

| 항목 | 결과 |
|---|---:|
| 완전한 행 탐지 | 6/6 |
| 섬 | 6/6 |
| 남은 횟수 | 6/6 |
| 소모 품목 | 6/6 |
| 요구 수량 | 6/6 |
| 획득 품목 | 6/6 |
| 획득 수량 | 6/6 |
| 검수 필요 행 | 0 |
| 잘못 자동 확정한 필드 | 0 |
| 5회 합계 처리 시간 | 9.1094초 |
| 평균 처리 시간 | 1.8219초 |
| 최소/최대 처리 시간 | 1.7046초 / 2.0741초 |

원시 결과와 행별 OCR 원문은 `docs/OCR_POC_RESULTS.json`에 보존한다.

### 전체화면 이미지

M1에서는 자동 탐지 대신 최초 설정과 같은 명시적 영역 `464,404,987,490`을 사용했다. 이 영역에서 같은 6개 행과 36개 Golden 필드가 모두 일치했다.

| 항목 | 결과 |
|---|---:|
| 3회 합계 처리 시간 | 5.7143초 |
| 평균 처리 시간 | 1.9048초 |
| 최소/최대 처리 시간 | 1.7739초 / 2.1091초 |
| 검수 필요 행 | 0 |
| 잘못 자동 확정한 필드 | 0 |

### 손상 입력 안전성

첫 행의 소모 품목 텍스트를 완전히 가린 변형 입력에서도 6행 분리는 유지됐다. 가린 필드는 `value: null`, 해당 행은 `review_required`가 되었고 잘못 자동 확정한 필드는 0개였다.

실행 코드에는 네트워크 클라이언트나 외부 OCR/AI API 호출이 없다. 모델 파일 다운로드가 필요한 OCR 엔진도 사용하지 않는다. 최대 메모리는 이번 M1에서 계측하지 않았다.

## 7. 출력과 재현

정규화 결과는 `docs/DATA_MODEL.md`의 `Barter Row Candidate` 형태를 따르며 다음을 함께 보존한다.

- 필드별 OCR 원문
- 정규화 후보와 match confidence
- 2순위 후보와 점수 차
- Windows OCR confidence 미제공을 나타내는 `null`
- 수량 글리프 signature와 판독 confidence
- 행별 `auto_confirmed` 또는 `review_required`
- 단계별 처리 시간

```powershell
uv sync --python 3.11

uv run --offline python -m bdo_barter_assistant evaluate `
  reference/samples/barter_cropped.png `
  --golden tests/fixtures/golden_rows.json `
  --repeat 5 `
  --output docs/OCR_POC_RESULTS.json

uv run --offline python -m bdo_barter_assistant evaluate `
  reference/samples/barter_fullscreen.png `
  --golden tests/fixtures/golden_rows.json `
  --region 464,404,987,490

uv run --offline pytest -q
```

HTML 사전을 다시 생성하는 명령:

```powershell
$html = Get-ChildItem reference/original -Filter *.html | Select-Object -First 1
uv run --offline python -m bdo_barter_assistant extract-reference `
  $html.FullName data/ocr_dictionary.json
```

## 8. 다음 단계에서 해결할 문제

- M2에서 최초 1회 수동 영역 지정 UX 또는 자동 패널 탐지를 실제 해상도/UI 배율 변화로 비교한다.
- 현재 고정 레이아웃 좌표를 다른 해상도와 UI 배율에서 검증한다.
- 1·2·3 이외의 요구/획득 수량 표본을 확보해 글리프 판독 범위를 확장하거나 전용 숫자 OCR로 교체한다.
- Windows 한국어 OCR 언어 팩이 없는 PC의 설치 안내와 실패 메시지를 마련한다.
- 더 많은 실제 화면과 흐림·가림·밝기 변화 fixture를 추가한다.
- 배포 단계 전에 OCR 프로세스를 포함한 최대 메모리를 계측한다.

M1 통과는 고정 샘플에서 로컬 OCR 가능성을 입증한 것이다. M2 이후 기능이 이미 구현되었다는 의미는 아니다.
