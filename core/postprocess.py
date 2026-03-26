from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from core.types import EventKey, TranslatedData


def _format_seconds(value: float) -> str:
    total = int(round(value))
    hour = total // 3600
    minute = (total % 3600) // 60
    second = total % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _time_of(
    values: Dict[str, float],
    event_id: Dict[EventKey, str],
    legacy_event_time: Dict[EventKey, float],
    event_key: EventKey,
) -> Optional[str]:
    token = event_id.get(event_key)
    if token is None:
        return None
    var_name = f"t_{token}"
    if var_name not in values:
        legacy_value = legacy_event_time.get(event_key)
        if legacy_value is None:
            return None
        return _format_seconds(legacy_value)
    return _format_seconds(values[var_name])


def _strip_optional_quotes(text: str) -> str:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _parse_legacy_event_var_name(var_name: str) -> Optional[EventKey]:
    # Legacy solutions may use:
    #   event_start_time(train_id,station,event_type)
    # or
    #   event_start_time[train_id,station,event_type]
    for prefix in ("event_start_time(", "event_start_time["):
        if not var_name.startswith(prefix):
            continue

        closer = ")" if prefix.endswith("(") else "]"
        if not var_name.endswith(closer):
            return None

        inner = var_name[len(prefix) : -1].strip()
        if inner.startswith("(") and inner.endswith(")"):
            inner = inner[1:-1].strip()

        parts = [_strip_optional_quotes(part) for part in inner.split(",")]
        if len(parts) != 3 or any(part == "" for part in parts):
            return None

        train_id, station, event_type = parts
        return train_id, station, event_type

    return None


def _build_legacy_event_time_map(values: Dict[str, float]) -> Dict[EventKey, float]:
    legacy_event_time: Dict[EventKey, float] = {}
    for var_name, var_value in values.items():
        event_key = _parse_legacy_event_var_name(var_name)
        if event_key is None:
            continue
        legacy_event_time[event_key] = var_value
    return legacy_event_time


def export_adjusted_timetable(
    translated: TranslatedData,
    values: Dict[str, float],
    output_path: Path,
) -> None:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: openpyxl") from exc

    event_id = {event_key: f"e{idx}" for idx, event_key in enumerate(translated.event_keys, start=1)}
    legacy_event_time = _build_legacy_event_time_map(values)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(["train_id", "station", "arrival_time", "departure_time"])

    for train_id in translated.train_ids:
        for station in translated.train_routes[train_id]:
            arr = _time_of(values, event_id, legacy_event_time, (train_id, station, "arr"))
            dep = _time_of(values, event_id, legacy_event_time, (train_id, station, "dep"))
            if arr is None and dep is None:
                continue
            worksheet.append([train_id, station, arr, dep])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
