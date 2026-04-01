from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import shutil
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

# Ensure project imports work when running as:
#   python scripts/import_lp.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.loader import load_config, load_mileage_table, load_timetable
from core.translator import translate
from core.types import AppConfig, ScenarioConfig, TranslatedData
from core.validator import validate_inputs

SECTION_BREAKS = {"bounds", "binary", "general", "generals", "end"}
LP_SENSES = ("<=", ">=", "=")
NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


@dataclass(frozen=True)
class SectionRecord:
    train_id: str
    start_station: str
    end_station: str
    dep_token: str
    arr_token: str
    dep_time: int
    arr_time: int
    planned_runtime: int


@dataclass(frozen=True)
class WindowCandidate:
    start_time: int
    end_time: int
    covered_tokens: FrozenSet[str]


def _require_yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: pyyaml") from exc
    return yaml


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import external .lp files into standardized case yaml + output layout."
    )
    parser.add_argument("--lp-root", default="tests/lp", help="Root folder containing *.lp files.")
    parser.add_argument("--base-config", default="config/base_demo.yaml", help="Template config used as base.")
    parser.add_argument("--generated-config-root", default="tests/generated_configs_lp", help="Generated yaml root.")
    parser.add_argument("--output-root", default="outputs/lp_import", help="Per-case output root.")
    parser.add_argument("--summary-csv", default="outputs/lp_import/import_lp_summary.csv", help="Import summary CSV.")
    parser.add_argument("--summary-json", default="outputs/lp_import/import_lp_summary.json", help="Import summary JSON.")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N lp files (0 = all).")
    parser.add_argument("--clean", action="store_true", help="Clean generated config/output roots before importing.")
    parser.add_argument(
        "--scenario-inference",
        choices=("auto", "require", "off"),
        default="auto",
        help="Infer build.scenarios from LP + timetable/mileage. 'auto' tries and falls back to empty, 'require' fails on inference errors.",
    )
    parser.add_argument("--timetable-path", default="", help="Override project.timetable_path for imported configs and scenario inference.")
    parser.add_argument("--mileage-path", default="", help="Override project.mileage_path for imported configs and scenario inference.")
    parser.add_argument("--timetable-sheet-name", default="", help="Override project.timetable_sheet_name for imported configs and scenario inference.")
    parser.add_argument("--mileage-sheet-name", default="", help="Override project.mileage_sheet_name for imported configs and scenario inference.")
    return parser.parse_args()


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _to_posix(path_value: Path) -> str:
    return str(path_value).replace("\\", "/")


def _normalize_path_text(path_text: str) -> str:
    return str(Path(path_text)).replace("\\", "/")


def _sanitize_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-") or "case"


def _dedup_case_id(base_id: str, seen: Dict[str, int]) -> str:
    count = seen.get(base_id, 0) + 1
    seen[base_id] = count
    if count == 1:
        return base_id
    return f"{base_id}_{count}"


def _to_hms(seconds: int) -> str:
    total = max(0, min(86399, int(seconds)))
    hour = total // 3600
    minute = (total % 3600) // 60
    second = total % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _to_int(value: float) -> int:
    rounded = int(round(value))
    if abs(value - rounded) > 1e-6:
        raise ValueError(f"Expected integer-like numeric value, got {value}")
    return rounded


def _build_empty_scenarios() -> Dict[str, object]:
    return {
        "delays": [],
        "speed_limits": [],
        "interruptions": [],
    }


