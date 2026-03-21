
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


# Ensure `core` package is importable when running:
#   python scripts/generate_case_library.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.loader import load_config, load_mileage_table, load_timetable
from core.translator import translate
from core.types import AppConfig, ScenarioConfig, TranslatedData, ValidatedInput
from core.validator import validate_inputs

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Missing dependency: pyyaml (required by generator).") from exc

DAY_START = 6 * 3600
DAY_END = 23 * 3600 + 59 * 60 + 59

DELAY_LEVELS = [
    ("L1", 4200, 7200, 25),
    ("L2", 1200, 4199, 25),
    ("L3", 360, 1199, 25),
    ("L4", 60, 359, 25),
]

SPEED_LEVELS = [
    ("L1_40kmh", 1800, 2400, 20),
    ("L2_80kmh", 900, 1799, 20),
    ("L3_160kmh", 420, 899, 20),
    ("L4_200kmh", 180, 419, 20),
    ("L5_250kmh", 60, 179, 20),
]

INTERRUPTION_SPAN_COUNTS = [(1, 34), (2, 33), (3, 33)]
COMBO_TYPES = [
    "delay_speedlimit",
    "speedlimit_disruption",
    "delay_disruption",
    "delay_speedlimit_disruption",
]

DEFAULT_BASE_CONFIG_CANDIDATES = [
    Path("config/mixed_scenarios_demo.yaml"),
    Path("config/delays_demo.yaml"),
    Path("config/speed_limits_demo.yaml"),
    Path("config/interruptions_demo.yaml"),
]



