# Gemini Replacement Contract

## 목적

이 문서는 원본 `reference/original/물물교환 지능형 스케쥴러_배포용 v14.1_by 송도조씨.html`에서 Gemini가 수행하던 스크린샷 해석을 로컬 파서로 대체하기 위한 호환 계약이다. 목표는 범용 OCR 완성도가 아니라 원본 엔진이 소비하는 `scannedTrades`와 같은 의미의 입력을 안전하게 만드는 것이다.

```json
{
  "island": "장소명",
  "fromItem": "소모 품목명",
  "reqAmount": 1,
  "toItem": "획득 품목명",
  "count": 10,
  "yield": 3
}
```

각 논리 값에는 `ocr`, `reference_rule`, `user_confirmed` 중 하나의 출처를 기록한다. 확인되지 않은 값을 원본 코드의 `|| 1`, `|| 100` 기본값으로 채워 OCR 성공처럼 취급하지 않는다.

## 원본 코드 감사 결과

| 원본 책임 | 확인한 동작 | 로컬 대체 책임 |
| --- | --- | --- |
| `analyzeMultipleImagesWithGemini()` | 이미지에서 여섯 필드 JSON을 요청하고 여러 이미지의 중복 행을 합친다. | 화면 관측값을 읽고 reference 기반으로 계약을 완성한다. |
| `processParsedTrades()` | 품목·장소를 reference에 맞추고 `scannedTrades`를 만든다. | canonical location, tier-aware item, 특수 category를 동일 의미로 정규화한다. |
| `getItemTier()` | `masterData` 1~7, `mat`, `coin`, 그 밖의 tier 0을 구분한다. | HTML에서 추출한 의미 공간만 사용해 동일 category를 판정한다. |
| `APP_CONFIG.TRADE_RULES` | T2 `1→3`, T3 `1→3`, T4 `1→2`, T5~T7 `1→1`을 정의한다. | 일반 교환의 `reqAmount`와 `yield`를 결정적으로 파생한다. |
| `renderTrades()` | tier 0의 `reqAmount`와 coin의 `yield`만 가변 입력으로 취급하며 `count`는 항상 보존한다. | 해당 두 예외 숫자와 `count`만 필수 OCR로 판단한다. |
| `runAlgorithmAllModes()` | 일반 교환 수량을 규칙으로 다시 계산하고 base/coin 예외만 행 값을 사용한다. | scheduler가 실제 사용하는 값 기준으로 준비 상태를 판단한다. |
| `completeTrade()` | 정규화 품목, tier, req/mult, 실행 횟수로 완료 결과를 적용한다. | 이번 단계에서는 입력 호환성만 보장하고 완료 처리는 구현하지 않는다. |

## 필드별 계약

| `scannedTrades` 필드 | Gemini가 읽던 값 | scheduler 사용 | 직접 OCR 필수 | reference 파생/예외 |
| --- | --- | --- | --- | --- |
| `island` | 행의 장소명 | 좌표 조회, 모드·항로 판단 | 예 | 같은 좌표 alias를 canonical location으로 정규화한다. |
| `fromItem` | 왼쪽 품목명 | source tier, 재고 소모 판단 | 예 | 단계 표기와 `toItem` 문맥으로 안전하게 후보를 좁힌다. tier 0 base 문맥이면 raw 이름을 보존할 수 있다. |
| `reqAmount` | 왼쪽 아이콘 수량 | 1회당 소모량 | 일반 교환은 아니오 | T2~T7 및 mat/coin은 `1`을 reference rule로 파생한다. `fromTier == 0`만 화면 OCR이 필수다. |
| `toItem` | 오른쪽 품목명 | destination tier/category, 재고 획득 판단 | 예 | masterData와 HTML의 mat/coin 패턴을 함께 사용한다. |
| `count` | 남은 교환 횟수 | 가능한 실행 횟수 계산 | 예 | 확인된 `0`은 실제 값이며 미확인 `null`과 구분한다. |
| `yield` | 오른쪽 아이콘 수량 | 1회당 획득량 | 일반 교환은 아니오 | T2 `3`, T3 `3`, T4 `2`, T5~T7 및 mat `1`을 파생한다. `toTier == coin`만 화면 OCR이 필수다. |

## Reference 의미 공간

- 일반 품목: `masterData`의 tier 1~7, 총 118개.
- 장소: `rawData`의 좌표 항목. 같은 좌표의 이름은 하나의 canonical location과 alias 묶음으로 취급한다.
- `mat`: `getItemTier()`가 검사하는 `진주 결정`, `암염 주괴`, `코발트 주괴`, `오킬루아의 꽃`, `파도의 블랙스톤`, `대양의 견고한 현철`, `유실된 무역품 상자`, `흑수정 장식 팔찌` 패턴.
- `coin`: `까마귀 주화` 패턴.
- 이 목록 밖의 게임 지식은 추가하지 않는다.

## 정규화와 보수적 확정

1. `[N단계]` 표기는 이름에서 분리해 관측 tier로 보존한다.
2. 관측 tier가 명확하면 해당 tier 후보를 우선 사용한다. `fromItem`/`toItem` 관계로 후보를 줄일 때도 원본 규칙이 뒷받침하는 경우에만 사용한다.
3. 장소 점수와 margin은 alias 문자열끼리가 아니라 서로 다른 canonical location끼리 비교한다.
4. known tier 1 output과 non-empty unknown left raw가 함께 관측되고, 그 raw가 다른 known item의 불확실한 오독으로 보이지 않을 때만 tier 0 base 품목으로 보존한다.
5. `scheduler_ready`는 `island`, `fromItem`, `toItem`, `count`와 해당 행에 실제 필요한 수량이 모두 안전하게 채워졌을 때만 참이다.
6. `review_required`는 `scheduler_ready`의 반대다. 일반 교환의 작은 수량 glyph OCR 누락만으로 검수를 요구하지 않는다.

저장된 결과는 `evaluate-contract` 명령으로 재평가할 수 있다. 미완성 행에는 `raw_empty`, `top1_correct_looking_but_threshold_blocked`, `alias_margin_issue`, `dictionary_reference_missing`, `actual_ocr_corruption`, `contract_context_conflict` 중 보수적인 원인 분류를 기록한다. live 입력에는 행별 정답표가 없으므로 `wrong_auto_confirmed_count`는 자동으로 추정하지 않고 `null`로 둔다.

## 범위

이 계약은 로컬 screenshot parser와 `scannedTrades` 호환 출력까지만 다룬다. 캡처·스크롤·coverage 구조, 스케줄러 이식, 재고, 완료 처리, GUI는 변경하거나 구현하지 않는다.
