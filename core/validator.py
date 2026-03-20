from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional

from core.types import AppConfig, MileageRow, RawTable, TimetableRow, ValidatedInput

TRAIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{1,2}):(\d{1,2})$")

REQUIRED_TIMETABLE_HEADERS = ["train_id", "station", "arrival_time", "departure_time"]
REQUIRED_MILEAGE_HEADERS = ["station", "mileage"]


def _validate_headers(headers: List[str], required: List[str], table_name: str) -> None:
    if len(headers) < len(required):
        raise ValueError(
            f"{table_name} columns must include {required} as leading columns, got {headers}."
        )
    if headers[:len(required)] != required:
        raise ValueError(
            f"{table_name} leading columns must be {required}, got {headers}."
        )


def _to_int_seconds(value: str) -> int:
    hour = int(value[0:2])
    minute = int(value[3:5])
    second = int(value[6:8])
    return hour * 3600 + minute * 60 + second


def _normalize_time(value: Optional[str], field_name: str, row_number: int) -> Optional[str]:
    if value is None:
        return None

    match = TIME_PATTERN.match(value)
    if not match:
        raise ValueError(
            f"Invalid time at row {row_number}, field '{field_name}': {value}. Expected HH:MM:SS."
        )

    hour, minute, second = [int(part) for part in match.groups()]
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError(
            f"Invalid time at row {row_number}, field '{field_name}': {value}. Expected HH:MM:SS."
        )

    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _validate_timetable_rows(table: RawTable) -> List[TimetableRow]:
    _validate_headers(table.headers, REQUIRED_TIMETABLE_HEADERS, "timetable")

    rows: List[TimetableRow] = []
    for idx, record in enumerate(table.rows, start=2):
        train_id = (record.get("train_id") or "").strip()
        station = (record.get("station") or "").strip()
        arrival_time = _normalize_time(record.get("arrival_time"), "arrival_time", idx)
        departure_time = _normalize_time(record.get("departure_time"), "departure_time", idx)

        if not train_id:
            raise ValueError(f"Empty train_id at row {idx}.")
        if not TRAIN_ID_PATTERN.match(train_id):
            raise ValueError(
                f"Invalid train_id at row {idx}: {train_id}. Use only A-Z a-z 0-9 _ -"
            )
        if not station:
            raise ValueError(f"Empty station at row {idx}.")
        if arrival_time is None and departure_time is None:
            raise ValueError(f"Both arrival_time and departure_time are empty at row {idx}.")

        if arrival_time is not None and departure_time is not None:
            if _to_int_seconds(departure_time) < _to_int_seconds(arrival_time):
                raise ValueError(
                    f"departure_time earlier than arrival_time at row {idx}: {arrival_time} -> {departure_time}."
                )

        rows.append(
            TimetableRow(
                train_id=train_id,
                station=station,
                arrival_time=arrival_time,
                departure_time=departure_time,
                row_number=idx,
            )
        )

    grouped: Dict[str, List[TimetableRow]] = defaultdict(list)
    for row in rows:
        grouped[row.train_id].append(row)

    for train_id, train_rows in grouped.items():
        if len(train_rows) < 2:
            raise ValueError(f"Train {train_id} must have at least two rows.")

        seen = set()
        for row in train_rows:
            if row.station in seen:
                raise ValueError(
                    f"Train {train_id} has duplicated station '{row.station}' at row {row.row_number}."
                )
            seen.add(row.station)

        last_row = train_rows[-1]
        if last_row.departure_time is not None:
            if last_row.arrival_time is None or last_row.departure_time != last_row.arrival_time:
                raise ValueError(
                    f"Train {train_id} last row allows departure_time only when it equals arrival_time (row {last_row.row_number})."
                )

    return rows


