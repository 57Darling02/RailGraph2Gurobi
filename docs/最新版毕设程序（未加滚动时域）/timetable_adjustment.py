from timetable_data import TimetableData
import timetable_utils as utils
from event_activity_model import EventActivityModel
import config
import time
import constraint_generation
import unit_model as unit


# 定义规则上下文类
class ConstraintContext:
    def __init__(self, constraints_list):
        self.constraints_list = constraints_list
        print(f"constraints_list: {self.constraints_list}")

    def has_constraint(self, constraint):
        return constraint in self.constraints_list

    def has_all_constraints(self, *constraints):
        result = all(self.has_constraint(c) for c in constraints)
        print(f"has_all_constraints({constraints}): {result}")
        return result
    
# 定义规则类
class Rule:
    def __init__(self, rule_str, context):
        self.rule_str = rule_str
        self.context = context

    def matches(self):
        global_namespace = {
            'has_all_constraints': self.context.has_all_constraints
        }
        return eval(self.rule_str, global_namespace, self.context.__dict__)

def main():
    # 实例化
    timetable_data = TimetableData()
    event_activity_model = EventActivityModel()
    constraints_list = []
    # 读取晚点场景、限速场景、中断场景并根据输入的突发事件信息判断需要调用哪些约束
    delay = config.Config.PRIMARY_DELAY_SCENARIOS
    upside_delay_data, downside_delay_data = utils.separate_up_down_delay(delay)
    if upside_delay_data != {}:
        constraints_list.append('上行晚点约束')
    if downside_delay_data != {}:
        constraints_list.append('下行晚点约束')

    limitation = config.Config.SPEED_LIMITATION_SCENARIOS
    interrupt = config.Config.INTERVAL_INTERRUPT_SCENARIOS
    input_data = [limitation, interrupt]
    engine = constraint_generation.ConstraintGeneration()
    engine.add_generic_constraints()
    for data in input_data:
        engine.process_data(data)
    result = engine.get_result()
    constraints_list.extend(result["constraints"])
    # print(constraints_list)

    # 创建规则上下文
    context = ConstraintContext(constraints_list)

    # 定义规则和操作，根据突发事件场景调用单元模型
    rules = [
        {
            "rule": "has_all_constraints('上行晚点约束', '通用约束') and len(constraints_list) == 2",
            "action": lambda: [unit.up_delay_model(timetable_data, event_activity_model, upside_delay_data),
                               unit.ajusted_down_timetable()]
        },
        {
            "rule": "has_all_constraints('下行晚点约束', '通用约束') and len(constraints_list) == 2",
            "action": lambda: [unit.down_delay_model(timetable_data, event_activity_model, downside_delay_data),
                               unit.ajusted_up_timetable()]
        },
        {
            "rule": "has_all_constraints('上行限速约束', '通用约束') and len(constraints_list) == 2",
            "action": lambda: [unit.up_limitation_model(timetable_data, event_activity_model, limitation),
                               unit.ajusted_down_timetable()]
        },
        {
            "rule": "has_all_constraints('下行限速约束', '通用约束') and len(constraints_list) == 2",
            "action": lambda: [unit.down_limitation_model(timetable_data, event_activity_model, limitation),
                               unit.ajusted_up_timetable()]
        },
        {
            "rule": "has_all_constraints('上行中断约束', '通用约束') and len(constraints_list) == 2",
            "action": lambda: [unit.up_interrupt_model(timetable_data, event_activity_model, interrupt),
                               unit.ajusted_down_timetable()]
        },
        {
            "rule": "has_all_constraints('下行中断约束', '通用约束') and len(constraints_list) == 2",
            "action": lambda: [unit.down_interrupt_model(timetable_data, event_activity_model, interrupt),
                               unit.ajusted_up_timetable()]
        },        
        {
            "rule": "has_all_constraints('上行晚点约束', '下行晚点约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_delay_model(timetable_data, event_activity_model, upside_delay_data),
                               unit.down_delay_model(timetable_data, event_activity_model, downside_delay_data)]
        },
        {
            "rule": "has_all_constraints('上行限速约束', '下行限速约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_limitation_model(timetable_data, event_activity_model, limitation),
                               unit.down_limitation_model(timetable_data, event_activity_model, limitation)]
        },
        {
            "rule": "has_all_constraints('上行中断约束', '下行中断约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_interrupt_model(timetable_data, event_activity_model, interrupt),
                               unit.down_interrupt_model(timetable_data, event_activity_model, interrupt)]
        },        
        {
            "rule": "has_all_constraints('上行晚点约束', '下行限速约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_delay_model(timetable_data, event_activity_model, upside_delay_data),
                               unit.down_limitation_model(timetable_data, event_activity_model, limitation)]
        },
        {
            "rule": "has_all_constraints('上行晚点约束', '下行中断约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_delay_model(timetable_data, event_activity_model, upside_delay_data),
                               unit.down_interrupt_model(timetable_data, event_activity_model, interrupt)]
        },
        {
            "rule": "has_all_constraints('上行限速约束', '下行中断约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_limitation_model(timetable_data, event_activity_model, limitation),
                               unit.down_interrupt_model(timetable_data, event_activity_model, interrupt)]
        },
        {
            "rule": "has_all_constraints('上行限速约束', '下行晚点约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_limitation_model(timetable_data, event_activity_model, limitation),
                               unit.down_delay_model(timetable_data, event_activity_model, downside_delay_data)]
        },

        {
            "rule": "has_all_constraints('上行中断约束', '下行晚点约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_interrupt_model(timetable_data, event_activity_model, interrupt),
                               unit.down_delay_model(timetable_data, event_activity_model, downside_delay_data)]
        },        
        {
            "rule": "has_all_constraints('上行中断约束', '下行限速约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_interrupt_model(timetable_data, event_activity_model, interrupt),
                               unit.down_limitation_model(timetable_data, event_activity_model, limitation)]
        },
        {
            "rule": "has_all_constraints('上行晚点约束', '上行限速约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_delay_limitation_model(timetable_data, event_activity_model, upside_delay_data, limitation),
                               unit.ajusted_down_timetable()]
        },
        {
            "rule": "has_all_constraints('上行限速约束', '上行中断约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.up_limitation_interrupt_model(timetable_data, event_activity_model, interrupt, limitation),
                               unit.ajusted_down_timetable()]
        },
        {
            "rule": "has_all_constraints('上行限速约束', '上行中断约束', '下行限速约束', '通用约束') and len(constraints_list) == 4",
            "action": lambda: [unit.up_limitation_interrupt_model(timetable_data, event_activity_model, interrupt, limitation),
                               unit.down_limitation_model(timetable_data, event_activity_model, limitation)]
        },
        {
            "rule": "has_all_constraints('上行限速约束', '上行晚点约束', '下行限速约束', '通用约束') and len(constraints_list) == 4",
            "action": lambda: [unit.up_delay_limitation_model(timetable_data, event_activity_model, upside_delay_data, limitation),
                               unit.down_limitation_model(timetable_data, event_activity_model, limitation)]
        },
        {
            "rule": "has_all_constraints('上行晚点约束', '上行中断约束', '下行限速约束', '通用约束') and len(constraints_list) == 4",
            "action": lambda: [unit.up_delay_interrupt_model(timetable_data, event_activity_model, interrupt, upside_delay_data),
                               unit.down_limitation_model(timetable_data, event_activity_model, limitation)]
        },
        {
            "rule": "has_all_constraints('上行晚点约束', '上行限速约束', '上行中断约束', '下行限速约束', '通用约束') and len(constraints_list) == 5",
            "action": lambda: [unit.up_delay_delay_limitation_interrupt_model(timetable_data, event_activity_model, interrupt, limitation, upside_delay_data),
                               unit.down_limitation_model(timetable_data, event_activity_model, limitation)]
        },
        {
            "rule": "has_all_constraints('下行晚点约束', '下行限速约束', '通用约束') and len(constraints_list) == 3",
            "action": lambda: [unit.down_delay_limitation_model(timetable_data, event_activity_model, limitation, downside_delay_data),
                               unit.ajusted_up_timetable()]
        }
    ]

    # 执行规则
    for rule_info in rules:     
        compiled_rule = Rule(rule_info["rule"], context)
        if compiled_rule.matches():
            rule_info["action"]()


if __name__ == '__main__':
    start = time.time()
    main()
    end = time.time()
    print("运行时间：", end - start, "秒")

