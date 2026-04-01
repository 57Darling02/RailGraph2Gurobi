from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure project imports work when running as:
#   python scripts/bench_analyze.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.scenario_report import (
    build_case_scenario_report_data,
    generate_batch_scenario_report,
    generate_case_scenario_report,
)
from core.loader import load_config, load_mileage_table, load_timetable
from core.translator import translate
from core.types import AppConfig, ScenarioConfig, TranslatedData
from core.validator import validate_inputs
from main import cmd_analyze


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run analyze stage and scenario statistics for case configs."
    )
    parser.add_argument(
        "--config-root",
        default="tests/case_library",
        help="Root directory containing case config files.",
    )
    parser.add_argument(
        "--glob",
        default="**/*.yaml",
        help="Glob pattern under config-root to find config files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process first N configs (0 = all).",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when one config fails.",
    )
    parser.add_argument(
        "--summary-csv",
        default="outputs/bench_analyze/summary.csv",
        help="Summary CSV output path.",
    )
    parser.add_argument(
        "--summary-json",
        default="outputs/bench_analyze/summary.json",
        help="Summary JSON output path.",
    )
    parser.add_argument(
        "--scenario-report",
        choices=("on", "off"),
        default="on",
        help="Generate scenario statistics from config.build.scenarios during batch analyze.",
    )
    parser.add_argument(
        "--scenario-report-scope",
        choices=("batch", "per_case", "both"),
        default="batch",
        help="Generate batch-only scenario analytics, per-case analytics, or both.",
    )
    parser.add_argument(
        "--scenario-report-output-root",
        default="",
        help="Root directory for scenario analytics outputs. Defaults to the summary-json directory.",
    )
    return parser.parse_args()


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _to_posix(path_value: Path) -> str:
    return str(path_value).replace("\\", "/")


def _collect_configs(config_root: Path, pattern: str, limit: int) -> List[Path]:
    if not config_root.exists():
        raise FileNotFoundError(f"config root not found: {config_root}")
    configs = sorted(path for path in config_root.glob(pattern) if path.is_file())
    if limit > 0:
        configs = configs[:limit]
    return configs


