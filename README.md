# RailGraph2Gurobi

RailGraph2Gurobi provides a clean 4-stage workflow:

1. Build LP model (`build`)
2. Solve LP (`solve`)
3. Export adjusted timetable (`export-timetable`)
4. Analyze metrics/plot (`analyze`)

You can run a single stage, or run all stages with `run`.

## Quick Start

```bash
python main.py run --config config/delays_demo.yaml
```

Step by step:

```bash
python main.py build --config config/delays_demo.yaml
python main.py solve --config config/delays_demo.yaml
python main.py export-timetable --config config/delays_demo.yaml
python main.py analyze --config config/delays_demo.yaml
```

## Config Design (Convention over Configuration)

Single file entry: `config.yaml`

```yaml
project:
  name: mixed_scenarios_demo
  output_dir: outputs/mixed_scenarios_demo
  timetable_path: inputs/your_timetable.xlsx
  mileage_path: inputs/your_mileage.xlsx
  timetable_sheet_name: Sheet1
  mileage_sheet_name: Sheet1

build:
  scenarios:
    delays: []
    speed_limits: []
    interruptions: []

solve:
  lp_path: ""
  objective_delay_weight: 1.0
  objective_mode: abs
  cancellation_enabled: false
  cancellation_penalty_weight: 1000.0
  arr_arr_headway_seconds: 180
  dep_dep_headway_seconds: 180
  dwell_seconds_at_stops: 120
  big_m: 100000
  cancellation_threshold_seconds: 7200

export-timetable:
  sol_path: ""

analyze:
  enable_metrics: true
  enable_plot: false
  plot_grid: true
  plot_title: Train Timetable
  adj_timetable_path: ""
  adj_timetable_sheet_name: Sheet1
```

### Stage Inputs and Fixed Outputs

- `build`
  - reads: `project.*` + `build.scenarios`
  - outputs: `{output_dir}/{name}.lp`

- `solve`
  - reads: `solve.*`
  - `objective_mode` supports: `delay` / `abs`
  - cancellation is independent of `objective_mode`, controlled by:
    - `solve.cancellation_enabled`
    - `solve.cancellation_penalty_weight`
    - `solve.cancellation_threshold_seconds` (or `tolerance_delay_seconds`)
  - LP input: `solve.lp_path` if non-empty, otherwise `{output_dir}/{name}.lp`
  - outputs: `{output_dir}/{name}.sol`

- `export-timetable`
  - reads: `export-timetable.sol_path`
  - SOL input: `sol_path` if non-empty, otherwise `{output_dir}/{name}.sol`
  - outputs: `{output_dir}/adjusted_timetable.xlsx`

- `analyze`
  - planned timetable: `project.timetable_path + project.timetable_sheet_name`
  - adjusted timetable input: `analyze.adj_timetable_path` if non-empty, otherwise `{output_dir}/adjusted_timetable.xlsx`
  - adjusted sheet: `analyze.adj_timetable_sheet_name` if non-empty, otherwise `Sheet1`
  - default outputs:
    - `{output_dir}/analysis_metrics.xlsx`
    - `{output_dir}/timetable_plot.png`

## Required Input Headers

Timetable first 4 columns must be:

```text
train_id | station | arrival_time | departure_time
```

Mileage first 2 columns must be:

```text
station | mileage
```

## Batch Case Config Generation (70 cases)

```powershell
python -u scripts/case_library_builder.py --output-root tests/case_library --project-output-root outputs/case_library --clean > outputs/case_library_builder.log 2>&1
```

This command generates config files only (`caseXXXX.yaml`) and keeps the same distribution logic:

- delay: 10
- speedlimit: 10
- disruption: 10
- combo: 40 (4 combo types * 10 each)

Then you can connect these configs to the main pipeline stages (`build/solve/export-timetable/analyze`) in batch.
If you need the original 700-case setup, run with: `--delay-count 100 --speed-count 100 --disruption-count 100 --combo-per-type 100`.
To avoid `screen` scrollback buffer overflow during long runs, commands below redirect all output to log files under `outputs/` and use `python -u` for line-buffered writes. You can monitor progress with `tail -f outputs/<script>.log`.

Batch build from generated configs:

```powershell
python -u scripts/bench_build.py --config-root tests/case_library > outputs/bench_build.log 2>&1
```

Batch solve from generated configs:

```powershell
python -u scripts/bench_solve.py --config-root tests/case_library > outputs/bench_solve.log 2>&1
```

Resume solve from a specific index range (1-based, inclusive):

```powershell
# solve from case #201 to the end
python -u scripts/bench_solve.py --config-root tests/case_library --start-index 201 > outputs/bench_solve.log 2>&1

# solve only case #201 ~ #400
python -u scripts/bench_solve.py --config-root tests/case_library --start-index 201 --end-index 400 > outputs/bench_solve.log 2>&1
```

`bench_solve.py` range-related options:

- `--start-index`: 1-based start index (default: `1`)
- `--end-index`: 1-based end index, inclusive (default: `0`, means no upper bound)
- `--limit`: applies after range slicing

Batch export-timetable from generated configs:

```powershell
python -u scripts/bench_export_timetable.py --config-root tests/case_library > outputs/bench_export_timetable.log 2>&1
```

Batch analyze from generated configs:

```powershell
python -u scripts/bench_analyze.py --config-root tests/case_library > outputs/bench_analyze.log 2>&1
```

## Import External `.sol` Into Standard Pipeline

Step 1: import external `.sol` files into standardized config/output layout:

