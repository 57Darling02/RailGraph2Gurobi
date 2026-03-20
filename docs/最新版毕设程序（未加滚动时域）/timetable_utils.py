import datetime
import pandas as pd

# 读数据
def read_excel(file_path, sheet_name=0):
    return pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl')

# 设置基准时间
def set_base_time(base_date):
    year, month, day = map(int, base_date.split('-'))
    return datetime.datetime(year, month, day, 0, 0, 0)

# 获取仅晚点场景中最早晚点开始时刻（计划图中最早的起始时间）
def find_earliest_delay_start_time(train_event_time, delay_data):
    plan_event_time = []
    for key in delay_data.keys():
        if key in train_event_time.keys():
            plan_event_time.append(train_event_time[key])
    earliest_delay_start_time = min(plan_event_time)
    return earliest_delay_start_time   

def get_phase_timetable(train_event_time, duration, phase_start_time):
    print("最早晚点开始时刻：", phase_start_time)
    phase_finish_time = phase_start_time + duration
    print("阶段结束时刻：", phase_finish_time)
    affected_trains = set()
    # 识别在时间窗口内有事件的车次
    for key, time in train_event_time.items():
        if phase_start_time <= time <= phase_finish_time:
            affected_trains.add(key[0])
    # 包含这些车次的所有事件（包括窗口外的事件）
    phase_timetable_data = {}
    for key, time in train_event_time.items():
        if key[0] in affected_trains:
            phase_timetable_data[key] = time
    return phase_timetable_data

# 转换时间格式（日期转换为秒数）
def convert_time_to_seconds(data, base_time, time_columns=['arrival_time', 'departure_time']):
    for col in time_columns:
        data[col] = pd.to_datetime(data[col], format='%H:%M:%S')
        data[col] = data[col].apply(lambda x: x.replace(year=base_time.year, month=base_time.month, day=base_time.day))
        data[col] = (data[col] - pd.Timestamp(base_time)).dt.total_seconds()
    return data

# 合并两个字典
def merge_dictionaries(dic1, dic2):
    result = {**dic1}
    for key, value in dic2.items():
        result.setdefault(key, []).extend(value if isinstance(value, list) else [value])
    return result

# 获取相同子路径
def get_same_sub_route(route1, route2):
    same_sub_route = []
    subRoute = []
    for s in route1:
        if s in route2:
            subRoute.append(s)
    for i in range(len(subRoute)):
        s = subRoute[i]
        j = i+1
        if j >= len(subRoute): break
        s_next = subRoute[j]
        indexOfS_R1 = route1.index(s)
        indexOfS_next_R1 = route1.index(s_next)
        indexOfS_R2 = route2.index(s)
        indexOfS_next_R2 = route2.index(s_next)
        if (indexOfS_next_R1-indexOfS_R1 == 1) and (indexOfS_next_R2-indexOfS_R2 == 1):
            same_sub_route.append((s,s_next))
    return same_sub_route

# 仅晚点场景下，上下行晚点数据分离
def separate_up_down_delay(delay):
    upside_data = []
    downside_data = []
    upside_delay_data = {}
    downside_delay_data = {}
    for i in range(len(delay)):
        # 挑出上行晚点信息列表
        if int(delay[i][0][-1]) % 2 == 0:
            upside_data.append(delay[i])
        # 挑出下行晚点信息列表
        else:
            downside_data.append(delay[i])
    # 构建晚点信息字典
    for s in upside_data:
        upside_delay_data[(s[0], s[1], s[2])] = s[3]
    for s in downside_data:
        downside_delay_data[(s[0], s[1], s[2])] = s[3]            
    return upside_delay_data, downside_delay_data  

# 找到阶段数据中发生变化的列车车次号
def find_changed_trains(phase_timetable, event_start_time):
    changed_trains = set()
    for (train_id, station, event), phase_time in phase_timetable.items():
        adjusted_time = event_start_time.get((train_id, station, event))
        if phase_time != adjusted_time:
            changed_trains.add(train_id)
    return list(changed_trains)

# 检查发生变化的列车终点站到达事件是否存在于event_start_time 中
def check_destination_arrival_events(changed_trains, train_destinations, event_start_time):
    incomplete_trains = []
    for train_id in changed_trains:
        destination_arr_event = (train_id, train_destinations[train_id], 'arr')
        if destination_arr_event not in event_start_time.keys():
            incomplete_trains.append(train_id)
    return incomplete_trains

# 在本阶段发生变化且未到达终点站的列车事件，找到这个车次在本阶段在最后一个车站的事件是否晚点
def check_incomplete_last_event(incomplete_trains, phase_timetable, event_start_time):
    # 检测未完成列车的最后事件状态
    new_delay_events = []
    for train_id in incomplete_trains:
        # 获取列车在当前阶段的所有事件
        phase_events = [e for e in phase_timetable if e[0] == train_id]
        if not phase_events:
            continue
        # 找出最后一个事件（按时间排序）
        last_event = max(phase_events, key=lambda e: phase_timetable[e])
        planned_time = phase_timetable[last_event]
        actual_time = event_start_time.get(last_event, planned_time)
                
        # 如果实际时间与计划不一致，记录为新的晚点
        if actual_time != planned_time:
            delay = actual_time - planned_time
            new_delay_events.append({
                        'train_id': train_id,
                        'station': last_event[1],
                        'event_type': last_event[2],
                        'time': delay
                    })
    return new_delay_events