@dataclass(frozen=True)
class BaseData:
    app_config: AppConfig
    validated: ValidatedInput
    translated: TranslatedData
    event_candidates: List[Tuple[str, str, str, int]]
    section_candidates: List[Tuple[str, str]]
    station_order: List[str]
    station_neighbors: Dict[str, set[str]]
    section_train_count: Dict[Tuple[str, str], int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate case library for converter validation.")
    parser.add_argument("--base-config", default="", help="Base config path. If omitted, auto-select from config/*.yaml.")
    parser.add_argument("--output-root", default="tests/case_library")
    parser.add_argument("--seed", type=int, default=20260320)
    parser.add_argument("--delay-count", type=int, default=100)
    parser.add_argument("--speed-count", type=int, default=100)
    parser.add_argument("--disruption-count", type=int, default=100)
    parser.add_argument("--combo-per-type", type=int, default=100)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def resolve_base_config(arg_value: str) -> Path:
    raw = (arg_value or "").strip()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        if candidate.exists() and candidate.is_file():
            return candidate
        raise FileNotFoundError(f"Base config not found: {candidate}")

    for rel in DEFAULT_BASE_CONFIG_CANDIDATES:
        candidate = REPO_ROOT / rel
        if candidate.exists() and candidate.is_file():
            return candidate

    config_dir = REPO_ROOT / "config"
    if config_dir.exists():
        yaml_files = sorted(config_dir.glob("*.yaml"))
        if yaml_files:
            return yaml_files[0]

    raise FileNotFoundError(
        "No base config found. Please pass --base-config <path> or add a yaml file under config/."
    )


def to_hms(seconds: int) -> str:
    seconds = max(0, min(24 * 3600 - 1, int(seconds)))
    hour = seconds // 3600
    minute = (seconds % 3600) // 60
    second = seconds % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def random_window(rng: random.Random, min_len: int = 900, max_len: int = 3600) -> Tuple[int, int]:
    duration = rng.randint(min_len, max_len)
    start = rng.randint(DAY_START, DAY_END - duration)
    return start, start + duration


def window_covering_point(rng: random.Random, point: int, min_len: int = 900, max_len: int = 3600) -> Tuple[int, int]:
    duration = rng.randint(min_len, max_len)
    earliest_start = max(DAY_START, point - duration + 60)
    latest_start = min(point, DAY_END - duration)
    if earliest_start > latest_start:
        return random_window(rng, min_len=min_len, max_len=max_len)
    start = rng.randint(earliest_start, latest_start)
    return start, start + duration


def window_excluding_point(rng: random.Random, point: int, min_len: int = 900, max_len: int = 3600) -> Tuple[int, int]:
    duration = rng.randint(min_len, max_len)
    options: List[Tuple[int, int]] = []
    if DAY_START + duration < point - 60:
        end = rng.randint(DAY_START + duration, point - 60)
        options.append((end - duration, end))
    if point + 60 < DAY_END - duration:
        start = rng.randint(point + 60, DAY_END - duration)
        options.append((start, start + duration))
    if not options:
        return random_window(rng, min_len=min_len, max_len=max_len)
    return rng.choice(options)


def window_related_to_window(rng: random.Random, base_window: Tuple[int, int], overlap: bool) -> Tuple[int, int]:
    duration = rng.randint(900, 3600)
    b_start, b_end = base_window
    if overlap:
        earliest_start = max(DAY_START, b_start - duration + 60)
        latest_start = min(DAY_END - duration, b_end - 60)
        if earliest_start <= latest_start:
            start = rng.randint(earliest_start, latest_start)
            return start, start + duration
        return random_window(rng)

    candidates: List[Tuple[int, int]] = []
    if DAY_START + duration < b_start - 60:
        end = rng.randint(DAY_START + duration, b_start - 60)
        candidates.append((end - duration, end))
    if b_end + 60 < DAY_END - duration:
        start = rng.randint(b_end + 60, DAY_END - duration)
        candidates.append((start, start + duration))
    if not candidates:
        return random_window(rng)
    return rng.choice(candidates)


def build_station_neighbors(station_order: Sequence[str]) -> Dict[str, set[str]]:
    neighbors: Dict[str, set[str]] = {station: set() for station in station_order}
    for idx, station in enumerate(station_order):
        if idx > 0:
            neighbors[station].add(station_order[idx - 1])
        if idx + 1 < len(station_order):
            neighbors[station].add(station_order[idx + 1])
    return neighbors


def sections_adjacent(s1: Tuple[str, str], s2: Tuple[str, str]) -> bool:
    return bool(set(s1) & set(s2))

def pick_section_by_relation(
    rng: random.Random,
    sections: Sequence[Tuple[str, str]],
    reference: Tuple[str, str],
    relation: str,
) -> Tuple[str, str]:
    if relation == "same":
        return reference
    if relation == "adjacent":
        candidates = [s for s in sections if s != reference and sections_adjacent(s, reference)]
    else:
        candidates = [s for s in sections if s != reference and not sections_adjacent(s, reference)]
    if not candidates:
        candidates = [s for s in sections if s != reference]
    if not candidates:
        return reference
    return rng.choice(candidates)


def pick_delay_event_by_relation(
    rng: random.Random,
    base: BaseData,
    section: Tuple[str, str],
    relation: str,
) -> Tuple[str, str, str, int]:
    s1, s2 = section
    if relation == "same":
        station_pool = {s1, s2}
    elif relation == "adjacent":
        station_pool = (base.station_neighbors.get(s1, set()) | base.station_neighbors.get(s2, set())) - {s1, s2}
    else:
        near = {s1, s2} | base.station_neighbors.get(s1, set()) | base.station_neighbors.get(s2, set())
        station_pool = set(base.station_order) - near

    candidates = [item for item in base.event_candidates if item[1] in station_pool]
    if not candidates:
        candidates = base.event_candidates
    return rng.choice(candidates)


def pick_contiguous_sections(rng: random.Random, station_order: Sequence[str], span: int) -> List[Tuple[str, str]]:
    span = max(1, min(span, len(station_order) - 1))
    start_idx = rng.randint(0, len(station_order) - span - 1)
    return [(station_order[i], station_order[i + 1]) for i in range(start_idx, start_idx + span)]


def combo_relation_plan(rng: random.Random, count: int) -> List[Tuple[str, str]]:
    if count % 4 != 0:
        raise ValueError("combo-per-type must be divisible by 4.")
    time_rel = ["overlap"] * (count // 2) + ["non_overlap"] * (count - count // 2)
    space_rel = ["same"] * (count // 4) + ["adjacent"] * (count // 2) + ["distant"] * (count // 4)
    rng.shuffle(time_rel)
    rng.shuffle(space_rel)
    return list(zip(time_rel, space_rel))


def load_base_data(base_config_path: Path) -> BaseData:
    app_config = load_config(base_config_path)
    neutral = replace(app_config, scenarios=ScenarioConfig(delays=[], speed_limits=[], interruptions=[]))
    timetable = load_timetable(neutral.input.timetable_path, neutral.input.timetable_sheet_name)
    mileage = load_mileage_table(neutral.input.mileage_path, neutral.input.mileage_sheet_name)
    validated = validate_inputs(neutral, timetable, mileage)
    translated = translate(validated, neutral)

    event_candidates = [
        (tid, station, etype, translated.event_time[(tid, station, etype)])
        for (tid, station, etype) in translated.event_keys
    ]
    section_candidates = sorted(set(translated.section_min_runtime.keys()))
    station_order = [row.station for row in sorted(validated.mileage_rows, key=lambda x: x.mileage)]
    station_neighbors = build_station_neighbors(station_order)

    section_train_count: Dict[Tuple[str, str], int] = defaultdict(int)
    for train_id in translated.train_ids:
        for section in translated.train_sections[train_id]:
            section_train_count[section] += 1

    return BaseData(
        app_config=neutral,
        validated=validated,
        translated=translated,
        event_candidates=event_candidates,
        section_candidates=section_candidates,
        station_order=station_order,
        station_neighbors=station_neighbors,
        section_train_count=dict(section_train_count),
    )


def base_config_payload(case_name: str, output_dir: str, base: BaseData) -> Dict[str, object]:
    cfg = base.app_config
    return {
        "project": {"name": case_name, "output_dir": output_dir},
        "input": {
            "timetable_path": str(cfg.input.timetable_path).replace("\\", "/"),
            "mileage_path": str(cfg.input.mileage_path).replace("\\", "/"),
            "timetable_sheet_name": cfg.input.timetable_sheet_name,
            "mileage_sheet_name": cfg.input.mileage_sheet_name,
        },
        "solver": {
            "objective_delay_weight": cfg.solver.objective_delay_weight,
            "objective_mode": cfg.solver.objective_mode,
            "arr_arr_headway_seconds": cfg.solver.arr_arr_headway_seconds,
            "dep_dep_headway_seconds": cfg.solver.dep_dep_headway_seconds,
            "dwell_seconds_at_stops": cfg.solver.dwell_seconds_at_stops,
            "big_m": cfg.solver.big_m,
            "tolerance_delay_seconds": cfg.solver.tolerance_delay_seconds,
        },
        "scenarios": {"delays": [], "speed_limits": [], "interruptions": []},
        "analyze": {
            "enable_metrics": False,
            "enable_plot": False,
            "plot_grid": False,
            "plot_title": "Case Library Run",
        },
    }


def write_case(case_dir: Path, config_payload: Dict[str, object], meta_payload: Dict[str, object]) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    with (case_dir / "config.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(config_payload, f, allow_unicode=True, sort_keys=False)
    with (case_dir / "meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta_payload, f, ensure_ascii=False, indent=2)

def generate_delay_cases(rng: random.Random, base: BaseData, output_root: Path, case_index: int, count: int) -> int:
    seq: List[Tuple[str, int, int]] = []
    for level, low, high, quota in DELAY_LEVELS:
        seq.extend([(level, low, high)] * quota)
    if len(seq) != count:
        raise ValueError(f"delay-count must be {len(seq)}")
    rng.shuffle(seq)

    for level, low, high in seq:
        train_id, station, event_type, event_time = rng.choice(base.event_candidates)
        delay_seconds = rng.randint(low, high)
        case_id = f"case{case_index:04d}_delay_{level.lower()}"
        cfg = base_config_payload(case_id, f"outputs/case_library/{case_id}", base)
        cfg["scenarios"]["delays"] = [
            {
                "train_id": train_id,
                "station": station,
                "event_type": event_type,
                "seconds": delay_seconds,
            }
        ]
        meta = {
            "case_id": case_id,
            "scenario_type": "delay",
            "events": [
                {
                    "type": "delay",
                    "start_time": to_hms(event_time),
                    "end_time": to_hms(event_time),
                    "location": {"station": station},
                    "intensity": {"level": level, "seconds": delay_seconds},
                    "affected_trains_count": 1,
                }
            ],
            "time_relation": None,
            "space_relation": None,
            "seed": rng.randint(0, 2**31 - 1),
        }
        write_case(output_root / case_id, cfg, meta)
        case_index += 1
    return case_index


def generate_speed_cases(rng: random.Random, base: BaseData, output_root: Path, case_index: int, count: int) -> int:
    seq: List[Tuple[str, int, int]] = []
    for level, low, high, quota in SPEED_LEVELS:
        seq.extend([(level, low, high)] * quota)
    if len(seq) != count:
        raise ValueError(f"speed-count must be {len(seq)}")
    rng.shuffle(seq)

    for level, low, high in seq:
        section = rng.choice(base.section_candidates)
        window = random_window(rng)
        extra_seconds = rng.randint(low, high)
        case_id = f"case{case_index:04d}_speedlimit_{level.lower()}"
        cfg = base_config_payload(case_id, f"outputs/case_library/{case_id}", base)
        cfg["scenarios"]["speed_limits"] = [
            {
                "start_station": section[0],
                "end_station": section[1],
                "extra_seconds": extra_seconds,
                "start_time": to_hms(window[0]),
                "end_time": to_hms(window[1]),
            }
        ]
        meta = {
            "case_id": case_id,
            "scenario_type": "speedlimit",
            "events": [
                {
                    "type": "speed_limit",
                    "start_time": to_hms(window[0]),
                    "end_time": to_hms(window[1]),
                    "location": {"segment": [section[0], section[1]]},
                    "intensity": {"level": level, "extra_seconds": extra_seconds},
                    "affected_trains_count": base.section_train_count.get(section, 0),
                }
            ],
            "time_relation": None,
            "space_relation": None,
            "seed": rng.randint(0, 2**31 - 1),
        }
        write_case(output_root / case_id, cfg, meta)
        case_index += 1
    return case_index


def generate_disruption_cases(rng: random.Random, base: BaseData, output_root: Path, case_index: int, count: int) -> int:
    seq: List[int] = []
    for span, quota in INTERRUPTION_SPAN_COUNTS:
        seq.extend([span] * quota)
    if len(seq) != count:
        raise ValueError(f"disruption-count must be {len(seq)}")
    rng.shuffle(seq)

    for span in seq:
        sections = pick_contiguous_sections(rng, base.station_order, span=span)
        window = random_window(rng, min_len=1200, max_len=4200)
        case_id = f"case{case_index:04d}_disruption_s{span}"
        cfg = base_config_payload(case_id, f"outputs/case_library/{case_id}", base)
        cfg["scenarios"]["interruptions"] = [
            {
                "start_station": s1,
                "end_station": s2,
                "start_time": to_hms(window[0]),
                "end_time": to_hms(window[1]),
            }
            for s1, s2 in sections
        ]
        events = [
            {
                "type": "disruption",
                "start_time": to_hms(window[0]),
                "end_time": to_hms(window[1]),
                "location": {"segment": [s1, s2]},
                "intensity": {"span_sections": span},
                "affected_trains_count": base.section_train_count.get((s1, s2), 0),
            }
            for s1, s2 in sections
        ]
        meta = {
            "case_id": case_id,
            "scenario_type": "disruption",
            "events": events,
            "time_relation": None,
            "space_relation": None,
            "seed": rng.randint(0, 2**31 - 1),
        }
        write_case(output_root / case_id, cfg, meta)
        case_index += 1
    return case_index

def combo_case_payload(
    rng: random.Random,
    base: BaseData,
    case_id: str,
    combo_type: str,
    time_relation: str,
    space_relation: str,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    cfg = base_config_payload(case_id, f"outputs/case_library/{case_id}", base)
    events: List[Dict[str, object]] = []

    if combo_type == "delay_speedlimit":
        section = rng.choice(base.section_candidates)
        delay_event = pick_delay_event_by_relation(rng, base, section, relation=space_relation)
        delay_seconds = rng.randint(120, 3600)
        speed_window = window_covering_point(rng, delay_event[3]) if time_relation == "overlap" else window_excluding_point(rng, delay_event[3])
        extra_seconds = rng.randint(120, 1800)

        cfg["scenarios"]["delays"] = [{"train_id": delay_event[0], "station": delay_event[1], "event_type": delay_event[2], "seconds": delay_seconds}]
        cfg["scenarios"]["speed_limits"] = [{"start_station": section[0], "end_station": section[1], "extra_seconds": extra_seconds, "start_time": to_hms(speed_window[0]), "end_time": to_hms(speed_window[1])}]

        events.append({"type": "delay", "start_time": to_hms(delay_event[3]), "end_time": to_hms(delay_event[3]), "location": {"station": delay_event[1]}, "intensity": {"seconds": delay_seconds}, "affected_trains_count": 1})
        events.append({"type": "speed_limit", "start_time": to_hms(speed_window[0]), "end_time": to_hms(speed_window[1]), "location": {"segment": [section[0], section[1]]}, "intensity": {"extra_seconds": extra_seconds}, "affected_trains_count": base.section_train_count.get(section, 0)})

    elif combo_type == "speedlimit_disruption":
        speed_section = rng.choice(base.section_candidates)
        disruption_section = pick_section_by_relation(rng, base.section_candidates, speed_section, space_relation)
        speed_window = random_window(rng)
        disruption_window = window_related_to_window(rng, speed_window, overlap=(time_relation == "overlap"))
        extra_seconds = rng.randint(120, 1800)

        cfg["scenarios"]["speed_limits"] = [{"start_station": speed_section[0], "end_station": speed_section[1], "extra_seconds": extra_seconds, "start_time": to_hms(speed_window[0]), "end_time": to_hms(speed_window[1])}]
        cfg["scenarios"]["interruptions"] = [{"start_station": disruption_section[0], "end_station": disruption_section[1], "start_time": to_hms(disruption_window[0]), "end_time": to_hms(disruption_window[1])}]

        events.append({"type": "speed_limit", "start_time": to_hms(speed_window[0]), "end_time": to_hms(speed_window[1]), "location": {"segment": [speed_section[0], speed_section[1]]}, "intensity": {"extra_seconds": extra_seconds}, "affected_trains_count": base.section_train_count.get(speed_section, 0)})
        events.append({"type": "disruption", "start_time": to_hms(disruption_window[0]), "end_time": to_hms(disruption_window[1]), "location": {"segment": [disruption_section[0], disruption_section[1]]}, "intensity": {"span_sections": 1}, "affected_trains_count": base.section_train_count.get(disruption_section, 0)})

    elif combo_type == "delay_disruption":
        disruption_section = rng.choice(base.section_candidates)
        delay_event = pick_delay_event_by_relation(rng, base, disruption_section, relation=space_relation)
        delay_seconds = rng.randint(120, 3600)
        disruption_window = window_covering_point(rng, delay_event[3]) if time_relation == "overlap" else window_excluding_point(rng, delay_event[3])

        cfg["scenarios"]["delays"] = [{"train_id": delay_event[0], "station": delay_event[1], "event_type": delay_event[2], "seconds": delay_seconds}]
        cfg["scenarios"]["interruptions"] = [{"start_station": disruption_section[0], "end_station": disruption_section[1], "start_time": to_hms(disruption_window[0]), "end_time": to_hms(disruption_window[1])}]

        events.append({"type": "delay", "start_time": to_hms(delay_event[3]), "end_time": to_hms(delay_event[3]), "location": {"station": delay_event[1]}, "intensity": {"seconds": delay_seconds}, "affected_trains_count": 1})
        events.append({"type": "disruption", "start_time": to_hms(disruption_window[0]), "end_time": to_hms(disruption_window[1]), "location": {"segment": [disruption_section[0], disruption_section[1]]}, "intensity": {"span_sections": 1}, "affected_trains_count": base.section_train_count.get(disruption_section, 0)})

    elif combo_type == "delay_speedlimit_disruption":
        speed_section = rng.choice(base.section_candidates)
        disruption_section = pick_section_by_relation(rng, base.section_candidates, speed_section, relation=space_relation)
        delay_event = pick_delay_event_by_relation(rng, base, speed_section, relation=space_relation)
        delay_seconds = rng.randint(120, 3600)
        extra_seconds = rng.randint(120, 1800)

        speed_window = window_covering_point(rng, delay_event[3])
        disruption_window = window_related_to_window(rng, speed_window, overlap=(time_relation == "overlap"))

        cfg["scenarios"]["delays"] = [{"train_id": delay_event[0], "station": delay_event[1], "event_type": delay_event[2], "seconds": delay_seconds}]
        cfg["scenarios"]["speed_limits"] = [{"start_station": speed_section[0], "end_station": speed_section[1], "extra_seconds": extra_seconds, "start_time": to_hms(speed_window[0]), "end_time": to_hms(speed_window[1])}]
        cfg["scenarios"]["interruptions"] = [{"start_station": disruption_section[0], "end_station": disruption_section[1], "start_time": to_hms(disruption_window[0]), "end_time": to_hms(disruption_window[1])}]

        events.append({"type": "delay", "start_time": to_hms(delay_event[3]), "end_time": to_hms(delay_event[3]), "location": {"station": delay_event[1]}, "intensity": {"seconds": delay_seconds}, "affected_trains_count": 1})
        events.append({"type": "speed_limit", "start_time": to_hms(speed_window[0]), "end_time": to_hms(speed_window[1]), "location": {"segment": [speed_section[0], speed_section[1]]}, "intensity": {"extra_seconds": extra_seconds}, "affected_trains_count": base.section_train_count.get(speed_section, 0)})
        events.append({"type": "disruption", "start_time": to_hms(disruption_window[0]), "end_time": to_hms(disruption_window[1]), "location": {"segment": [disruption_section[0], disruption_section[1]]}, "intensity": {"span_sections": 1}, "affected_trains_count": base.section_train_count.get(disruption_section, 0)})

    else:
        raise ValueError(f"Unsupported combo type: {combo_type}")

    meta = {
        "case_id": case_id,
        "scenario_type": "combo",
        "combo_type": combo_type,
        "events": events,
        "time_relation": time_relation,
        "space_relation": space_relation,
        "seed": rng.randint(0, 2**31 - 1),
    }
    return cfg, meta


def generate_combo_cases(rng: random.Random, base: BaseData, output_root: Path, case_index: int, per_type: int) -> int:
    relations = combo_relation_plan(rng, per_type)
    for combo_type in COMBO_TYPES:
        for time_relation, space_relation in relations:
            case_id = f"case{case_index:04d}_combo_{combo_type}"
            cfg, meta = combo_case_payload(rng, base, case_id, combo_type, time_relation, space_relation)
            write_case(output_root / case_id, cfg, meta)
            case_index += 1
    return case_index

def write_manifest(
    output_root: Path,
    base_config: Path,
    seed: int,
    delay_count: int,
    speed_count: int,
    disruption_count: int,
    combo_per_type: int,
) -> None:
    payload = {
        "base_config": str(base_config).replace("\\", "/"),
        "seed": seed,
        "distribution": {
            "delay": delay_count,
            "speedlimit": speed_count,
            "disruption": disruption_count,
            "combo": {
                "delay_speedlimit": combo_per_type,
                "speedlimit_disruption": combo_per_type,
                "delay_disruption": combo_per_type,
                "delay_speedlimit_disruption": combo_per_type,
                "total": combo_per_type * len(COMBO_TYPES),
            },
            "total": delay_count + speed_count + disruption_count + combo_per_type * len(COMBO_TYPES),
        },
    }
    with (output_root / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    args = parse_args()
    if args.delay_count != 100:
        raise ValueError("delay-count must be 100 (4*25).")
    if args.speed_count != 100:
        raise ValueError("speed-count must be 100 (5*20).")
    if args.disruption_count != 100:
        raise ValueError("disruption-count must be 100 (34/33/33).")
    if args.combo_per_type != 100:
        raise ValueError("combo-per-type must be 100 (4 types * 100 = 400).")

    base_config = resolve_base_config(args.base_config)

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = REPO_ROOT / output_root
    output_root.mkdir(parents=True, exist_ok=True)
    if args.clean and output_root.exists():
        for case_dir in output_root.glob("case*"):
            if case_dir.is_dir():
                shutil.rmtree(case_dir)
        manifest_path = output_root / "manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()

    rng = random.Random(args.seed)
    base = load_base_data(base_config)

    case_index = 1
    case_index = generate_delay_cases(rng, base, output_root, case_index, args.delay_count)
    case_index = generate_speed_cases(rng, base, output_root, case_index, args.speed_count)
    case_index = generate_disruption_cases(rng, base, output_root, case_index, args.disruption_count)
    case_index = generate_combo_cases(rng, base, output_root, case_index, args.combo_per_type)

    write_manifest(
        output_root=output_root,
        base_config=base_config,
        seed=args.seed,
        delay_count=args.delay_count,
        speed_count=args.speed_count,
        disruption_count=args.disruption_count,
        combo_per_type=args.combo_per_type,
    )

    print(f"Generated {case_index - 1} cases under {output_root}")


if __name__ == "__main__":
    main()

