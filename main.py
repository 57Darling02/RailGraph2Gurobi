from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.builder import build_model
from core.exporter import export_lp
from core.loader import load_config, load_mileage_table, load_timetable
from core.postprocess import export_adjusted_timetable
from core.solver import load_solution_values, solve_lp
from core.translator import translate
from core.validator import validate_inputs


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
        )
        print(f"Metrics exported: {metrics_path}")

    if config.analyze.enable_plot:
        from analysis.plot import plot_timetable

        plot_path = plot_timetable(
            config.analyze.plot_timetable_path,
            config.analyze.plot_output_path,
            show_grid=config.analyze.plot_grid,
            title=config.analyze.plot_title,
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
    parser.add_argument("--config", default="config/demo.yaml", help="Path to YAML configuration file.")
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
    config_value = getattr(args, "config", "config/demo.yaml")
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
