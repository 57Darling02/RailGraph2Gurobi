# RailGraph2Gurobi

4-stage pipeline: **build → solve → export-timetable → analyze**

## Quick Start

```bash
# Run all stages at once
python main.py run --config config/delays_demo.yaml

# Or run each stage separately
python main.py build            --config config/delays_demo.yaml
python main.py solve            --config config/delays_demo.yaml
python main.py export-timetable --config config/delays_demo.yaml
python main.py analyze          --config config/delays_demo.yaml
```

## Config

```yaml
project:
  name: my_case
  output_dir: outputs/my_case
  timetable_path: inputs/timetable.xlsx
  mileage_path: inputs/mileage.xlsx
  timetable_sheet_name: Sheet1
  mileage_sheet_name: Sheet1

build:
  scenarios:
    delays:       []   # {train_id, station, event_type, seconds}
    speed_limits: []   # {start_station, end_station, extra_seconds, start_time, end_time}
    interruptions: []  # {start_station, end_station, start_time, end_time}

solve:
  lp_path: ""                      # override LP input path (default: {output_dir}/{name}.lp)
  objective_mode: abs              # abs | delay
  objective_delay_weight: 1.0
  cancellation_enabled: false
  cancellation_penalty_weight: 1000.0
  arr_arr_headway_seconds: 180
  dep_dep_headway_seconds: 180
  dwell_seconds_at_stops: 120
  big_m: 100000
  tolerance_delay_seconds: 7200

export-timetable:
  sol_path: ""                     # override SOL input path (default: {output_dir}/{name}.sol)

analyze:
  enable_metrics: true
  enable_plot: false
  plot_grid: true
  plot_title: Train Timetable
  adj_timetable_path: ""           # override adjusted timetable input
  adj_timetable_sheet_name: Sheet1
```

Stage outputs (convention, no config needed):

| Stage | Output |
|---|---|
| build | `{output_dir}/{name}.lp` |
| solve | `{output_dir}/{name}.sol` |
| export-timetable | `{output_dir}/adjusted_timetable.xlsx` |
| analyze | `{output_dir}/analysis_metrics.xlsx`, `{output_dir}/timetable_plot.png` |

## Input Format

Timetable (first 4 columns): `train_id | station | arrival_time | departure_time`

Mileage (first 2 columns): `station | mileage`

**Note:** scenario `start_station → end_station` must match the actual train travel direction in the timetable.

## Batch Pipeline

Generate case configs (70 cases by default):

```bash
python -u scripts/case_library_builder.py \
  --output-root tests/case_library \
  --project-output-root outputs/case_library \
  --clean > outputs/case_library_builder.log 2>&1
```

Run all 4 batch stages in order:

```bash
python -u scripts/bench_build.py           --config-root tests/case_library > outputs/bench_build.log 2>&1
python -u scripts/bench_solve.py           --config-root tests/case_library > outputs/bench_solve.log 2>&1
python -u scripts/bench_export_timetable.py --config-root tests/case_library > outputs/bench_export_timetable.log 2>&1
python -u scripts/bench_analyze.py         --config-root tests/case_library > outputs/bench_analyze.log 2>&1
```

Use `tail -f outputs/<script>.log` to monitor progress.

### bench_solve.py Options

| Option | Default | Description |
|---|---|---|
| `--start-index` | `1` | 1-based start index (inclusive) |
| `--end-index` | `0` | 1-based end index (inclusive, 0 = no upper bound) |
| `--workers` | `1` | parallel solver processes |
| `--threads-per-solve` | `0` | Gurobi threads per solve (0 = `cpu_count // workers`) |
| `--time-limit` | `0` | seconds per solve (0 = no limit); timeout with feasible sol → `timeout` |
| `--mip-gap` | `0` | relative MIP gap (0 = Gurobi default ~1e-4); e.g. `0.01` = 1% |

Multi-core example:

```bash
python -u scripts/bench_solve.py --config-root tests/case_library \
  --workers 4 --threads-per-solve 32 > outputs/bench_solve.log 2>&1
```

## Import External Solutions

### Import `.sol` files

```bash
python -u scripts/import_solutions.py \
  --solutions-root tests/solutions \
  --base-config config/base_demo.yaml \
  --generated-config-root tests/generated_configs \
  --output-root outputs/solutions_import > outputs/import_solutions.log 2>&1

python -u scripts/bench_export_timetable.py --config-root tests/generated_configs > outputs/bench_export_timetable.log 2>&1
python -u scripts/bench_analyze.py          --config-root tests/generated_configs > outputs/bench_analyze.log 2>&1
```

### Import `.lp` files

```bash
python -u scripts/import_lp.py \
  --lp-root tests/lp \
  --base-config config/base_demo.yaml \
  --generated-config-root tests/generated_configs_lp \
  --output-root outputs/lp_import \
  --scenario-inference require > outputs/import_lp.log 2>&1
```

If the LP uses a different timetable/mileage than the base config, add `--timetable-path` / `--mileage-path` overrides. To skip scenario inference: `--scenario-inference off`.

```bash
python -u scripts/bench_solve.py            --config-root tests/generated_configs_lp > outputs/bench_solve.log 2>&1
python -u scripts/bench_export_timetable.py --config-root tests/generated_configs_lp > outputs/bench_export_timetable.log 2>&1
python -u scripts/bench_analyze.py          --config-root tests/generated_configs_lp \
  --scenario-report on --scenario-report-scope batch > outputs/bench_analyze.log 2>&1
```

`bench_analyze.py` scenario report options: `--scenario-report on|off`, `--scenario-report-scope batch|per_case|both`.

## Common Errors

| Error | Fix |
|---|---|
| `No module named core` | Run from repository root |
| `Missing dependency` | Install `pyyaml openpyxl pandas matplotlib gurobipy` |
| `No stations found for plotting` | Set `analyze.enable_plot: false` |
| `Missing required config field: project.timetable_path` | Fill required `project` fields |
| `scenario_inference_status=failed` | Verify LP naming convention matches this project; check `--timetable-path` / `--mileage-path` point to the correct inputs |