```powershell
python -u scripts/import_solutions.py --solutions-root tests/solutions --base-config config/base_demo.yaml --generated-config-root tests/generated_configs --output-root outputs/solutions_import > outputs/import_solutions.log 2>&1
```

Note: `export-timetable` now supports both solution variable styles:
- current project style, e.g. `t_e123`
- legacy style, e.g. `event_start_time(train,station,event_type)` / `event_start_time[train,station,event_type]`

Step 2: run export-timetable on imported cases:

```powershell
python -u scripts/bench_export_timetable.py --config-root tests/generated_configs > outputs/bench_export_timetable.log 2>&1
```

Step 3: run analyze on imported cases:

```powershell
python -u scripts/bench_analyze.py --config-root tests/generated_configs > outputs/bench_analyze.log 2>&1
```

## Import External `.lp` Into Standard Pipeline

`import_lp.py` now defaults to `--scenario-inference auto`.
When the imported `.lp` was generated by this project (or follows the same naming convention), the script will rebuild event/section mapping from `timetable_path + mileage_path` and write inferred `build.scenarios` back into each generated case yaml.

Inference input priority:

- `--timetable-path` / `--mileage-path` / sheet-name overrides, if provided
- otherwise `project.*` in `--base-config` (falling back to legacy `input.*`)

Step 1: import `.lp` files and require successful scenario inference:

```powershell
python -u scripts/import_lp.py --lp-root tests/lp --base-config config/base_demo.yaml --generated-config-root tests/generated_configs_lp --output-root outputs/lp_import --scenario-inference require > outputs/import_lp.log 2>&1
```

If this LP batch uses a different timetable or mileage file than the base config, override them explicitly:

```powershell
python -u scripts/import_lp.py --lp-root tests/lp --base-config config/base_demo.yaml --generated-config-root tests/generated_configs_lp --output-root outputs/lp_import --timetable-path inputs/your_timetable.xlsx --mileage-path inputs/your_mileage.xlsx --scenario-inference require > outputs/import_lp.log 2>&1
```

If you only want the old behavior (import LP without inferring scenarios), turn inference off:

```powershell
python -u scripts/import_lp.py --lp-root tests/lp --base-config config/base_demo.yaml --generated-config-root tests/generated_configs_lp --output-root outputs/lp_import --scenario-inference off > outputs/import_lp.log 2>&1
```

After import, review `outputs/lp_import/import_lp_summary.csv`:

- `scenario_inference_status`: `ok` / `skipped` / `failed` / `disabled`
- `inferred_delay_count`, `inferred_speed_limit_count`, `inferred_interruption_count`
- `speed_limit_groups`: `exact` means one canonical window matched directly; `cover` means the script reconstructed the same affected-train set with one or more canonical windows

Step 2: run solve on imported cases:

```powershell
python -u scripts/bench_solve.py --config-root tests/generated_configs_lp > outputs/bench_solve.log 2>&1
```

Step 3: continue with export-timetable if needed:

```powershell
python -u scripts/bench_export_timetable.py --config-root tests/generated_configs_lp > outputs/bench_export_timetable.log 2>&1
```

Step 4: run `bench_analyze.py` for batch scenario statistics and regular analyze outputs:

```powershell
python -u scripts/bench_analyze.py --config-root tests/generated_configs_lp --scenario-report on --scenario-report-scope batch > outputs/bench_analyze.log 2>&1
```

`bench_analyze.py` now supports two parallel responsibilities:

- regular analyze stage: metrics and adjusted timetable plots when `analyze.enable_metrics/enable_plot` are enabled and the adjusted timetable exists; adjusted timetable plots now also overlay the inferred/configured scenarios as translucent blocks
- scenario statistics stage: batch or per-case scenario distribution analysis based only on `build.scenarios + timetable_path + mileage_path`

Important behavior:

- if a config has no adjusted timetable yet, `bench_analyze.py` will mark the regular analyze stage as `skipped`, but the scenario statistics stage can still succeed
- this means you can run scenario batch statistics directly after `import_lp.py`, even before exporting adjusted timetables

Scenario report options:

- `--scenario-report on|off`
- `--scenario-report-scope batch|per_case|both`
- `--scenario-report-output-root <dir>`

Default batch outputs are written under `<summary-json-dir>/scenario_analysis_batch/`:

- `scenario_batch_summary.xlsx`
- `scenario_batch_summary.json`
- `scenario_batch_timetable.png` (planned timetable with all scenarios overlaid)
- `scenario_batch_type_distribution.png`
- `scenario_batch_case_distribution.png` (time-of-day distribution across the whole batch)
- `scenario_batch_location_distribution.png`
- `scenario_batch_coverage_distribution.png`

Coverage semantics:

- `delay`: spatial coverage = affected stations / all stations
- `speed_limit`: spatial coverage = affected base sections / all base sections
- `interruption`: spatial coverage = affected base sections / all base sections
- time coverage = union length of the colored timetable blocks on the time axis / total timetable span

If you also want per-case scenario reports:

```powershell
python -u scripts/bench_analyze.py --config-root tests/generated_configs_lp --scenario-report on --scenario-report-scope both > outputs/bench_analyze.log 2>&1
```
## Common Errors

- `No module named core`: run commands from repository root.
- `Missing dependency`: install `pyyaml/openpyxl/pandas/matplotlib/gurobipy`.
- `No stations found for plotting`: set `analyze.enable_plot=false`.
- `Missing required config field: project.timetable_path`: fill required `project` input fields.
- `scenario_inference_status=skipped/failed`: verify the imported `.lp` uses this project's naming convention, and make sure `--base-config` or the `--timetable-path/--mileage-path` overrides point to the exact timetable and mileage inputs used to build that LP.














