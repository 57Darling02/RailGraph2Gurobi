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
    event_key: EventKey,
) -> Optional[str]:
    token = event_id.get(event_key)
    if token is None:
        return None
    var_name = f"t_{token}"
    if var_name not in values:
        return None
    return _format_seconds(values[var_name])


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

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(["train_id", "station", "arrival_time", "departure_time"])

    for train_id in translated.train_ids:
        for station in translated.train_routes[train_id]:
            arr = _time_of(values, event_id, (train_id, station, "arr"))
            dep = _time_of(values, event_id, (train_id, station, "dep"))
            if arr is None and dep is None:
                continue
            worksheet.append([train_id, station, arr, dep])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
