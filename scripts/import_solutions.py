from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Ensure project imports work when running as:
#   python scripts/import_solutions.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _require_yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: pyyaml") from exc
    return yaml


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import external .sol files into standardized case yaml + output layout."
    )
    parser.add_argument("--solutions-root", default="tests/solutions", help="Root folder containing *.sol files.")
    parser.add_argument("--base-config", default="config/base_demo.yaml", help="Template config used as base.")
    parser.add_argument("--generated-config-root", default="tests/generated_configs", help="Generated yaml root.")
    parser.add_argument("--output-root", default="outputs/solutions_import", help="Per-case output root.")
    parser.add_argument("--summary-csv", default="outputs/solutions_import/import_summary.csv", help="Import summary CSV.")
    parser.add_argument("--summary-json", default="outputs/solutions_import/import_summary.json", help="Import summary JSON.")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N sol files (0 = all).")
    parser.add_argument("--clean", action="store_true", help="Clean generated config/output roots before importing.")
    return parser.parse_args()


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _to_posix(path_value: Path) -> str:
    return str(path_value).replace("\\", "/")


def _sanitize_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-") or "case"


def _dedup_case_id(base_id: str, seen: Dict[str, int]) -> str:
    count = seen.get(base_id, 0) + 1
    seen[base_id] = count
    if count == 1:
        return base_id
    return f"{base_id}_{count}"


def _build_case_config(
    base_payload: Dict[str, object],
    case_name: str,
    output_dir: Path,
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

    project["name"] = case_name
    project["output_dir"] = _to_posix(output_dir)
    payload["project"] = project

    build = dict(payload.get("build", {}))
    build["scenarios"] = {
        "delays": [],
        "speed_limits": [],
        "interruptions": [],
    }
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
    headers = list(records[0].keys()) if records else ["index", "solution_file", "status", "error"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def main() -> None:
    args = _parse_args()
    yaml = _require_yaml()

    solutions_root = _resolve_path(args.solutions_root)
    base_config_path = _resolve_path(args.base_config)
    generated_config_root = _resolve_path(args.generated_config_root)
    output_root = _resolve_path(args.output_root)
    summary_csv = _resolve_path(args.summary_csv)
    summary_json = _resolve_path(args.summary_json)

    if not solutions_root.exists():
        raise FileNotFoundError(f"solutions root not found: {solutions_root}")
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

    sol_files = sorted(solutions_root.rglob("*.sol"))
    if args.limit > 0:
        sol_files = sol_files[: args.limit]

    seen_ids: Dict[str, int] = {}
    records: List[Dict[str, object]] = []

    for idx, sol_path in enumerate(sol_files, start=1):
        base_id = _sanitize_name(sol_path.stem)
        case_id = _dedup_case_id(base_id, seen_ids)

        case_output_dir = output_root / case_id
        case_config_path = generated_config_root / f"{case_id}.yaml"

        case_output_dir.mkdir(parents=True, exist_ok=True)

        record: Dict[str, object] = {
            "index": idx,
            "solution_file": _to_posix(sol_path),
            "case_id": case_id,
            "generated_config": _to_posix(case_config_path),
            "output_dir": _to_posix(case_output_dir),
            "imported_sol_path": _to_posix(case_output_dir / f"{case_id}.sol"),
            "status": "ok",
            "error": "",
        }

        try:
            case_payload = _build_case_config(
                base_payload=base_payload,
                case_name=case_id,
                output_dir=case_output_dir,
            )
            with case_config_path.open("w", encoding="utf-8") as file:
                yaml.safe_dump(case_payload, file, allow_unicode=True, sort_keys=False)

            expected_solution_path = case_output_dir / f"{case_id}.sol"
            shutil.copy2(sol_path, expected_solution_path)

            if not expected_solution_path.exists():
                raise FileNotFoundError(f"Imported .sol missing: {expected_solution_path}")
        except Exception as exc:  # pragma: no cover
            record["status"] = "failed"
            record["error"] = str(exc)

        records.append(record)

    _write_csv(summary_csv, records)

    status_counts: Dict[str, int] = {}
    for item in records:
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    summary_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "solutions_root": _to_posix(solutions_root),
        "base_config": _to_posix(base_config_path),
        "generated_config_root": _to_posix(generated_config_root),
        "output_root": _to_posix(output_root),
        "total_solutions": len(records),
        "status_counts": status_counts,
        "summary_csv": _to_posix(summary_csv),
    }
    _write_json(summary_json, summary_payload)

    print(f"Imported solutions: {len(records)}")
    print(f"Status counts: {status_counts}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Summary JSON: {summary_json}")


if __name__ == "__main__":
    main()

