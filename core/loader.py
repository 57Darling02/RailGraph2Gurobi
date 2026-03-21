from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.types import (
    AnalyzeConfig,
    AppConfig,
    BuildConfig,
    DelayScenario,
    ExportTimetableConfig,
    InputConfig,
    InterruptionScenario,
    ProjectConfig,
    RawTable,
    ScenarioConfig,
    SolveConfig,
    SolverConfig,
    SpeedLimitScenario,
)

TIME_HEADERS = {"arrival_time", "departure_time"}


def _require_yaml() -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: pyyaml") from exc
    return yaml


def _normalize_header(header: str) -> str:
    return header.lower()


def _normalize_time_text(value: str) -> str:
    parts = value.split(":")
    if len(parts) != 3 or any(part == "" for part in parts):
        return value
    try:
        hour, minute, second = [int(part) for part in parts]
    except ValueError:
        return value
    if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
        return value
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _normalize_cell_value(cell: Any, header: str) -> Optional[str]:
    if cell is None:
        return None
    if isinstance(cell, datetime):
        cell = cell.time()
    if isinstance(cell, time):
        return cell.strftime("%H:%M:%S")
    text = str(cell).strip()
    if text == "":
        return None
    if header in TIME_HEADERS:
        return _normalize_time_text(text)
    return text


def _read_excel(path: Path, sheet_name: str) -> RawTable:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: openpyxl") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found in {path}")
    worksheet = workbook[sheet_name]
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError(f"Empty sheet: {path}#{sheet_name}")

    raw_headers = [_normalize_header(str(cell).strip()) if cell is not None else "" for cell in rows[0]]
    headers: List[str] = []
    header_indexes: List[int] = []
    for index, header in enumerate(raw_headers):
        if header == "":
            continue
        if header in headers:
            raise ValueError(f"Duplicated header in {path}#{sheet_name}: {header}")
        headers.append(header)
        header_indexes.append(index)

    records: List[Dict[str, Optional[str]]] = []
    for row in rows[1:]:
        if all(cell is None for cell in row):
            continue
        record: Dict[str, Optional[str]] = {}
        for header, index in zip(headers, header_indexes):
            cell = row[index] if index < len(row) else None
            record[header] = _normalize_cell_value(cell, header)
        records.append(record)
    return RawTable(headers=headers, rows=records)


def _parse_time_to_seconds(value: Any) -> int:
    # YAML may parse unquoted "HH:MM:SS" into a numeric scalar (e.g. 08:00:00 -> 28800).
    # Support both explicit "HH:MM:SS" strings and numeric seconds.
    if isinstance(value, (int, float)):
        seconds = int(value)
        if seconds < 0 or seconds > 24 * 3600 - 1:
            raise ValueError(f"Invalid HH:MM:SS time: {value}")
        return seconds

    text = str(value).strip()
    if text.isdigit():
        seconds = int(text)
        if seconds < 0 or seconds > 24 * 3600 - 1:
            raise ValueError(f"Invalid HH:MM:SS time: {value}")
        return seconds

    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid HH:MM:SS time: {value}")
    hour, minute, second = [int(part) for part in parts]
    if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
        raise ValueError(f"Invalid HH:MM:SS time: {value}")
    return hour * 3600 + minute * 60 + second


