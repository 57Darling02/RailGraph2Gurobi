from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path
from typing import Any, Dict

import _case_generation_core as gen


def _require_yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: pyyaml (required by case builder).") from exc
    return yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build case library yaml files only, reusing generation core logic."
    )
    parser.add_argument(
        "--base-config",
        default="",
        help="Base config path. If omitted, auto-select from config/*.yaml.",
    )
    parser.add_argument(
        "--output-root",
        default="tests/case_library",
        help="Directory where caseXXXX.yaml files will be written.",
    )
    parser.add_argument(
        "--project-output-root",
        default="outputs/case_library",
        help="Prefix used in generated config project.output_dir (e.g. outputs/case_library).",
    )
    parser.add_argument("--seed", type=int, default=20260320)
    parser.add_argument("--delay-count", type=int, default=100)
    parser.add_argument("--speed-count", type=int, default=100)
    parser.add_argument("--disruption-count", type=int, default=100)
    parser.add_argument("--combo-per-type", type=int, default=100)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def _to_posix(path_text: str) -> str:
    return path_text.replace("\\", "/").rstrip("/")


def _write_config_only(case_path: Path, config_payload: Dict[str, object], _meta_payload: Dict[str, object]) -> None:
    yaml = _require_yaml()
    yaml_path = case_path.with_suffix(".yaml")
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with yaml_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config_payload, file, allow_unicode=True, sort_keys=False)


def _validate_counts(args: argparse.Namespace) -> None:
    if args.delay_count != 100:
        raise ValueError("delay-count must be 100 (4*25).")
    if args.speed_count != 100:
        raise ValueError("speed-count must be 100 (5*20).")
    if args.disruption_count != 100:
        raise ValueError("disruption-count must be 100 (34/33/33).")
    if args.combo_per_type != 100:
        raise ValueError("combo-per-type must be 100 (4 types * 100 = 400).")


def main() -> None:
    args = parse_args()
    _validate_counts(args)

    base_config = gen.resolve_base_config(args.base_config)

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = gen.REPO_ROOT / output_root
    output_root.mkdir(parents=True, exist_ok=True)

    if args.clean and output_root.exists():
        for old_path in output_root.iterdir():
            if old_path.is_file() and old_path.suffix.lower() == ".yaml" and old_path.stem.startswith("case"):
                old_path.unlink()
            elif old_path.is_dir() and old_path.name.startswith("case"):
                shutil.rmtree(old_path)

    project_output_root = _to_posix(args.project_output_root)

    rng = random.Random(args.seed)
    base = gen.load_base_data(base_config)

    original_write_case = gen.write_case
    original_base_config_payload = gen.base_config_payload

    def patched_base_config_payload(case_name: str, _output_dir: str, base_data: Any) -> Dict[str, object]:
        output_dir = f"{project_output_root}/{case_name}"
        return original_base_config_payload(case_name, output_dir, base_data)

    gen.write_case = _write_config_only
    gen.base_config_payload = patched_base_config_payload

    try:
        case_index = 1
        case_index = gen.generate_delay_cases(rng, base, output_root, case_index, args.delay_count)
        case_index = gen.generate_speed_cases(rng, base, output_root, case_index, args.speed_count)
        case_index = gen.generate_disruption_cases(rng, base, output_root, case_index, args.disruption_count)
        case_index = gen.generate_combo_cases(rng, base, output_root, case_index, args.combo_per_type)
    finally:
        gen.write_case = original_write_case
        gen.base_config_payload = original_base_config_payload

    print(f"Generated {case_index - 1} case yaml files under {output_root}")
    print(f"project.output_dir prefix: {project_output_root}")


if __name__ == "__main__":
    main()
