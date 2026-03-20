# 列车运行图突发情况调整系统

本项目用于在既有运行图基础上，针对“晚点、限速、中断”等突发场景，自动构建并求解优化模型，输出调整后的上下行时刻表。

- 入口脚本：[`timetable_adjustment.py`]
- 配置文件：[`config.py`]

## 目录结构

- `timetable_adjustment.py` 主流程与规则匹配入口
- `config.py` 路径与突发场景配置
- `timetable_data.py` Excel 运行图读取与阶段数据构建
- `timetable_utils.py` 读取/时间转换/输出等工具函数
- `unit_model.py` 不同场景的单元模型封装与结果输出
- `event_activity_model.py` 基于 Gurobi 的事件-活动优化模型实现
- `上行计划时刻表.xlsx`、`下行计划时刻表.xlsx` 基础运行图
- `调整后的上行时刻表.xlsx`、`调整后的下行时刻表.xlsx` 调整结果

## 环境依赖
- Python 3.9+（已见到 `__pycache__` 兼容 3.9/3.10/3.12）
- 主要库：`pandas`、`openpyxl`、`gurobipy`
- 必须安装并激活 Gurobi（含有效 License），否则无法求解模型

Windows 安装示例：
```powershell
pip install pandas openpyxl gurobipy
# 安装 Gurobi 软件并配置 license 后方可运行
```

## 数据格式要求
运行图 Excel（默认表索引 0）需包含列：
- `train_ID` 车次号
- `station` 车站名
- `arrival_time` 到达时间（格式 `HH:MM:SS`）
- `departure_time` 出发时间（格式 `HH:MM:SS`）

读取与转换参考：
- 读取：[`read_excel`]
- 时间转秒：[`convert_time_to_seconds`]

注意：
- 站名需与运行图一致（与配置场景的站名完全匹配）
- 时间均会根据 `BASE_DATE` 转换为当日秒数

## 配置指南
在 [`config.py`] 中设置：

- 文件路径
```python
UP_FILE_PATH = '上行计划时刻表.xlsx'
DOWN_FILE_PATH = '下行计划时刻表.xlsx'
AJUSTED_UP_FILE_PATH = '调整后的上行时刻表.xlsx'
AJUSTED_DOWN_FILE_PATH = '调整后的下行时刻表.xlsx'
BASE_DATE = '2024-06-15'
```

- 初始晚点场景
```python
# 列表项: (车次号, 车站名, 事件类型 'dep'/'arr', 晚点时长(秒))
PRIMARY_DELAY_SCENARIOS = [
    ('G2661', 'jinanxi', 'dep', 60000),
    ('G113', 'taian', 'arr', 24000),
]
```

- 区间限速场景
```python
# 字典项: (起点站, 终点站): (限速参数, (开始秒, 结束秒))
SPEED_LIMITATION_SCENARIOS = {
    # 示例（开启时取消上方的 {}）:
    # ('滕州东', '枣庄'): (2280, (48000, 51600))
}
```

- 区间中断场景
```python
# 字典项: (起点站, 终点站): (开始秒, 结束秒)
INTERVAL_INTERRUPT_SCENARIOS = {
    # 示例:
    # ('滕州东', '曲阜东'): (30000, 31800)
}
```

提示：
- 上/下行晚点会根据车次最后一位数字的奇偶自动区分（偶数→上行，奇数→下行），见函数 [`separate_up_down_delay`](file:///g:/WorkSpace/最新版毕设程序（未加滚动时域）/最新版毕设程序（未加滚动时域）/timetable_utils.py#L74-L91)。

## 运行方法
在项目目录下执行：
```powershell
python timetable_adjustment.py
```
执行流程概览（见 [`timetable_adjustment.py`](file:///g:/WorkSpace/最新版毕设程序（未加滚动时域）/最新版毕设程序（未加滚动时域）/timetable_adjustment.py)):
1. 读取配置并识别场景，生成约束标签（如“上行晚点约束”、“下行限速约束”、“通用约束”等）
2. 基于规则引擎匹配相应的单元模型（`unit_model.py`）
3. 调用 `event_activity_model.py` 构建并求解优化模型
4. 输出调整后的时刻表 Excel（上/下行）

## 规则与模型映射
规则列表见入口脚本中 `rules`（约第 64-176 行）。典型映射关系：
- 仅上行晚点 + 通用约束 → `up_delay_model` + 下行原样输出
- 仅下行限速 + 通用约束 → `down_limitation_model` + 上行原样输出
- 上下行晚点叠加 → 同时调用 `up_delay_model` 与 `down_delay_model`
- 上行限速+中断 → `up_limitation_interrupt_model`
- 复杂叠加（如上行晚点+限速+中断 + 下行限速）→ 对应复合单元模型与下行限速模型

各单元模型最终通过 [`output_data`](file:///g:/WorkSpace/最新版毕设程序（未加滚动时域）/最新版毕设程序（未加滚动时域）/timetable_utils.py#L229-L266) 输出结果到配置指定的 Excel 路径。

## 输出结果
- `调整后的上行时刻表.xlsx`：调整后上行全量到发时刻
- `调整后的下行时刻表.xlsx`：调整后下行全量到发时刻
- 格式为合并后的到发表（到达/出发列可能存在空值，按事件生成）

## 常见问题
- 无输出/无动作：
  - 检查是否真的配置了场景（字典是否为空）
  - 检查站名与运行图是否一致
  - 复杂场景是否被 `rules` 覆盖（规则中有严格的 `len(constraints_list)` 判断）
- Gurobi 报错：
  - 确认已安装 Gurobi 并配置有效 License
  - Python 环境与 `gurobipy` 版本兼容
- 上下行判定异常：
  - 晚点场景上/下行依赖车次末位数字的奇偶（如人工命名非数字结尾会导致判定失败）
- 时间解析错误：
  - 运行图时间需为 `HH:MM:SS`，`BASE_DATE` 会用于转为当日秒数

## 开发提示
- 数据处理入口见：
  - 上行：[`load_and_process_upside_data`]
  - 下行：[`load_and_process_downside_data`]
- 规则引擎使用字符串表达式与上下文（`has_all_constraints`/`constraints_list`），详见入口脚本的 `Rule` 与 `ConstraintContext`。
- 若新增场景组合，需在 `rules` 中添加对应表达式与 `unit_model` 调用。