def _validate_mileage_rows(table: RawTable) -> List[MileageRow]:
    _validate_headers(table.headers, REQUIRED_MILEAGE_HEADERS, "mileage")

    rows: List[MileageRow] = []
    station_seen = set()
    for idx, record in enumerate(table.rows, start=2):
        station = (record.get("station") or "").strip()
        mileage_text = (record.get("mileage") or "").strip()

        if not station:
            raise ValueError(f"Empty station in mileage table at row {idx}.")
        if station in station_seen:
            raise ValueError(f"Duplicated station '{station}' in mileage table at row {idx}.")
        station_seen.add(station)

        try:
            mileage = float(mileage_text)
        except ValueError as exc:
            raise ValueError(
                f"Invalid mileage at row {idx}: {mileage_text}."
            ) from exc

        rows.append(MileageRow(station=station, mileage=mileage, row_number=idx))

    return rows


def _validate_station_coverage(
    timetable_rows: List[TimetableRow],
    mileage_rows: List[MileageRow],
) -> None:
    mileage_station_set = {item.station for item in mileage_rows}
    for row in timetable_rows:
        if row.station not in mileage_station_set:
            raise ValueError(
                f"Station '{row.station}' (row {row.row_number}) not found in mileage table."
            )


def _validate_scenarios(config: AppConfig, timetable_rows: List[TimetableRow], mileage_rows: List[MileageRow]) -> None:
    event_index = {
        (row.train_id, row.station, "arr")
        for row in timetable_rows
        if row.arrival_time is not None
    }
    event_index.update(
        {
            (row.train_id, row.station, "dep")
            for row in timetable_rows
            if row.departure_time is not None
        }
    )

    station_set = {row.station for row in mileage_rows}

    for delay in config.scenarios.delays:
        if delay.event_type not in {"arr", "dep"}:
            raise ValueError(f"Invalid delay event_type: {delay.event_type}")
        if delay.seconds < 0:
            raise ValueError("Delay seconds must be >= 0")
        if (delay.train_id, delay.station, delay.event_type) not in event_index:
            raise ValueError(
                f"Delay scenario event not found in timetable: ({delay.train_id}, {delay.station}, {delay.event_type})"
            )

    for speed_limit in config.scenarios.speed_limits:
        if speed_limit.extra_seconds < 0:
            raise ValueError("Speed limit extra_seconds must be >= 0")
        if speed_limit.start_time >= speed_limit.end_time:
            raise ValueError("Speed limit start_time must be earlier than end_time")
        if speed_limit.start_station not in station_set or speed_limit.end_station not in station_set:
            raise ValueError("Speed limit station not found in mileage table")

    for interruption in config.scenarios.interruptions:
        if interruption.start_time >= interruption.end_time:
            raise ValueError("Interruption start_time must be earlier than end_time")
        if interruption.start_station not in station_set or interruption.end_station not in station_set:
            raise ValueError("Interruption station not found in mileage table")


def _validate_solver(config: AppConfig) -> None:
    if config.solver.objective_mode not in {"delay", "abs", "cal_delay_plus_cancel"}:
        raise ValueError(
            "solver.objective_mode must be one of: delay, abs, cal_delay_plus_cancel"
        )
    if config.solver.arr_arr_headway_seconds < 0:
        raise ValueError("solver.arr_arr_headway_seconds must be >= 0")
    if config.solver.dep_dep_headway_seconds < 0:
        raise ValueError("solver.dep_dep_headway_seconds must be >= 0")
    if config.solver.dwell_seconds_at_stops < 0:
        raise ValueError("solver.dwell_seconds_at_stops must be >= 0")
    if config.solver.big_m <= 0:
        raise ValueError("solver.big_m must be > 0")
    if config.solver.tolerance_delay_seconds < 0:
        raise ValueError("solver.tolerance_delay_seconds must be >= 0")


def validate_inputs(
    config: AppConfig,
    timetable_table: RawTable,
    mileage_table: RawTable,
) -> ValidatedInput:
    timetable_rows = _validate_timetable_rows(timetable_table)
    mileage_rows = _validate_mileage_rows(mileage_table)
    _validate_station_coverage(timetable_rows, mileage_rows)
    _validate_scenarios(config, timetable_rows, mileage_rows)
    _validate_solver(config)
    return ValidatedInput(timetable_rows=timetable_rows, mileage_rows=mileage_rows)