def load_config(path: Path) -> AppConfig:
    yaml = _require_yaml()
    with path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}

    input_cfg = payload.get("input", {})
    solver_cfg = payload.get("solver", {})
    scenarios_cfg = payload.get("scenarios", {})
    project_cfg = payload.get("project", {})
    analyze_cfg = payload.get("analyze", payload.get("analysis", {}))

    case_name = str(project_cfg.get("name", path.stem)).strip() or path.stem
    output_dir = Path(str(project_cfg.get("output_dir", Path("outputs") / case_name)))

    # Fixed pipeline artifact paths under project.output_dir.
    # The config no longer needs to specify per-stage IO paths.
    lp_path = output_dir / "model.lp"
    solution_path = output_dir / "solution.sol"
    adjusted_timetable_path = output_dir / "adjusted_timetable.xlsx"
    metrics_output_path = output_dir / "analysis_metrics.xlsx"
    plot_output_path = output_dir / "timetable_plot.png"

    delays = [
        DelayScenario(
            train_id=str(item["train_id"]).strip(),
            station=str(item["station"]).strip(),
            event_type=str(item["event_type"]).strip(),
            seconds=int(item["seconds"]),
        )
        for item in scenarios_cfg.get("delays", [])
    ]
    speed_limits = [
        SpeedLimitScenario(
            start_station=str(item["start_station"]).strip(),
            end_station=str(item["end_station"]).strip(),
            extra_seconds=int(item["extra_seconds"]),
            start_time=_parse_time_to_seconds(item["start_time"]),
            end_time=_parse_time_to_seconds(item["end_time"]),
        )
        for item in scenarios_cfg.get("speed_limits", [])
    ]
    interruptions = [
        InterruptionScenario(
            start_station=str(item["start_station"]).strip(),
            end_station=str(item["end_station"]).strip(),
            start_time=_parse_time_to_seconds(item["start_time"]),
            end_time=_parse_time_to_seconds(item["end_time"]),
        )
        for item in scenarios_cfg.get("interruptions", [])
    ]

    return AppConfig(
        project=ProjectConfig(name=case_name, output_dir=output_dir),
        input=InputConfig(
            timetable_path=Path(str(input_cfg.get("timetable_path", ""))),
            mileage_path=Path(str(input_cfg.get("mileage_path", ""))),
            timetable_sheet_name=str(input_cfg.get("timetable_sheet_name", "Sheet1")),
            mileage_sheet_name=str(input_cfg.get("mileage_sheet_name", "Sheet1")),
        ),
        solver=SolverConfig(
            objective_delay_weight=float(solver_cfg.get("objective_delay_weight", 1.0)),
            objective_mode=str(solver_cfg.get("objective_mode", "abs")),
            arr_arr_headway_seconds=int(solver_cfg.get("arr_arr_headway_seconds", 180)),
            dep_dep_headway_seconds=int(solver_cfg.get("dep_dep_headway_seconds", 180)),
            dwell_seconds_at_stops=int(solver_cfg.get("dwell_seconds_at_stops", 120)),
            big_m=int(solver_cfg.get("big_m", 100000)),
            tolerance_delay_seconds=int(solver_cfg.get("tolerance_delay_seconds", 2 * 3600)),
        ),
        scenarios=ScenarioConfig(
            delays=delays,
            speed_limits=speed_limits,
            interruptions=interruptions,
        ),
        build=BuildConfig(lp_path=lp_path),
        solve=SolveConfig(lp_path=lp_path, solution_path=solution_path),
        export_timetable=ExportTimetableConfig(
            solution_path=solution_path,
            timetable_path=adjusted_timetable_path,
        ),
        analyze=AnalyzeConfig(
            enable_metrics=bool(analyze_cfg.get("enable_metrics", False)),
            enable_plot=bool(analyze_cfg.get("enable_plot", False)),
            plot_grid=bool(analyze_cfg.get("plot_grid", False)),
            plot_title=str(analyze_cfg.get("plot_title", "Train Timetable")),
            plan_timetable_path=Path(str(input_cfg.get("timetable_path", ""))),
            adjusted_timetable_path=adjusted_timetable_path,
            metrics_output_path=metrics_output_path,
            plot_output_path=plot_output_path,
            plot_timetable_path=adjusted_timetable_path,
        ),
    )


def load_timetable(path: Path, sheet_name: str) -> RawTable:
    return _read_excel(path, sheet_name)


def load_mileage_table(path: Path, sheet_name: str) -> RawTable:
    return _read_excel(path, sheet_name)
