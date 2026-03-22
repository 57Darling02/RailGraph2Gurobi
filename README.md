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

## Batch Case Config Generation (700 cases)

```powershell
python scripts/case_library_builder.py --output-root tests/case_library --project-output-root outputs/case_library --clean
```

This command generates config files only (`caseXXXX.yaml`) and keeps the same distribution logic:

- delay: 100
- speedlimit: 100
- disruption: 100
- combo: 400 (4 combo types * 100 each)

Then you can connect these configs to the main pipeline stages (`build/solve/export-timetable/analyze`) in batch.

Batch build from generated configs:

```powershell
python scripts/bench_build.py --config-root tests/case_library
```

Batch solve from generated configs:

```powershell
python scripts/bench_solve.py --config-root tests/case_library
```

Resume solve from a specific index range (1-based, inclusive):

```powershell
# solve from case #201 to the end
python scripts/bench_solve.py --config-root tests/case_library --start-index 201

# solve only case #201 ~ #400
python scripts/bench_solve.py --config-root tests/case_library --start-index 201 --end-index 400
```

`bench_solve.py` range-related options:

- `--start-index`: 1-based start index (default: `1`)
- `--end-index`: 1-based end index, inclusive (default: `0`, means no upper bound)
- `--limit`: applies after range slicing

Batch export-timetable from generated configs:

```powershell
python scripts/bench_export_timetable.py --config-root tests/case_library
```

Batch analyze from generated configs:

```powershell
python scripts/bench_analyze.py --config-root tests/case_library
```

## Import External `.sol` Into Standard Pipeline

Step 1: import external `.sol` files into standardized config/output layout:

```powershell
python scripts/import_solutions.py --solutions-root tests/solutions --base-config config/base_demo.yaml --generated-config-root tests/generated_configs --output-root outputs/solutions_import
```

Step 2: run export-timetable on imported cases:

```powershell
python scripts/bench_export_timetable.py --config-root tests/generated_configs
```

Step 3: run analyze on imported cases:

```powershell
python scripts/bench_analyze.py --config-root tests/generated_configs
```

## Import External `.lp` Into Standard Pipeline

Step 1: import external `.lp` files into standardized config/output layout:

```powershell
python scripts/import_lp.py --lp-root tests/lp --base-config config/base_demo.yaml --generated-config-root tests/generated_configs_lp --output-root outputs/lp_import
```

Step 2: run solve on imported cases:

```powershell
python scripts/bench_solve.py --config-root tests/generated_configs_lp
```

Step 3: continue with export-timetable and analyze if needed:

```powershell
python scripts/bench_export_timetable.py --config-root tests/generated_configs_lp
python scripts/bench_analyze.py --config-root tests/generated_configs_lp
```
## Common Errors

- `No module named core`: run commands from repository root.
- `Missing dependency`: install `pyyaml/openpyxl/pandas/matplotlib/gurobipy`.
- `No stations found for plotting`: set `analyze.enable_plot=false`.
- `Missing required config field: project.timetable_path`: fill required `project` input fields.








