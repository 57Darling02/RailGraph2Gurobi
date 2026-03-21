# RailGraph2Gurobi

将列车运行图与里程表转译为 LP 调度模型，并支持求解、回写调整后时刻表、指标分析与运行图绘制。

## 1. 当前代码状态

- 入口：`main.py`（子命令式 CLI）
- 主流程：`load -> validate -> translate -> build -> solve -> export -> analyze`
- 已支持场景约束：
  - `delays`
  - `speed_limits`
  - `interruptions`
- 目标函数模式（`solver.objective_mode`）：
  - `delay`
  - `abs`
  - `cal_delay_plus_cancel`
- 当前默认 demo 配置：`config/demo.yaml`
  - 启用指标分析：`analyze.enable_metrics: true`
  - 启用运行图绘制：`analyze.enable_plot: true`

### 目录结构

```text
RailGraph2Gurobi/
  main.py
  README.md

  config/
    demo.yaml

  core/
    loader.py
    validator.py
    translator.py
    builder.py
    exporter.py
    solver.py
    postprocess.py
    types.py

  constraints/
    base.py
    delay.py
    speed_limit.py
    interruption.py
    objective_modes.py
    registry.py

  analysis/
    io.py
    metrics.py
    plot.py

  inputs/
  outputs/
  tests/
  docs/
```

## 2. 5 分钟快速上手

### 2.1 环境要求

- Python `3.9+`
- 求解器：Gurobi（仅 `solve` / `run` 需要）

### 2.2 安装依赖（PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -U pip
pip install pyyaml openpyxl pandas matplotlib
pip install gurobipy
```

说明：
- 如果只想先验证建模链路，可暂不安装 `gurobipy`，先执行 `build`。

### 2.3 直接运行 demo

1. 仅建模（不依赖 Gurobi）：
```powershell
python main.py build --config config/demo.yaml
```

2. 求解（需要 Gurobi）：
```powershell
python main.py solve --config config/demo.yaml
```

3. 回写时刻表：
```powershell
python main.py export-timetable --config config/demo.yaml
```

4. 分析与画图：
```powershell
python main.py analyze --config config/demo.yaml
```

5. 一键全流程：
```powershell
python main.py run --config config/demo.yaml
```

不写子命令时默认等价于 `run`：

```powershell
python main.py --config config/demo.yaml
```

### 2.4 成功后应看到的文件

默认输出目录来自 `project.output_dir`（demo 为 `outputs/demo`）：

- `outputs/demo/model.lp`
- `outputs/demo/solution.sol`
- `outputs/demo/adjusted_timetable.xlsx`
- `outputs/demo/analysis_metrics.xlsx`
- `outputs/demo/timetable_plot.png`

## 3. 配置说明

`config/demo.yaml` 使用单文件分节：

```yaml
project:
  name: demo
  output_dir: outputs/demo

input:
  timetable_path: inputs/下行计划时刻表.xlsx
  mileage_path: inputs/区间里程.xlsx
  timetable_sheet_name: Sheet1
  mileage_sheet_name: Sheet1

solver:
  objective_delay_weight: 1.0
  objective_mode: abs
  arr_arr_headway_seconds: 180
  dep_dep_headway_seconds: 180
  dwell_seconds_at_stops: 120
  big_m: 100000
  tolerance_delay_seconds: 7200

scenarios:
  delays: []
  speed_limits: []
  interruptions: []

analyze:
  enable_metrics: true
  enable_plot: true
  plot_grid: true
  plot_title: Train Timetable
```

关键点：
- `build/solve/export_timetable` 的产物路径由程序固定推导，不需要在 yaml 中再配这些 section。
- 产物统一落在 `project.output_dir` 下。
- `case_name = project.name`（若缺省则退回配置文件名）。

## 4. 输入规范

### 4.1 运行图 Excel

前四列必须按顺序为（允许后续附加列）：

```text
train_id | station | arrival_time | departure_time
```

校验规则：
- 每行至少有一个时间（到或发）
- 同车次至少 2 行
- 同车次站名不可重复
- 若到发都存在，要求 `departure_time >= arrival_time`
- `train_id` 仅允许 `A-Z a-z 0-9 _ -`
- 时间格式为 `HH:MM:SS`（支持单数字小时输入，程序会规范化）
- 末站若给出 `departure_time`，必须与 `arrival_time` 相等

### 4.2 里程表 Excel

前两列必须按顺序为（允许后续附加列）：

```text
station | mileage
```

校验规则：
- `station` 不可重复
- `mileage` 必须可转为浮点数
- 运行图中的站名必须全部能在里程表中找到

## 5. 场景 API

```yaml
scenarios:
  delays: [DelayScenario, ...]
  speed_limits: [SpeedLimitScenario, ...]
  interruptions: [InterruptionScenario, ...]
```

### delays

```yaml
- train_id: <string>
  station: <string>
  event_type: <arr|dep>
  seconds: <int>=0
```

### speed_limits

```yaml
- start_station: <string>
  end_station: <string>
  extra_seconds: <int>=0
  start_time: <HH:MM:SS>
  end_time: <HH:MM:SS>
```

### interruptions

```yaml
- start_station: <string>
  end_station: <string>
  start_time: <HH:MM:SS>
  end_time: <HH:MM:SS>
```

## 6. 常见报错与排查

- `Missing dependency: pyyaml`：安装 `pyyaml`
- `Missing dependency: openpyxl`：安装 `openpyxl`
- `Missing dependency: gurobipy`：执行 `solve/run` 但未安装 Gurobi Python 包
- `... leading columns must be ...`：Excel 前置列名或顺序不符合要求
- `Delay scenario event not found in timetable`：配置的晚点事件在运行图中不存在
- `Unsupported objective_mode`：`solver.objective_mode` 不在支持列表中

## 7. 开发与自测

运行已有测试：

```powershell
python -m unittest tests/test_input_normalization.py
```

批量生成并验证转换器样例库（700个）：

```powershell
python scripts/generate_case_library.py --clean
python -m unittest tests/test_translator_bulk.py
```

如果你要新增约束模块，入口在 `constraints/registry.py`。
