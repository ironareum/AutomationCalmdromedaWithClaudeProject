"""
카테고리 고정 로테이션 + 서브컨셉 히스토리 기반 선택

galaxy → aurora → nebula → stellar → galaxy (고정 순환)
서브컨셉: 최근 HISTORY_LIMIT개 제외 → priority 가중 랜덤 선택
상태 저장: used_assets.json (rotation 필드만 업데이트, 세션 데이터 보존)
"""
import json
import random
import logging
from pathlib import Path

from planner.subconcepts import get_enabled

log = logging.getLogger(__name__)

CATEGORY_ORDER = ["galaxy", "aurora", "nebula", "stellar"]
HISTORY_LIMIT = 10


def pick_category_and_subconcept(
    used_assets_path: Path,
    force_category: str | None = None,
) -> dict:
    """
    1. used_assets.json에서 category_index, used_subconcepts 읽기
    2. 카테고리 결정 (force 또는 로테이션)
    3. 해당 카테고리 서브컨셉 중 recent history 제외
    4. priority 가중 random.choices() 선택
    5. used_assets.json rotation 필드 업데이트
    반환: 선택된 subconcept dict
    """
    data = _load(used_assets_path)

    if force_category and force_category in CATEGORY_ORDER:
        category = force_category
        new_index = data.get("category_index", 0)
    else:
        idx = data.get("category_index", 0)
        category = CATEGORY_ORDER[idx % len(CATEGORY_ORDER)]
        new_index = (idx + 1) % len(CATEGORY_ORDER)

    candidates = get_enabled(category)
    if not candidates:
        log.error(f"서브컨셉 없음: {category}")
        fallback = get_enabled()
        return fallback[0] if fallback else {}

    used_recent = set(data.get("used_subconcepts", [])[-HISTORY_LIMIT:])
    fresh = [sc for sc in candidates if sc["id"] not in used_recent]
    pool = fresh if fresh else candidates

    weights = [sc.get("priority", 1.0) for sc in pool]
    chosen = random.choices(pool, weights=weights, k=1)[0]

    history = list(data.get("used_subconcepts", []))
    history.append(chosen["id"])

    stats = dict(data.get("statistics", {}))
    entry = dict(stats.get(chosen["id"], {"used": 0}))
    entry["used"] = entry.get("used", 0) + 1
    stats[chosen["id"]] = entry

    _save(used_assets_path, {
        "category_index": new_index,
        "used_subconcepts": history[-HISTORY_LIMIT:],
        "statistics": stats,
    })

    log.info(f"카테고리: {category} / 서브컨셉: {chosen['id']} ({chosen['display_name']['en']})")
    return chosen


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _save(path: Path, updates: dict):
    """rotation 관련 필드만 업데이트 (기존 세션 데이터 보존)"""
    try:
        data = _load(path)
        data.update(updates)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"rotation 상태 저장 실패: {e}")