def _build_case_config(
    base_payload: Dict[str, object],
    case_name: str,
    output_dir: Path,
    scenarios: Optional[Dict[str, object]] = None,
    timetable_path_override: str = "",
    mileage_path_override: str = "",
    timetable_sheet_override: str = "",
    mileage_sheet_override: str = "",
) -> Dict[str, object]:
    payload = copy.deepcopy(base_payload)

    project = dict(payload.get("project", {}))
    legacy_input = dict(payload.get("input", {}))
    required_project_defaults = {
        "timetable_path": "",
        "mileage_path": "",
        "timetable_sheet_name": "Sheet1",
        "mileage_sheet_name": "Sheet1",
    }
    for key, default_value in required_project_defaults.items():
        current_value = project.get(key)
        current_text = "" if current_value is None else str(current_value).strip()
        if current_text != "":
            continue
        legacy_value = legacy_input.get(key, default_value)
        project[key] = default_value if legacy_value is None else legacy_value

    if timetable_path_override.strip():
        project["timetable_path"] = _normalize_path_text(timetable_path_override)
    if mileage_path_override.strip():
        project["mileage_path"] = _normalize_path_text(mileage_path_override)
    if timetable_sheet_override.strip():
        project["timetable_sheet_name"] = timetable_sheet_override.strip()
    if mileage_sheet_override.strip():
        project["mileage_sheet_name"] = mileage_sheet_override.strip()

    project["name"] = case_name
    project["output_dir"] = _to_posix(output_dir)
    payload["project"] = project

    build = dict(payload.get("build", {}))
    build["scenarios"] = copy.deepcopy(scenarios or _build_empty_scenarios())
    payload["build"] = build

    solve = dict(payload.get("solve", {}))
    if not solve:
        solve = dict(payload.get("solver", {}))
    solve["lp_path"] = ""
    payload["solve"] = solve

    export_cfg = dict(payload.get("export-timetable", payload.get("export_timetable", {})))
    export_cfg["sol_path"] = ""
    payload["export-timetable"] = export_cfg
    payload.pop("export_timetable", None)

    analyze = dict(payload.get("analyze", {}))
    analyze.setdefault("plot_grid", False)
    analyze.setdefault("plot_title", "Train Timetable")
    analyze["adj_timetable_path"] = ""
    analyze.setdefault("adj_timetable_sheet_name", "Sheet1")
    payload["analyze"] = analyze

    payload.pop("scenarios", None)
    return payload


