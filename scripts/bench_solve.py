from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Ensure project imports work when running as:
#   python scripts/bench_solve.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.loader import load_config
from main import cmd_solve


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run main solve stage for case configs produced by case_library_builder.py."
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
        "--start-index",
        type=int,
        default=1,
        help="1-based start index in the sorted config list (inclusive).",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        default=0,
        help="1-based end index in the sorted config list (inclusive, 0 = no upper bound).",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when one config fails.",
    )
    parser.add_argument(
        "--summary-csv",
        default="outputs/bench_solve/summary.csv",
        help="Summary CSV output path.",
    )
    parser.add_argument(
        "--summary-json",
        default="outputs/bench_solve/summary.json",
        help="Summary JSON output path.",
    )
    return parser.parse_args()


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _to_posix(path_value: Path) -> str:
    return str(path_value).replace("\\", "/")


def _collect_configs(
    config_root: Path,
    pattern: str,
    start_index: int,
    end_index: int,
    limit: int,
) -> List[Path]:
    if not config_root.exists():
        raise FileNotFoundError(f"config root not found: {config_root}")

    if start_index < 1:
        raise ValueError("start-index must be >= 1")
    if end_index < 0:
        raise ValueError("end-index must be >= 0")
    if end_index > 0 and end_index < start_index:
        raise ValueError("end-index must be >= start-index when end-index > 0")

    all_configs = sorted(path for path in config_root.glob(pattern) if path.is_file())

    start_pos = start_index - 1
    end_pos = end_index if end_index > 0 else None
    configs = all_configs[start_pos:end_pos]

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


def main() -> None:
    args = parse_args()
    config_root = _resolve_path(args.config_root)
    summary_csv = _resolve_path(args.summary_csv)
    summary_json = _resolve_path(args.summary_json)

    configs = _collect_configs(
        config_root=config_root,
        pattern=args.glob,
        start_index=args.start_index,
        end_index=args.end_index,
        limit=args.limit,
    )
    print(
        "Found configs: "
        f"{len(configs)} "
        f"(start-index={args.start_index}, end-index={args.end_index or 'all'}, limit={args.limit})"
    )

    records: List[Dict[str, object]] = []

    for offset, config_path in enumerate(configs, start=0):
        idx = args.start_index + offset
        time.sleep(0.2)
        start = time.perf_counter()
        record: Dict[str, object] = {
            "index": idx,
            "config_file": _to_posix(config_path),
            "case_id": config_path.parent.name,
            "status": "ok",
            "error": "",
            "output_dir": "",
            "lp_path": "",
            "lp_exists": False,
            "sol_path": "",
            "sol_exists": False,
            "duration_sec": 0.0,
        }

        try:
            loaded = load_config(config_path)
            record["output_dir"] = _to_posix(loaded.project.output_dir)
            record["lp_path"] = _to_posix(loaded.solve.lp_path)
            record["lp_exists"] = loaded.solve.lp_path.exists()
            record["sol_path"] = _to_posix(loaded.solve.solution_path)

            if not loaded.solve.lp_path.exists():
                raise FileNotFoundError(f"LP file not found for solve: {loaded.solve.lp_path}")

            code = cmd_solve(config_path)
            if code != 0:
                raise RuntimeError(f"cmd_solve returned non-zero code: {code}")

            record["sol_exists"] = loaded.solve.solution_path.exists()
            if not loaded.solve.solution_path.exists():
                raise FileNotFoundError(
                    f"Solution file not found after solve: {loaded.solve.solution_path}"
                )
        except Exception as exc:  # pragma: no cover
            record["status"] = "failed"
            record["error"] = str(exc)

        record["duration_sec"] = round(time.perf_counter() - start, 3)
        records.append(record)

        print(
            f"[{offset + 1}/{len(configs)}|global#{idx}] "
            f"{record['status']} | {record['case_id']} | {record['duration_sec']}s"
        )
        if record["status"] == "failed":
            print(f"    reason: {record['error']}", file=sys.stderr)

        if record["status"] == "failed" and args.stop_on_error:
            break

    status_counts: Dict[str, int] = {}
    for item in records:
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    payload: Dict[str, object] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config_root": _to_posix(config_root),
        "glob": args.glob,
        "limit": args.limit,
        "start_index": args.start_index,
        "end_index": args.end_index,
        "total": len(records),
        "status_counts": status_counts,
        "summary_csv": _to_posix(summary_csv),
    }

    _write_csv(summary_csv, records)
    _write_json(summary_json, payload)

    print(f"Status counts: {status_counts}")

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
