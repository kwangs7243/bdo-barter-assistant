# Data Model

이 문서는 M0의 논리 모델이다. 저장소 형식과 Python 타입은 각 구현 마일스톤에서 확정한다. JSON 예시는 외부 계약이 아니라 필드 의미를 고정하기 위한 기준이다.

## 1. 공통 원칙

- 내부 필드명은 `snake_case`를 사용한다.
- 품목과 섬은 표시 이름만으로 장기 식별하지 않고 파생 데이터 생성 시 안정 ID를 부여한다.
- 0은 확인된 값이다. 미확인 수량은 `null`과 상태 필드로 구분한다.
- OCR 관찰값과 사용자가 확정한 값을 덮어쓰지 않고 함께 보존한다.
- 모든 영구 상태는 `schema_version`을 가진다.

## 2. Reference Item

```json
{
  "item_id": "t5_sculptures_tear",
  "name_ko": "조각상의 눈물",
  "tier": 5,
  "unit_weight": 1000,
  "source": "v14.1_master_data"
}
```

`item_id` 생성 규칙은 M5 데이터 추출 전에 확정한다. 이름이 바뀌어도 사용자 재고 정체성이 조용히 바뀌지 않도록 migration 정책이 필요하다.

## 3. Island Reference

```json
{
  "island_id": "ostra_island",
  "name_ko": "오스트라 섬",
  "aliases": [],
  "x": -39,
  "y": -193,
  "is_ocean": false
}
```

원본 `rawData`에는 같은 위치의 별칭 키가 있으므로 canonical name과 aliases를 분리한다.

## 4. OCR Observation

```json
{
  "observation_id": "obs_...",
  "capture_id": "capture_...",
  "row_index": 0,
  "field": "from_item",
  "raw_text": "황금빛 선인장 꽃다발",
  "ocr_confidence": 0.91,
  "bounding_box": [274, 16, 638, 74]
}
```

엔진이 확신도를 제공하지 않으면 `ocr_confidence`는 `null`이며 임의 숫자를 만들지 않는다.

## 5. Barter Row Candidate

```json
{
  "barter_row_id": "barter_...",
  "island": {
    "raw": "일리야 섬",
    "value": "일리야 섬",
    "reference_id": "iliya_island",
    "match_confidence": 1.0
  },
  "remaining_count": 5,
  "from_item": {
    "raw": "황금빛 선인장 꽃다발",
    "value": "황금빛 선인장 꽃다발",
    "reference_id": "t6_golden_cactus_bouquet",
    "match_confidence": 1.0
  },
  "req_amount": 1,
  "to_item": {
    "raw": "발레노스 고래 조각상",
    "value": "발레노스 고래 조각상",
    "reference_id": "t7_balenos_whale_statue",
    "match_confidence": 1.0
  },
  "yield_amount": 1,
  "review_status": "auto_confirmed",
  "alternatives": []
}
```

`review_status` 후보:

- `auto_confirmed`
- `review_required`
- `user_confirmed`
- `user_corrected`
- `rejected`

## 6. Confirmed Barter List

```json
{
  "barter_list_id": "barter_list_...",
  "captured_at": "2026-09-21T00:00:00+09:00",
  "rows": [],
  "coverage": {
    "scan_started": true,
    "scan_finished_by_user": true,
    "unreviewed_count": 0
  }
}
```

중복 판별용 파생 키:

```text
island.reference_id + from_item.reference_id + to_item.reference_id + remaining_count
```

키가 같아도 수량이나 원문 충돌이 있으면 자동 병합하지 않고 검수한다.

## 7. Inventory Record

```json
{
  "item_id": "t5_sculptures_tear",
  "quantity": 0,
  "target_quantity": 2,
  "input_status": "confirmed",
  "revision": 7,
  "updated_at": "2026-09-21T00:00:00+09:00",
  "source": "manual_initial_input"
}
```

미입력 예:

```json
{
  "item_id": "t5_sculptures_tear",
  "quantity": null,
  "target_quantity": null,
  "input_status": "unconfirmed",
  "revision": 0,
  "updated_at": null,
  "source": null
}
```

`quantity: 0`을 기본값이나 파싱 실패 대체값으로 사용하지 않는다.

## 8. Scheduler Input

```json
{
  "barter_list_id": "barter_list_...",
  "inventory_revision": 7,
  "mode": "balance",
  "ocean_mode": "inner",
  "normal_weight": 14379,
  "max_weight": 24445,
  "parley_available": 1250000,
  "config_revision": "v14_1_compat_1"
}
```

## 9. Sortie Plan

```json
{
  "plan_id": "plan_...",
  "inventory_revision": 7,
  "barter_list_id": "barter_list_...",
  "mode": "balance",
  "status": "proposed",
  "sorties": [
    {
      "sortie_id": "sortie_1",
      "load": [],
      "stops": [],
      "parley_used": 0,
      "start_weight": 0,
      "peak_weight": 0,
      "estimated_minutes": 0,
      "proposed_inventory_delta": {}
    }
  ]
}
```

`proposed_inventory_delta`는 미리보기일 뿐 Inventory에 적용되지 않는다.

## 10. Completion Record and Transaction

```json
{
  "completion_id": "completion_...",
  "plan_id": "plan_...",
  "sortie_id": "sortie_1",
  "status": "confirmed",
  "executed_trades": [],
  "inventory_revision_before": 7,
  "inventory_revision_after": 8,
  "transaction_id": "inventory_tx_...",
  "confirmed_at": "2026-09-21T00:00:00+09:00"
}
```

```json
{
  "transaction_id": "inventory_tx_...",
  "idempotency_key": "completion_...",
  "delta": {
    "t4_marine_knights_helmet": -1,
    "t5_sculptures_tear": 1
  }
}
```

`idempotency_key`가 이미 적용되었으면 같은 delta를 다시 적용하지 않는다.

## 11. Storage Envelope

```json
{
  "schema_version": 1,
  "inventory_revision": 8,
  "inventory": [],
  "completion_records": [],
  "transactions": []
}
```

실제 저장 형식은 M4에서 결정한다. 형식과 무관하게 원자적 저장, schema migration, 백업 복구, 중복 완료 방지는 필수다.