# 找到下一阶段的开始时刻
def find_next_phase_start_time(incomplete_trains, phase_timetable, event_start_time, phase_finish_time):
    next_phase_start_time = phase_finish_time
    for tr in incomplete_trains:
        value = []
        closest_key = None
        for (train_id, station, event), time in event_start_time.items():
            if tr == train_id:
                value.append(time)
        # 如果没有找到该列车的时刻，则跳过该列车
        if not value:
            print(f"警告：列车 {tr} 没有找到任何时刻，跳过该列车")
            continue
        # 找到最接近下一阶段开始时刻的事件时刻
        closest_time = min(value, key=lambda t: abs(t - next_phase_start_time))  # 最接近下一阶段开始时刻的事件时刻
        for key, time in event_start_time.items():
            if time == closest_time and key[0] == tr:  # 如果时间和列车ID匹配
                closest_key = key
                break
        # 如果找到了匹配的事件时刻
        if closest_key:
            # 获取该列车下一站的计划时刻
            planned_time = phase_timetable.get(closest_key, None)

            if planned_time == event_start_time[closest_key]:
                print(f'列车{tr}未影响下一阶段')
            else:
                next_phase_start_time = min(next_phase_start_time, event_start_time[closest_key])
            print(f'列车{tr}的下一阶段开始时刻为{next_phase_start_time}')
        else:
            print(f"警告：列车 {tr} 的最接近时刻没有找到对应的事件键")
    if next_phase_start_time == phase_finish_time:
        next_phase_start_time = None
    return next_phase_start_time

# 输出阶段数据，保存至阶段文件中
def output_phase_data(file_path, phase_timetable_data):
    rows = []
    for (train_id, station, event), time in phase_timetable_data.items():
        # 格式化时间，如果时间为空则留空
        formatted_time = pd.to_datetime(time, unit='s').strftime('%H:%M:%S') if time else ''
        
        if event == 'arr':  # 处理到站事件
            # 记录到站时间，出发时间暂时为空
            rows.append((train_id, station, formatted_time, None))
        elif event == 'dep':  # 处理出发事件
            # 检查是否已有对应的到站记录
            if rows and rows[-1][0] == train_id and rows[-1][1] == station:
                # 如果已经记录了到站事件，更新对应的出发时间
                rows[-1] = (train_id, station, rows[-1][2], formatted_time)
            else:
                # 如果没有到站事件，仅记录出发时间，到站时间为空
                rows.append((train_id, station, None, formatted_time))
    
    # 将数据存储为 DataFrame，并导出到 Excel
    phase_data = pd.DataFrame(rows, columns=['train_ID', 'station', 'arrival_time', 'departure_time'])
    phase_data.to_excel(file_path, index=False)
    print("阶段时刻表已成功保存。")
    
# 仅限速场景输入处理
def speed_limitation_scenarios(limitation):
    sections = list(limitation.keys())
    speedLimitedSections = sections
    limitedSpeeds = []
    speedLimitedTimes = []
    for section in sections:
        situation = limitation.get(section)
        limitedSpeeds.append(situation[0])
        speedLimitedTimes.append(situation[1])
    return speedLimitedSections, limitedSpeeds, speedLimitedTimes

def getTrainIdsTraverseSection(section, train_ids, train_routes):
    trainIdSet = train_ids
    trainRoute = train_routes
    traverseSectionTrainIds = []
    for tr in trainIdSet:
        route = trainRoute[tr]
        i = route.index(section[0])
        j = i+1
        if j >= len(route): continue
        if section[1] == route[j] : 
            traverseSectionTrainIds.append(tr)
    return traverseSectionTrainIds

def initialize_interval_interrupt_scenarios(interval_interrupt_scenarios):
    sections = list(interval_interrupt_scenarios.keys())
    interval_interrupt_time = []
    for section in sections:
        # 从字典中获取该区段对应的时间元组并添加到列表
        time_tuple = interval_interrupt_scenarios.get(section)
        interval_interrupt_time.append(time_tuple) 
    return sections, interval_interrupt_time

def output_data(output_path, objective_value, event_start_time):
    print("目标函数值：", objective_value)
    timetable_data = []
    # 直接遍历调整后的所有事件键
    for e in event_start_time:
        time_val = event_start_time[e]
        if time_val < 86400:
            formatted_time = (
                f"{int(time_val // 3600):02}:"
                f"{int((time_val % 3600) // 60):02}:"
                f"{int(time_val % 60):02}"
            )
            timetable_data.append({
                'train_ID': e[0],
                'station': e[1],
                'etype': e[2],
                'formatted_time': formatted_time
            })
    
    # 生成到发时刻表
    arrival_df = pd.DataFrame([
        {'train_ID': d['train_ID'], 'station': d['station'], 'arrival_time': d['formatted_time']}
        for d in timetable_data if d['etype'] == 'arr'
    ])
    departure_df = pd.DataFrame([
        {'train_ID': d['train_ID'], 'station': d['station'], 'departure_time': d['formatted_time']}
        for d in timetable_data if d['etype'] == 'dep'
    ])
    
    # 合并并保存
    merged_df = pd.merge(
        arrival_df, 
        departure_df, 
        on=['train_ID', 'station'], 
        how='outer'
    )
    merged_df.to_excel(output_path, index=False)
    print(f"全量时刻表已保存至 {output_path}")

