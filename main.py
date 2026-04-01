from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analysis.scenario_report import build_case_scenario_report_data
from core.builder import build_model
from core.exporter import export_lp
from core.loader import load_config, load_mileage_table, load_timetable
from core.postprocess import export_adjusted_timetable
from core.solver import load_solution_values, solve_lp
from core.translator import translate
from core.validator import validate_inputs


def _to_hms(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hour = seconds // 3600
    minute = (seconds % 3600) // 60
    return f"{hour:02d}:{minute:02d}"


def _scenario_config_to_payload(scenarios) -> dict:
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
                "start_time": f"{item.start_time // 3600:02d}:{(item.start_time % 3600) // 60:02d}:{item.start_time % 60:02d}",
                "end_time": f"{item.end_time // 3600:02d}:{(item.end_time % 3600) // 60:02d}:{item.end_time % 60:02d}",
            }
            for item in scenarios.speed_limits
        ],
        "interruptions": [
            {
                "start_station": item.start_station,
                "end_station": item.end_station,
                "start_time": f"{item.start_time // 3600:02d}:{(item.start_time % 3600) // 60:02d}:{item.start_time % 60:02d}",
                "end_time": f"{item.end_time // 3600:02d}:{(item.end_time % 3600) // 60:02d}:{item.end_time % 60:02d}",
            }
            for item in scenarios.interruptions
        ],
    }


def _build_scenario_note(config) -> str:
    parts = []

    for delay in config.scenarios.delays:
        parts.append(
            f"delay: train={delay.train_id}, station={delay.station}, event={delay.event_type}, +{delay.seconds}s"
        )

    for speed_limit in config.scenarios.speed_limits:
        parts.append(
            "speed_limit: "
            f"segment={speed_limit.start_station}->{speed_limit.end_station}, "
            f"+{speed_limit.extra_seconds}s, "
            f"window={_to_hms(speed_limit.start_time)}-{_to_hms(speed_limit.end_time)}"
        )

    for interruption in config.scenarios.interruptions:
        parts.append(
            "interruption: "
            f"segment={interruption.start_station}->{interruption.end_station}, "
            f"window={_to_hms(interruption.start_time)}-{_to_hms(interruption.end_time)}"
        )

    if not parts:
        return "Scenarios: none"

    max_items = 6
    shown = parts[:max_items]
    if len(parts) > max_items:
        shown.append(f"...(+{len(parts) - max_items} more)")

    return "Scenarios: " + " | ".join(shown)


def _load_translated(config_path: Path):
    config = load_config(config_path)
    timetable_bundle = load_timetable(
        config.input.timetable_path,
        config.input.timetable_sheet_name,
    )
    mileage_bundle = load_mileage_table(
        config.input.mileage_path,
        config.input.mileage_sheet_name,
    )
    validated = validate_inputs(config, timetable_bundle, mileage_bundle)
    translated = translate(validated, config)
    return config, translated


def cmd_build(config_path: Path) -> int:
    config, translated = _load_translated(config_path)
    model = build_model(translated, config)
    export_lp(model, config.build.lp_path)
    print(f"Model exported: {config.build.lp_path}")
    print(f"Trains: {len(translated.train_ids)}")
    print(f"Events: {len(translated.event_keys)}")
    print(f"Constraints: {len(model.constraints)}")
    return 0


def cmd_solve(config_path: Path) -> int:
    config = load_config(config_path)
    objective, _values = solve_lp(config.solve.lp_path, config.solve.solution_path)
    print(f"Objective: {objective:g}")
    print(f"Solution exported: {config.solve.solution_path}")
    return 0


def cmd_export_timetable(config_path: Path) -> int:
    config, translated = _load_translated(config_path)
    values = load_solution_values(config.export_timetable.solution_path)
    export_adjusted_timetable(translated, values, config.export_timetable.timetable_path)
    print(f"Adjusted timetable exported: {config.export_timetable.timetable_path}")
    return 0


def cmd_analyze(config_path: Path) -> int:
    config = load_config(config_path)
    if not config.analyze.enable_metrics and not config.analyze.enable_plot:
        print("Analysis skipped: both analyze.enable_metrics and analyze.enable_plot are false.")
        return 0

    if config.analyze.enable_metrics:
        from analysis.metrics import analyze_timetable

        metrics_path = analyze_timetable(
            config.analyze.plan_timetable_path,
            config.analyze.adjusted_timetable_path,
            config.analyze.metrics_output_path,
            plan_sheet_name=config.analyze.plan_timetable_sheet_name,
            adjusted_sheet_name=config.analyze.adjusted_timetable_sheet_name,
        )
        print(f"Metrics exported: {metrics_path}")

    if config.analyze.enable_plot:
        from analysis.plot import plot_timetable

        _config_for_plot, translated = _load_translated(config_path)
        scenario_overlay = build_case_scenario_report_data(
            case_id=config.project.name,
            scenarios=_scenario_config_to_payload(config.scenarios),
            config=config,
            translated=translated,
        )["scenario_rows"]

        plot_path = plot_timetable(
            config.analyze.plot_timetable_path,
            config.analyze.plot_output_path,
            show_grid=config.analyze.plot_grid,
            title=config.analyze.plot_title,
            subtitle=_build_scenario_note(config),
            sheet_name=config.analyze.adjusted_timetable_sheet_name,
            scenario_overlay=scenario_overlay,
            mileage_path=config.input.mileage_path,
            mileage_sheet_name=config.input.mileage_sheet_name,
        )
        print(f"Plot exported: {plot_path}")
    return 0


def cmd_run(config_path: Path) -> int:
    cmd_build(config_path)
    cmd_solve(config_path)
    cmd_export_timetable(config_path)
    cmd_analyze(config_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RailGraph2Gurobi command line.")
    parser.add_argument("--config", default="config/mixed_scenarios_demo.yaml", help="Path to YAML configuration file.")
    sub = parser.add_subparsers(dest="command")

    def _add_config_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", default=argparse.SUPPRESS, help="Path to YAML configuration file.")

    p_build = sub.add_parser("build", help="Build and export LP.")
    _add_config_arg(p_build)

    p_solve = sub.add_parser("solve", help="Solve LP and export .sol.")
    _add_config_arg(p_solve)

    p_export = sub.add_parser("export-timetable", help="Export adjusted timetable from .sol.")
    _add_config_arg(p_export)

    p_analyze = sub.add_parser("analyze", help="Run metrics and plotting analysis.")
    _add_config_arg(p_analyze)

    p_run = sub.add_parser("run", help="Run build, solve, export-timetable, analyze.")
    _add_config_arg(p_run)

    parser.set_defaults(command="run")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    config_value = getattr(args, "config", "config/mixed_scenarios_demo.yaml")
    config_path = Path(config_value)
    try:
        if args.command == "build":
            raise SystemExit(cmd_build(config_path))
        if args.command == "solve":
            raise SystemExit(cmd_solve(config_path))
        if args.command == "export-timetable":
            raise SystemExit(cmd_export_timetable(config_path))
        if args.command == "analyze":
            raise SystemExit(cmd_analyze(config_path))
        raise SystemExit(cmd_run(config_path))
    except Exception as exc:  # pragma: no cover
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

