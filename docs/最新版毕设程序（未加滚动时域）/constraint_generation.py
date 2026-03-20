import pandas as pd

# --------------------------
# 1. 数据预处理（动态读取Excel）
# --------------------------
def load_station_mileage(file_path='区间里程.xlsx'):
    try:
        df = pd.read_excel(file_path, sheet_name='Sheet1', engine='openpyxl')
        return dict(zip(df['车站名称'], df['里程（km）']))
    except Exception as e:
        raise ValueError(f"Excel读取失败: {str(e)}")

station_mileage = load_station_mileage()

# --------------------------
# 2. 方向判断规则
# --------------------------
def get_direction(start_station, end_station):
    try:
        start_mile = station_mileage[start_station]
        end_mile = station_mileage[end_station]
    except KeyError as e:
        raise ValueError(f"车站不存在: {str(e)}")

    return "上行" if start_mile > end_mile else "下行"

# --------------------------
# 3. 规则引擎核心（修改后）
# --------------------------
class ConstraintGeneration:
    def __init__(self):
        self.constraints = set()
        self.objectives = {}

    def add_generic_constraints(self):
        self.constraints.add("通用约束")

    def process_data(self, data_dict):
        """根据数据格式自动判断场景类型"""
        for (start, end), value in data_dict.items():
            # 判断逻辑：若值的第二个元素是嵌套元组，则为限速场景
            if isinstance(value[1], tuple) and len(value[1]) == 2:
                self._process_speed_limit({(start, end): value})
            # 否则视为中断场景
            else:
                self._process_interrupt({(start, end): value})

    def _process_delay(self, delays):
        self.constraints.add("晚点约束")
        self.objectives['delay'] = ("晚点目标函数", 1.0)

    def _process_speed_limit(self, speed_limits):
        for (start, end), _ in speed_limits.items():
            direction = get_direction(start, end)
            self.constraints.add(f"{direction}限速约束")
        self._add_objective('speed_limit', 0.5)

    def _process_interrupt(self, interrupts):
        for (start, end), _ in interrupts.items():
            direction = get_direction(start, end)
            self.constraints.add(f"{direction}中断约束")
        self._add_objective('interrupt', 0.5)

    def _add_objective(self, key, weight):
        current_weight = self.objectives.get(key, (None, 0))[1]
        self.objectives[key] = (f"{key}目标函数", current_weight + weight)

    def get_result(self):
        total_weight = sum(w for _, w in self.objectives.values())
        normalized_objectives = [
            (obj, w/total_weight)
            for obj, w in self.objectives.values()
        ]
        return {
            "constraints": list(self.constraints),
            "objectives": normalized_objectives
        }

# --------------------------
# 4. 使用示例（修改后）
# --------------------------
if __name__ == "__main__":
    # 输入数据（不再包含场景类型键）
    input_data = [
        {('徐州东', '枣庄'): (600, (28800, 32400))},
        {('泰安', '济南西'): (50100, 51000)}
    ]

    engine = ConstraintGeneration()
    engine.add_generic_constraints()

    # 处理所有输入数据
    for data in input_data:
        engine.process_data(data)

    result = engine.get_result()
    
    print("激活约束:", result["constraints"])
    print("目标函数权重分配:")
    for obj, weight in result["objectives"]:
        print(f"- {obj}: {weight:.1f}")

# --------------------------
# 输出示例（保持不变）
# --------------------------
# 激活约束: ['通用约束', '上行限速约束', '下行中断约束']
# 目标函数权重分配:
# - speed_limit目标函数: 0.5
# - interrupt目标函数: 0.5