def _write_csv(path: Path, records: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        headers = ["index", "config_file", "status", "error"]
    else:
        headers = list(records[0].keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _seconds_to_hms(seconds: int) -> str:
    total = max(0, min(86399, int(seconds)))
    hour = total // 3600
    minute = (total % 3600) // 60
    second = total % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _scenario_config_to_payload(scenarios: ScenarioConfig) -> Dict[str, object]:
    return {
        "delays": [
            {
                "train_id": item.train_id,
                "station": item.station,
                "event_type": item.event_type,
                "seconds": item.seconds,
            }
            for item in scenarios.delays
        ],
        "speed_limits": [
            {
                "start_station": item.start_station,
                "end_station": item.end_station,
                "extra_seconds": item.extra_seconds,
                "start_time": _seconds_to_hms(item.start_time),
                "end_time": _seconds_to_hms(item.end_time),
            }
            for item in scenarios.speed_limits
        ],
        "interruptions": [
            {
                "start_station": item.start_station,
                "end_station": item.end_station,
                "start_time": _seconds_to_hms(item.start_time),
                "end_time": _seconds_to_hms(item.end_time),
            }
            for item in scenarios.interruptions
        ],
    }


def _build_translated_context(config: AppConfig) -> TranslatedData:
    timetable_table = load_timetable(config.input.timetable_path, sheet_name=config.input.timetable_sheet_name)
    mileage_table = load_mileage_table(config.input.mileage_path, sheet_name=config.input.mileage_sheet_name)
    validated = validate_inputs(config, timetable_table, mileage_table)
    return translate(validated, config)


def _finalize_status(analyze_status: str, scenario_status: str) -> Tuple[str, str]:
    enabled_statuses = [status for status in (analyze_status, scenario_status) if status != "disabled"]
    if not enabled_statuses:
        return "skipped", ""
    if any(status == "failed" for status in enabled_statuses):
        if any(status in {"ok", "batched", "skipped"} for status in enabled_statuses):
            return "partial", ""
        return "failed", ""
    if all(status == "skipped" for status in enabled_statuses):
        return "skipped", ""
    return "ok", ""


def main() -> None:
    args = parse_args()
    config_root = _resolve_path(args.config_root)
    summary_csv = _resolve_path(args.summary_csv)
    summary_json = _resolve_path(args.summary_json)
    scenario_report_output_root = _resolve_path(args.scenario_report_output_root) if args.scenario_report_output_root else summary_json.parent

    configs = _collect_configs(config_root, args.glob, args.limit)
    print(f"Found configs: {len(configs)}")

    records: List[Dict[str, object]] = []
    case_report_items: List[Dict[str, object]] = []
    scenario_report_config: AppConfig | None = None

    for idx, config_path in enumerate(configs, start=1):
        time.sleep(0.2)
        start = time.perf_counter()
        record: Dict[str, object] = {
            "index": idx,
            "config_file": _to_posix(config_path),
            "case_id": config_path.stem,
            "status": "ok",
            "error": "",
            "note": "",
            "output_dir": "",
            "enable_metrics": False,
            "enable_plot": False,
            "adjusted_timetable_path": "",
            "adjusted_timetable_exists": False,
            "metrics_path": "",
            "metrics_exists": False,
            "plot_path": "",
            "plot_exists": False,
            "analyze_status": "pending",
            "analyze_error": "",
            "scenario_report_scope": args.scenario_report_scope if args.scenario_report == "on" else "off",
            "scenario_report_status": "disabled" if args.scenario_report == "off" else "pending",
            "scenario_report_error": "",
            "scenario_report_dir": "",
            "scenario_report_json": "",
            "scenario_report_excel": "",
            "scenario_report_timetable_plot": "",
            "scenario_report_type_plot": "",
            "scenario_report_location_plot": "",
            "scenario_report_coverage_plot": "",
            "scenario_report_case_plot": "",
            "duration_sec": 0.0,
        }

        try:
            loaded = load_config(config_path)
            case_id = loaded.project.name or config_path.stem
            record["case_id"] = case_id
            record["output_dir"] = _to_posix(loaded.project.output_dir)
            record["enable_metrics"] = loaded.analyze.enable_metrics
            record["enable_plot"] = loaded.analyze.enable_plot
            record["adjusted_timetable_path"] = _to_posix(loaded.analyze.adjusted_timetable_path)
            record["adjusted_timetable_exists"] = loaded.analyze.adjusted_timetable_path.exists()
            record["metrics_path"] = _to_posix(loaded.analyze.metrics_output_path)
            record["plot_path"] = _to_posix(loaded.analyze.plot_output_path)

            analyze_requested = loaded.analyze.enable_metrics or loaded.analyze.enable_plot
            if not analyze_requested:
                record["analyze_status"] = "disabled"
            elif not loaded.analyze.adjusted_timetable_path.exists():
                record["analyze_status"] = "skipped"
                record["analyze_error"] = (
                    f"Adjusted timetable not found for analyze: {loaded.analyze.adjusted_timetable_path}. "
                    "Skipped metrics/plot stage."
                )
            else:
                code = cmd_analyze(config_path)
                if code != 0:
                    raise RuntimeError(f"cmd_analyze returned non-zero code: {code}")

                if loaded.analyze.enable_metrics:
                    record["metrics_exists"] = loaded.analyze.metrics_output_path.exists()
                    if not loaded.analyze.metrics_output_path.exists():
                        raise FileNotFoundError(
                            f"Metrics file not found after analyze: {loaded.analyze.metrics_output_path}"
                        )

                if loaded.analyze.enable_plot:
                    record["plot_exists"] = loaded.analyze.plot_output_path.exists()
                    if not loaded.analyze.plot_output_path.exists():
                        raise FileNotFoundError(
                            f"Plot file not found after analyze: {loaded.analyze.plot_output_path}"
                        )
                record["analyze_status"] = "ok"

            if args.scenario_report == "on":
                try:
                    translated = _build_translated_context(loaded)
                    scenario_payload = _scenario_config_to_payload(loaded.scenarios)
                    if scenario_report_config is None:
                        scenario_report_config = loaded
                    report_item = build_case_scenario_report_data(
                        case_id=case_id,
                        scenarios=scenario_payload,
                        config=loaded,
                        translated=translated,
                    )
                    case_report_items.append(report_item)
                    if args.scenario_report_scope in ("per_case", "both"):
                        case_report = generate_case_scenario_report(
                            case_id=case_id,
                            scenarios=scenario_payload,
                            config=loaded,
                            translated=translated,
                            output_dir=loaded.project.output_dir,
                        )
                        record["scenario_report_status"] = "ok"
                        record["scenario_report_dir"] = str(case_report["report_dir"])
                        record["scenario_report_json"] = str(case_report["summary_json"])
                        record["scenario_report_excel"] = str(case_report["summary_excel"])
                        record["scenario_report_timetable_plot"] = str(case_report["timetable_plot"])
                        record["scenario_report_type_plot"] = str(case_report["type_plot"])
                        record["scenario_report_location_plot"] = str(case_report["location_plot"])
                        record["scenario_report_coverage_plot"] = str(case_report["coverage_plot"])
                        record["scenario_report_case_plot"] = str(case_report["case_plot"])
                    else:
                        record["scenario_report_status"] = "batched"
                except Exception as report_exc:
                    record["scenario_report_status"] = "failed"
                    record["scenario_report_error"] = str(report_exc)

            record["status"], _ = _finalize_status(
                str(record["analyze_status"]),
                str(record["scenario_report_status"]),
            )
            error_parts = []
            note_parts = []
            if str(record["analyze_status"]) == "failed" and str(record["analyze_error"]).strip():
                error_parts.append(str(record["analyze_error"]).strip())
            elif str(record["analyze_status"]) == "skipped" and str(record["analyze_error"]).strip():
                note_parts.append(str(record["analyze_error"]).strip())
            if str(record["scenario_report_status"]) == "failed" and str(record["scenario_report_error"]).strip():
                error_parts.append(str(record["scenario_report_error"]).strip())
            record["error"] = " | ".join(error_parts)
            record["note"] = " | ".join(note_parts)
        except Exception as exc:  # pragma: no cover
            record["status"] = "failed"
            record["error"] = str(exc)
            if record["analyze_status"] == "pending":
                record["analyze_status"] = "failed"
                record["analyze_error"] = str(exc)
            if args.scenario_report == "on" and record["scenario_report_status"] == "pending":
                record["scenario_report_status"] = "failed"
                record["scenario_report_error"] = str(exc)

        record["duration_sec"] = round(time.perf_counter() - start, 3)
        records.append(record)

        print(
            f"[{idx}/{len(configs)}] {record['status']} | "
            f"{record['case_id']} | {record['duration_sec']}s"
        )
        if record["status"] in {"failed", "partial"} and record["error"]:
            print(f"    reason: {record['error']}", file=sys.stderr)

        if record["status"] == "failed" and args.stop_on_error:
            break

    batch_report: Dict[str, object] = {}
    batch_report_error = ""
    if args.scenario_report == "on" and case_report_items and scenario_report_config is not None:
        try:
            batch_report = generate_batch_scenario_report(case_report_items, scenario_report_output_root, scenario_report_config)
        except Exception as exc:
            batch_report_error = str(exc)

    status_counts: Dict[str, int] = {}
    analyze_status_counts: Dict[str, int] = {}
    report_status_counts: Dict[str, int] = {}
    for item in records:
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        analyze_status = str(item.get("analyze_status", "unknown"))
        analyze_status_counts[analyze_status] = analyze_status_counts.get(analyze_status, 0) + 1
        report_status = str(item.get("scenario_report_status", "unknown"))
        report_status_counts[report_status] = report_status_counts.get(report_status, 0) + 1

    payload: Dict[str, object] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config_root": _to_posix(config_root),
        "glob": args.glob,
        "limit": args.limit,
        "total": len(records),
        "status_counts": status_counts,
        "analyze_status_counts": analyze_status_counts,
        "scenario_report_scope": args.scenario_report_scope if args.scenario_report == "on" else "off",
        "scenario_report_status_counts": report_status_counts,
        "scenario_report_output_root": _to_posix(scenario_report_output_root),
        "scenario_batch_report": batch_report,
        "scenario_batch_report_error": batch_report_error,
        "summary_csv": _to_posix(summary_csv),
    }

    _write_csv(summary_csv, records)
    _write_json(summary_json, payload)

    print(f"Status counts: {status_counts}")
    print(f"Analyze status counts: {analyze_status_counts}")
    print(f"Scenario report status counts: {report_status_counts}")
    if batch_report:
        print(f"Scenario batch report: {batch_report.get('report_dir', '')}")
    if batch_report_error:
        print(f"Scenario batch report error: {batch_report_error}")

    failed_records = [item for item in records if str(item.get("status")) == "failed"]
    if failed_records:
        print("Failed cases:", file=sys.stderr)
        for item in failed_records:
            print(
                f"- {item.get('case_id', '')}: {item.get('error', '')}",
                file=sys.stderr,
            )

    print(f"Summary CSV: {summary_csv}")
    print(f"Summary JSON: {summary_json}")


if __name__ == "__main__":
    main()
