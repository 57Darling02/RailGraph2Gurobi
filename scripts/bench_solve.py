from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.loader import load_config
from core.solver import solve_lp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run main solve stage for case configs produced by case_library_builder.py."
    )
    parser.add_argument("--config-root", default="tests/case_library")
    parser.add_argument("--glob", default="**/*.yaml")
    parser.add_argument("--start-index", type=int, default=1, help="1-based start index (inclusive).")
    parser.add_argument("--end-index", type=int, default=0, help="1-based end index (inclusive, 0 = no upper bound).")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--workers", type=int, default=1, help="Parallel solver processes (default: 1).")
    parser.add_argument("--threads-per-solve", type=int, default=0, help="Gurobi threads per solve (default: 0 = cpu_count // workers).")
    parser.add_argument("--time-limit", type=float, default=0.0, help="Gurobi time limit in seconds per solve (0 = no limit).")
    parser.add_argument("--mip-gap", type=float, default=0.0, help="Gurobi MIP relative gap threshold (0 = Gurobi default ~1e-4).")
    parser.add_argument("--summary-csv", default="outputs/bench_solve/summary.csv")
    parser.add_argument("--summary-json", default="outputs/bench_solve/summary.json")
    return parser.parse_args()


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _to_posix(path_value: Path) -> str:
    return str(path_value).replace("\\", "/")


def _collect_configs(config_root: Path, pattern: str, start_index: int, end_index: int) -> List[Path]:
    if not config_root.exists():
        raise FileNotFoundError(f"config root not found: {config_root}")
    if start_index < 1:
        raise ValueError("start-index must be >= 1")
    if end_index > 0 and end_index < start_index:
        raise ValueError("end-index must be >= start-index")

    all_configs = sorted(path for path in config_root.glob(pattern) if path.is_file())
    end_pos = end_index if end_index > 0 else None
    return all_configs[start_index - 1 : end_pos]


def _write_csv(path: Path, records: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(records[0].keys()) if records else ["index", "config_file", "status", "error"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _solve_one_case(
    idx: int,
    config_path: Path,
    threads_per_solve: int,
    time_limit: float,
    mip_gap: float,
) -> Dict[str, object]:
    """Top-level function so it can be pickled by ProcessPoolExecutor."""
    start = time.perf_counter()
    record: Dict[str, object] = {
        "index": idx,
        "config_file": _to_posix(config_path),
        "case_id": config_path.stem,
        "status": "ok",
        "error": "",
        "lp_path": "",
        "lp_exists": False,
        "sol_path": "",
        "sol_exists": False,
        "objective": None,
        "mip_gap": None,
        "duration_sec": 0.0,
    }
    try:
        loaded = load_config(config_path)
        record["lp_path"] = _to_posix(loaded.solve.lp_path)
        record["lp_exists"] = loaded.solve.lp_path.exists()
        record["sol_path"] = _to_posix(loaded.solve.solution_path)

        if not loaded.solve.lp_path.exists():
            raise FileNotFoundError(f"LP file not found: {loaded.solve.lp_path}")

        result = solve_lp(
            loaded.solve.lp_path,
            loaded.solve.solution_path,
            quiet=True,
            threads=threads_per_solve,
            time_limit=time_limit,
            mip_gap=mip_gap,
        )
        record["objective"] = round(result.objective, 4)
        record["mip_gap"] = round(result.mip_gap, 6)
        if result.timed_out:
            record["status"] = "timeout"

        record["sol_exists"] = loaded.solve.solution_path.exists()
        if not loaded.solve.solution_path.exists():
            raise FileNotFoundError(f"Solution file not found after solve: {loaded.solve.solution_path}")
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)

    record["duration_sec"] = round(time.perf_counter() - start, 3)
    return record


def _print_record(record: Dict[str, object], completed: int, total: int) -> None:
    obj_str = f"obj={record['objective']}" if record["objective"] is not None else "obj=N/A"
    gap = record.get("mip_gap")
    gap_str = f" gap={gap:.2%}" if gap is not None else ""
    sol_str = " sol=yes" if record.get("sol_exists") else " sol=no"
    print(f"[{completed}/{total}] {record['status']} | {record['case_id']} | {obj_str}{gap_str}{sol_str} | {record['duration_sec']}s")
    if record["status"] == "failed":
        print(f"  ! {record['error']}", file=sys.stderr)


def main() -> None:
    args = parse_args()
    config_root = _resolve_path(args.config_root)
    summary_csv = _resolve_path(args.summary_csv)
    summary_json = _resolve_path(args.summary_json)

    configs = _collect_configs(config_root, args.glob, args.start_index, args.end_index)

    workers = max(1, args.workers)
    cpu_count = multiprocessing.cpu_count()
    threads_per_solve = args.threads_per_solve if args.threads_per_solve > 0 else max(1, cpu_count // workers)
    time_limit: float = args.time_limit
    mip_gap: float = args.mip_gap

    range_str = f"start={args.start_index} end={args.end_index or 'all'}"
    limit_str = f"  time-limit={time_limit}s" if time_limit > 0 else ""
    gap_str = f"  mip-gap={mip_gap:.2%}" if mip_gap > 0 else ""
    print(f"Found configs: {len(configs)} ({range_str})")
    print(f"Workers: {workers}  threads-per-solve: {threads_per_solve}  CPUs: {cpu_count}{limit_str}{gap_str}")

    records: List[Dict[str, object]] = []
    total = len(configs)

    if workers == 1:
        for offset, config_path in enumerate(configs):
            record = _solve_one_case(args.start_index + offset, config_path, threads_per_solve, time_limit, mip_gap)
            records.append(record)
            _print_record(record, offset + 1, total)
            if record["status"] == "failed" and args.stop_on_error:
                break
    else:
        completed = 0
        stop = False
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_idx = {
                executor.submit(_solve_one_case, args.start_index + offset, config_path, threads_per_solve, time_limit, mip_gap): offset
                for offset, config_path in enumerate(configs)
            }
            for future in as_completed(future_to_idx):
                if stop:
                    future.cancel()
                    continue
                completed += 1
                record = future.result()
                records.append(record)
                _print_record(record, completed, total)
                if record["status"] == "failed" and args.stop_on_error:
                    stop = True

    records.sort(key=lambda r: int(r["index"]))

    status_counts: Dict[str, int] = {}
    for item in records:
        s = str(item.get("status", "unknown"))
        status_counts[s] = status_counts.get(s, 0) + 1

    ok_objectives = [float(r["objective"]) for r in records if r.get("objective") is not None and r.get("status") != "failed"]
    obj_stats = ""
    if ok_objectives:
        obj_stats = f" | obj min={min(ok_objectives):.4g} avg={sum(ok_objectives)/len(ok_objectives):.4g} max={max(ok_objectives):.4g}"

    _write_csv(summary_csv, records)
    _write_json(summary_json, {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config_root": _to_posix(config_root),
        "glob": args.glob,
        "start_index": args.start_index,
        "end_index": args.end_index,
        "total": len(records),
        "status_counts": status_counts,
        "summary_csv": _to_posix(summary_csv),
    })

    print(f"\nDone: {' '.join(f'{k}={v}' for k, v in status_counts.items())}{obj_stats}")

    failed_records = [r for r in records if str(r.get("status")) == "failed"]
    if failed_records:
        print("Failed cases:", file=sys.stderr)
        for r in failed_records:
            print(f"  - {r.get('case_id', '')}: {r.get('error', '')}", file=sys.stderr)

    print(f"Summary → {summary_csv}")


if __name__ == "__main__":
    main()
