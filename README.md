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
  arr_arr_headway_seconds: 180
  dep_dep_headway_seconds: 180
  dwell_seconds_at_stops: 120
  big_m: 100000
  tolerance_delay_seconds: 7200

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

## Batch Regression Case Generation (700 cases)

```powershell
python scripts/generate_case_library.py --clean
python -m unittest tests/test_translator_bulk.py
```

Default distribution:

- delay: 100
- speedlimit: 100
- disruption: 100
- combo: 400 (4 combo types * 100 each)

Optional env vars:

- `RAIL_CASE_ROOT`: case root dir (default `tests/case_library`)
- `RAIL_CASE_LIMIT`: run first N cases only
- `RAIL_ENABLE_MAIN_RUN=1`: also run end-to-end `main.py run`
- `RAIL_MAIN_RUN_LIMIT`: max cases for end-to-end run (default 5)

## Batch Analyze Existing `.sol`

```powershell
python scripts/batch_solution_analyze.py --solutions-root tests/solutions --base-config tests/test.yaml
```

This script will:

- recursively scan `tests/solutions/**/*.sol`
- auto-generate one config per `.sol`
- run `export-timetable + analyze`
- aggregate:
  - `outputs/solutions_batch/summary.csv`
  - `outputs/solutions_batch/summary.json`

## Common Errors

- `No module named core`: run commands from repository root.
- `Missing dependency`: install `pyyaml/openpyxl/pandas/matplotlib/gurobipy`.
- `No stations found for plotting`: set `analyze.enable_plot=false`.
- `Missing required config field: project.timetable_path`: fill required `project` input fields.
