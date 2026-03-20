from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from core.types import (
    AppConfig,
    EventKey,
    OrderKey,
    SectionKey,
    TimetableRow,
    TrainSectionKey,
    TranslatedData,
    ValidatedInput,
)


def _time_to_seconds(value: str) -> int:
    hour = int(value[0:2])
    minute = int(value[3:5])
    second = int(value[6:8])
    return hour * 3600 + minute * 60 + second


def _build_mileage_map(validated: ValidatedInput) -> Dict[str, float]:
    return {item.station: item.mileage for item in validated.mileage_rows}


def _group_train_rows(validated: ValidatedInput) -> Dict[str, List[TimetableRow]]:
    grouped: Dict[str, List[TimetableRow]] = defaultdict(list)
    for row in validated.timetable_rows:
        grouped[row.train_id].append(row)
    return grouped


def _derive_direction(route: List[str], mileage_map: Dict[str, float], train_id: str) -> str:
    first_station = route[0]
    last_station = route[-1]
    first_mileage = mileage_map[first_station]
    last_mileage = mileage_map[last_station]
    if last_mileage == first_mileage:
        raise ValueError(
            f"Cannot derive direction for train {train_id}: origin and destination mileage are equal."
        )
    return "down" if last_mileage > first_mileage else "up"


def _get_same_sub_route(route1: List[str], route2: List[str]) -> List[SectionKey]:
    same_sub_route: List[SectionKey] = []
    sub_route: List[str] = [station for station in route1 if station in route2]

    for i in range(len(sub_route) - 1):
        s = sub_route[i]
        s_next = sub_route[i + 1]
        index_s_r1 = route1.index(s)
        index_s_next_r1 = route1.index(s_next)
        index_s_r2 = route2.index(s)
        index_s_next_r2 = route2.index(s_next)
        if (index_s_next_r1 - index_s_r1 == 1) and (index_s_next_r2 - index_s_r2 == 1):
            same_sub_route.append((s, s_next))
    return same_sub_route


def _build_train_order_pairs(
    train_ids: List[str],
    train_routes: Dict[str, List[str]],
) -> tuple[List[OrderKey], List[OrderKey], List[OrderKey], List[OrderKey]]:
    arr_order_pair: List[OrderKey] = []
    dep_order_pair: List[OrderKey] = []
    arr_order_single: List[OrderKey] = []
    dep_order_single: List[OrderKey] = []

    for i, tr1 in enumerate(train_ids):
        route1 = train_routes[tr1]
        for tr2 in train_ids[i + 1 :]:
            route2 = train_routes[tr2]
            sub_route_pair = _get_same_sub_route(route1, route2)
            stations = set()
            for s, s_next in sub_route_pair:
                for station in (s, s_next):
                    if station in stations:
                        continue
                    stations.add(station)
                    arr_order_pair.extend([(tr1, tr2, station, "arr"), (tr2, tr1, station, "arr")])
                    dep_order_pair.extend([(tr1, tr2, station, "dep"), (tr2, tr1, station, "dep")])
                    arr_order_single.append((tr1, tr2, station, "arr"))
                    dep_order_single.append((tr1, tr2, station, "dep"))

    return arr_order_pair, dep_order_pair, arr_order_single, dep_order_single


def translate(validated: ValidatedInput, config: AppConfig) -> TranslatedData:
    del config  # kept for forward compatibility

    mileage_map = _build_mileage_map(validated)
    grouped = _group_train_rows(validated)

    train_ids = list(grouped.keys())
    train_routes: Dict[str, List[str]] = {}
    train_directions: Dict[str, str] = {}
    train_origins: Dict[str, str] = {}
    train_destinations: Dict[str, str] = {}
    train_stops: Dict[str, List[str]] = {}
    train_sections: Dict[str, List[SectionKey]] = {}

    event_keys: List[EventKey] = []
    event_time: Dict[EventKey, int] = {}

    station_dwell_all: Dict[str, List[int]] = defaultdict(list)
    section_runtime_all: Dict[SectionKey, List[int]] = defaultdict(list)
    planned_section_runtime: Dict[TrainSectionKey, int] = {}

    for train_id in train_ids:
        rows = grouped[train_id]
        route = [row.station for row in rows]
        train_routes[train_id] = route
        train_directions[train_id] = _derive_direction(route, mileage_map, train_id)
        train_origins[train_id] = route[0]
        train_destinations[train_id] = route[-1]

        sections: List[SectionKey] = []
        stops: List[str] = []
        for index, row in enumerate(rows):
            if row.arrival_time is not None:
                key = (train_id, row.station, "arr")
                event_keys.append(key)
                event_time[key] = _time_to_seconds(row.arrival_time)
            if row.departure_time is not None:
                key = (train_id, row.station, "dep")
                event_keys.append(key)
                event_time[key] = _time_to_seconds(row.departure_time)

            if row.arrival_time is not None and row.departure_time is not None:
                arr_s = _time_to_seconds(row.arrival_time)
                dep_s = _time_to_seconds(row.departure_time)
                dwell = dep_s - arr_s
                station_dwell_all[row.station].append(dwell)
                if dwell > 0:
                    stops.append(row.station)

            if index < len(rows) - 1:
                next_row = rows[index + 1]
                section = (row.station, next_row.station)
                sections.append(section)
                if row.departure_time is None or next_row.arrival_time is None:
                    raise ValueError(
                        f"Missing departure/arrival for runtime computation: {train_id} {row.station}->{next_row.station}"
                    )
                runtime = _time_to_seconds(next_row.arrival_time) - _time_to_seconds(row.departure_time)
                if runtime < 0:
                    raise ValueError(
                        f"Negative runtime detected for {train_id} section {row.station}->{next_row.station}"
                    )
                section_runtime_all[section].append(runtime)
                planned_section_runtime[(train_id, row.station, next_row.station)] = runtime

        train_sections[train_id] = sections
        train_stops[train_id] = stops

    station_min_dwell = {station: min(values) for station, values in station_dwell_all.items()}
    section_min_runtime = {section: min(values) for section, values in section_runtime_all.items()}
    (
        arr_order_pair,
        dep_order_pair,
        arr_order_single,
        dep_order_single,
    ) = _build_train_order_pairs(train_ids, train_routes)

    return TranslatedData(
        train_ids=train_ids,
        train_directions=train_directions,
        train_routes=train_routes,
        train_origins=train_origins,
        train_destinations=train_destinations,
        train_stops=train_stops,
        event_keys=event_keys,
        event_time=event_time,
        station_min_dwell=station_min_dwell,
        section_min_runtime=section_min_runtime,
        train_sections=train_sections,
        planned_section_runtime=planned_section_runtime,
        arr_order_pair=arr_order_pair,
        dep_order_pair=dep_order_pair,
        arr_order_single=arr_order_single,
        dep_order_single=dep_order_single,
    )