def _write_csv(path: Path, records: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(records[0].keys()) if records else ["index", "lp_file", "status", "error"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _build_inference_config(
    base_config_path: Path,
    timetable_path_override: str,
    mileage_path_override: str,
    timetable_sheet_override: str,
    mileage_sheet_override: str,
) -> AppConfig:
    loaded = load_config(base_config_path)
    input_config = loaded.input

    if timetable_path_override.strip():
        input_config = replace(input_config, timetable_path=Path(timetable_path_override.strip()))
    if mileage_path_override.strip():
        input_config = replace(input_config, mileage_path=Path(mileage_path_override.strip()))
    if timetable_sheet_override.strip():
        input_config = replace(input_config, timetable_sheet_name=timetable_sheet_override.strip())
    if mileage_sheet_override.strip():
        input_config = replace(input_config, mileage_sheet_name=mileage_sheet_override.strip())

    return replace(
        loaded,
        input=input_config,
        scenarios=ScenarioConfig(delays=[], speed_limits=[], interruptions=[]),
    )


def _load_translated(config: AppConfig) -> TranslatedData:
    timetable_table = load_timetable(
        config.input.timetable_path,
        config.input.timetable_sheet_name,
    )
    mileage_table = load_mileage_table(
        config.input.mileage_path,
        config.input.mileage_sheet_name,
    )
    validated = validate_inputs(config, timetable_table, mileage_table)
    return translate(validated, config)


def _parse_linear_expression(text: str) -> Dict[str, float]:
    tokens = text.replace("+", " + ").replace("-", " - ").split()
    coefficients: Dict[str, float] = {}
    index = 0

    while index < len(tokens):
        sign = 1.0
        token = tokens[index]
        if token == "+":
            index += 1
        elif token == "-":
            sign = -1.0
            index += 1

        if index >= len(tokens):
            raise ValueError(f"Invalid LP linear expression: {text}")

        coefficient = 1.0
        token = tokens[index]
        if NUMBER_PATTERN.match(token):
            coefficient = float(token)
            index += 1
            if index >= len(tokens):
                raise ValueError(f"Missing variable after coefficient in expression: {text}")

        var_name = tokens[index]
        coefficients[var_name] = coefficients.get(var_name, 0.0) + sign * coefficient
        index += 1

    return coefficients


def _parse_constraint_line(text: str) -> Tuple[str, Dict[str, float], str, float]:
    if ":" not in text:
        raise ValueError(f"Invalid LP constraint line without ':': {text}")
    name, remainder = text.split(":", 1)
    body = remainder.strip()
    for sense in LP_SENSES:
        marker = f" {sense} "
        if marker not in body:
            continue
        left, rhs_text = body.split(marker, 1)
        return name.strip(), _parse_linear_expression(left.strip()), sense, float(rhs_text.strip())
    raise ValueError(f"Unsupported LP constraint sense in line: {text}")


def _iter_lp_constraints(lp_path: Path) -> Iterable[Tuple[str, Dict[str, float], str, float]]:
    in_subject_to = False
    with lp_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            text = raw_line.strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered == "subject to":
                in_subject_to = True
                continue
            if not in_subject_to:
                continue
            if lowered in SECTION_BREAKS:
                break
            yield _parse_constraint_line(text)


def _strip_constraint_counter(name: str) -> str:
    return re.sub(r"_\d+$", "", name)


def _build_indexes(
    translated: TranslatedData,
) -> Tuple[Dict[str, Tuple[str, str, str]], Dict[str, SectionRecord], Dict[str, SectionRecord], Dict[Tuple[str, str], List[SectionRecord]]]:
    event_by_token: Dict[str, Tuple[str, str, str]] = {}
    token_by_event: Dict[Tuple[str, str, str], str] = {}
    section_by_arr_token: Dict[str, SectionRecord] = {}
    section_by_dep_token: Dict[str, SectionRecord] = {}
    section_records_by_section: Dict[Tuple[str, str], List[SectionRecord]] = {}

    for index, event_key in enumerate(translated.event_keys, start=1):
        token = f"e{index}"
        event_by_token[token] = event_key
        token_by_event[event_key] = token

    for train_id, sections in translated.train_sections.items():
        for start_station, end_station in sections:
            dep_key = (train_id, start_station, "dep")
            arr_key = (train_id, end_station, "arr")
            dep_token = token_by_event[dep_key]
            arr_token = token_by_event[arr_key]
            record = SectionRecord(
                train_id=train_id,
                start_station=start_station,
                end_station=end_station,
                dep_token=dep_token,
                arr_token=arr_token,
                dep_time=translated.event_time[dep_key],
                arr_time=translated.event_time[arr_key],
                planned_runtime=translated.planned_section_runtime[(train_id, start_station, end_station)],
            )
            section_by_arr_token[arr_token] = record
            section_by_dep_token[dep_token] = record
            section_records_by_section.setdefault((start_station, end_station), []).append(record)

    for records in section_records_by_section.values():
        records.sort(key=lambda item: (item.dep_time, item.arr_time, item.train_id))

    return event_by_token, section_by_arr_token, section_by_dep_token, section_records_by_section


def _find_token(coefficients: Dict[str, float], expected_prefix: str, expected_value: float) -> Optional[str]:
    for var_name, coefficient in coefficients.items():
        if not var_name.startswith(expected_prefix):
            continue
        if abs(coefficient - expected_value) <= 1e-6:
            return var_name[len(expected_prefix):]
    return None


def _infer_speed_windows(
    records: List[SectionRecord],
    target_tokens: Set[str],
) -> Tuple[List[Tuple[int, int]], str]:
    target = frozenset(target_tokens)
    if not target:
        return [], "empty"

    start_candidates = sorted(
        {
            0,
            *[max(0, record.arr_time - 1) for record in records],
            *[min(86399, record.arr_time) for record in records],
        }
    )
    end_candidates = sorted(
        {
            1,
            86399,
            *[max(1, min(86399, record.dep_time)) for record in records],
            *[max(1, min(86399, record.dep_time + 1)) for record in records],
        }
    )

    candidates: List[WindowCandidate] = []
    seen_windows: Set[Tuple[int, int, FrozenSet[str]]] = set()
    for start_time in start_candidates:
        for end_time in end_candidates:
            if start_time >= end_time:
                continue
            covered = frozenset(
                record.arr_token
                for record in records
                if record.dep_time < end_time and record.arr_time > start_time
            )
            if not covered or not covered.issubset(target):
                continue
            key = (start_time, end_time, covered)
            if key in seen_windows:
                continue
            seen_windows.add(key)
            candidates.append(
                WindowCandidate(
                    start_time=start_time,
                    end_time=end_time,
                    covered_tokens=covered,
                )
            )

    exact_candidates = [item for item in candidates if item.covered_tokens == target]
    if exact_candidates:
        best = min(
            exact_candidates,
            key=lambda item: (item.end_time - item.start_time, item.start_time, item.end_time),
        )
        return [(best.start_time, best.end_time)], "exact"

    remaining = set(target)
    chosen: List[WindowCandidate] = []
    while remaining:
        options = [item for item in candidates if item.covered_tokens & remaining]
        if not options:
            raise ValueError(f"Unable to infer speed-limit window from affected tokens: {sorted(target)}")
        best = min(
            options,
            key=lambda item: (
                -len(item.covered_tokens & remaining),
                item.end_time - item.start_time,
                item.start_time,
                item.end_time,
            ),
        )
        chosen.append(best)
        remaining -= set(best.covered_tokens)

    windows = sorted({(item.start_time, item.end_time) for item in chosen})
    return windows, "cover"


def _infer_scenarios_from_lp(
    lp_path: Path,
    translated: TranslatedData,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    event_by_token, section_by_arr_token, section_by_dep_token, section_records_by_section = _build_indexes(translated)

    delay_set: Set[Tuple[str, str, str, int]] = set()
    speed_groups: Dict[Tuple[str, str, int], Set[str]] = {}
    interrupt_before: Dict[str, Tuple[str, int]] = {}
    interrupt_after: Dict[str, Tuple[str, int]] = {}

    delay_pattern = re.compile(r"^primary_delay_(e\d+)$")
    speed_pattern = re.compile(r"^speed_limit_(e\d+)$")
    interrupt_before_pattern = re.compile(r"^interrupt_before_(e\d+)$")
    interrupt_after_pattern = re.compile(r"^interrupt_after_(e\d+)$")

    for raw_name, coefficients, _sense, rhs in _iter_lp_constraints(lp_path):
        name = _strip_constraint_counter(raw_name)

        delay_match = delay_pattern.match(name)
        if delay_match:
            event_token = delay_match.group(1)
            event_key = event_by_token[event_token]
            planned = translated.event_time[event_key]
            seconds = _to_int(rhs - planned)
            delay_set.add((event_key[0], event_key[1], event_key[2], seconds))
            continue

        speed_match = speed_pattern.match(name)
        if speed_match:
            arr_token = speed_match.group(1)
            record = section_by_arr_token.get(arr_token)
            if record is None:
                raise ValueError(f"Speed-limit constraint references unknown arrival token: {arr_token}")
            dep_token = _find_token(coefficients, "t_", -1.0)
            if dep_token is None:
                raise ValueError(f"Speed-limit constraint missing departure variable: {raw_name}")
            if dep_token != record.dep_token:
                raise ValueError(
                    f"Speed-limit constraint token mismatch: expected dep {record.dep_token}, got {dep_token}"
                )
            extra_seconds = _to_int(rhs - record.planned_runtime)
            group_key = (record.start_station, record.end_station, extra_seconds)
            speed_groups.setdefault(group_key, set()).add(arr_token)
            continue

        before_match = interrupt_before_pattern.match(name)
        if before_match:
            arr_token = before_match.group(1)
            record = section_by_arr_token.get(arr_token)
            if record is None:
                raise ValueError(f"Interruption constraint references unknown arrival token: {arr_token}")
            z_var = next((var_name for var_name in coefficients if var_name.startswith("z_interrupt_")), None)
            if z_var is None:
                raise ValueError(f"Interruption constraint missing z variable: {raw_name}")
            z_coef = coefficients[z_var]
            start_time = _to_int(rhs - z_coef)
            interrupt_before[z_var] = (arr_token, start_time)
            continue

        after_match = interrupt_after_pattern.match(name)
        if after_match:
            dep_token = after_match.group(1)
            record = section_by_dep_token.get(dep_token)
            if record is None:
                raise ValueError(f"Interruption constraint references unknown departure token: {dep_token}")
            z_var = next((var_name for var_name in coefficients if var_name.startswith("z_interrupt_")), None)
            if z_var is None:
                raise ValueError(f"Interruption constraint missing z variable: {raw_name}")
            interrupt_after[z_var] = (dep_token, _to_int(rhs))

    interruption_set: Set[Tuple[str, str, int, int]] = set()
    all_z_vars = set(interrupt_before) | set(interrupt_after)
    for z_var in all_z_vars:
        if z_var not in interrupt_before or z_var not in interrupt_after:
            raise ValueError(f"Unpaired interruption constraints for {z_var} in {lp_path}")
        arr_token, start_time = interrupt_before[z_var]
        dep_token, end_time = interrupt_after[z_var]
        arr_record = section_by_arr_token[arr_token]
        dep_record = section_by_dep_token[dep_token]
        if (arr_record.start_station, arr_record.end_station) != (dep_record.start_station, dep_record.end_station):
            raise ValueError(f"Interruption section mismatch for {z_var}")
        interruption_set.add(
            (
                dep_record.start_station,
                dep_record.end_station,
                start_time,
                end_time,
            )
        )

    speed_limits: List[Dict[str, object]] = []
    speed_group_notes: List[str] = []
    for (start_station, end_station, extra_seconds), affected_tokens in sorted(speed_groups.items()):
        section_key = (start_station, end_station)
        windows, mode = _infer_speed_windows(section_records_by_section[section_key], affected_tokens)
        speed_group_notes.append(
            f"{start_station}->{end_station} +{extra_seconds}s [{mode}] x{len(windows)}"
        )
        for start_time, end_time in windows:
            speed_limits.append(
                {
                    "start_station": start_station,
                    "end_station": end_station,
                    "extra_seconds": extra_seconds,
                    "start_time": _to_hms(start_time),
                    "end_time": _to_hms(end_time),
                }
            )

    scenarios = {
        "delays": [
            {
                "train_id": train_id,
                "station": station,
                "event_type": event_type,
                "seconds": seconds,
            }
            for train_id, station, event_type, seconds in sorted(delay_set)
        ],
        "speed_limits": sorted(
            speed_limits,
            key=lambda item: (
                str(item["start_station"]),
                str(item["end_station"]),
                int(item["extra_seconds"]),
                str(item["start_time"]),
                str(item["end_time"]),
            ),
        ),
        "interruptions": [
            {
                "start_station": start_station,
                "end_station": end_station,
                "start_time": _to_hms(start_time),
                "end_time": _to_hms(end_time),
            }
            for start_station, end_station, start_time, end_time in sorted(interruption_set)
        ],
    }
    diagnostics = {
        "delay_count": len(scenarios["delays"]),
        "speed_limit_count": len(scenarios["speed_limits"]),
        "interruption_count": len(scenarios["interruptions"]),
        "speed_limit_groups": "; ".join(speed_group_notes),
    }
    return scenarios, diagnostics


def main() -> None:
    args = _parse_args()
    yaml = _require_yaml()

    lp_root = _resolve_path(args.lp_root)
    base_config_path = _resolve_path(args.base_config)
    generated_config_root = _resolve_path(args.generated_config_root)
    output_root = _resolve_path(args.output_root)
    summary_csv = _resolve_path(args.summary_csv)
    summary_json = _resolve_path(args.summary_json)

    if not lp_root.exists():
        raise FileNotFoundError(f"lp root not found: {lp_root}")
    if not base_config_path.exists():
        raise FileNotFoundError(f"base config not found: {base_config_path}")

    if args.clean:
        if generated_config_root.exists():
            shutil.rmtree(generated_config_root)
        if output_root.exists():
            shutil.rmtree(output_root)

    generated_config_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    with base_config_path.open("r", encoding="utf-8") as file:
        base_payload = yaml.safe_load(file) or {}

    inference_app_config: Optional[AppConfig] = None
    inference_context: Optional[TranslatedData] = None
    inference_error = ""
    if args.scenario_inference != "off":
        try:
            inference_app_config = _build_inference_config(
                base_config_path=base_config_path,
                timetable_path_override=args.timetable_path,
                mileage_path_override=args.mileage_path,
                timetable_sheet_override=args.timetable_sheet_name,
                mileage_sheet_override=args.mileage_sheet_name,
            )
            inference_context = _load_translated(inference_app_config)
        except Exception as exc:
            inference_error = str(exc)
            if args.scenario_inference == "require":
                raise

    lp_files = sorted(lp_root.rglob("*.lp"))
    if args.limit > 0:
        lp_files = lp_files[: args.limit]

    seen_ids: Dict[str, int] = {}
    records: List[Dict[str, object]] = []

    for idx, lp_path in enumerate(lp_files, start=1):
        base_id = _sanitize_name(lp_path.stem)
        case_id = _dedup_case_id(base_id, seen_ids)

        case_output_dir = output_root / case_id
        case_config_path = generated_config_root / f"{case_id}.yaml"

        case_output_dir.mkdir(parents=True, exist_ok=True)

        record: Dict[str, object] = {
            "index": idx,
            "lp_file": _to_posix(lp_path),
            "case_id": case_id,
            "generated_config": _to_posix(case_config_path),
            "output_dir": _to_posix(case_output_dir),
            "imported_lp_path": _to_posix(case_output_dir / f"{case_id}.lp"),
            "scenario_inference_mode": args.scenario_inference,
            "scenario_inference_status": "disabled" if args.scenario_inference == "off" else "pending",
            "scenario_inference_error": "",
            "inferred_delay_count": 0,
            "inferred_speed_limit_count": 0,
            "inferred_interruption_count": 0,
            "speed_limit_groups": "",
            "status": "ok",
            "error": "",
        }

        try:
            scenarios = _build_empty_scenarios()
            if args.scenario_inference != "off":
                if inference_context is None:
                    record["scenario_inference_status"] = "skipped"
                    record["scenario_inference_error"] = inference_error
                    if args.scenario_inference == "require":
                        raise RuntimeError(inference_error or "Scenario inference context unavailable.")
                else:
                    scenarios, diagnostics = _infer_scenarios_from_lp(lp_path, inference_context)
                    record["scenario_inference_status"] = "ok"
                    record["inferred_delay_count"] = diagnostics["delay_count"]
                    record["inferred_speed_limit_count"] = diagnostics["speed_limit_count"]
                    record["inferred_interruption_count"] = diagnostics["interruption_count"]
                    record["speed_limit_groups"] = diagnostics["speed_limit_groups"]

            case_payload = _build_case_config(
                base_payload=base_payload,
                case_name=case_id,
                output_dir=case_output_dir,
                scenarios=scenarios,
                timetable_path_override=args.timetable_path,
                mileage_path_override=args.mileage_path,
                timetable_sheet_override=args.timetable_sheet_name,
                mileage_sheet_override=args.mileage_sheet_name,
            )
            with case_config_path.open("w", encoding="utf-8") as file:
                yaml.safe_dump(case_payload, file, allow_unicode=True, sort_keys=False)

            expected_lp_path = case_output_dir / f"{case_id}.lp"
            shutil.copy2(lp_path, expected_lp_path)

            if not expected_lp_path.exists():
                raise FileNotFoundError(f"Imported .lp missing: {expected_lp_path}")

        except Exception as exc:  # pragma: no cover
            record["status"] = "failed"
            record["error"] = str(exc)
            if args.scenario_inference != "off" and record["scenario_inference_status"] == "pending":
                record["scenario_inference_status"] = "failed"
                record["scenario_inference_error"] = str(exc)

        records.append(record)

    _write_csv(summary_csv, records)

    status_counts: Dict[str, int] = {}
    inference_status_counts: Dict[str, int] = {}
    for item in records:
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        inference_status = str(item.get("scenario_inference_status", "unknown"))
        inference_status_counts[inference_status] = inference_status_counts.get(inference_status, 0) + 1

    summary_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "lp_root": _to_posix(lp_root),
        "base_config": _to_posix(base_config_path),
        "generated_config_root": _to_posix(generated_config_root),
        "output_root": _to_posix(output_root),
        "scenario_inference_mode": args.scenario_inference,
        "timetable_path_override": _normalize_path_text(args.timetable_path) if args.timetable_path.strip() else "",
        "mileage_path_override": _normalize_path_text(args.mileage_path) if args.mileage_path.strip() else "",
        "timetable_sheet_name_override": args.timetable_sheet_name.strip(),
        "mileage_sheet_name_override": args.mileage_sheet_name.strip(),
        "total_lp": len(records),
        "status_counts": status_counts,
        "scenario_inference_status_counts": inference_status_counts,
        "summary_csv": _to_posix(summary_csv),
    }
    _write_json(summary_json, summary_payload)

    print(f"Imported LP files: {len(records)}")
    print(f"Status counts: {status_counts}")
    print(f"Scenario inference status counts: {inference_status_counts}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Summary JSON: {summary_json}")


if __name__ == "__main__":
    main()





