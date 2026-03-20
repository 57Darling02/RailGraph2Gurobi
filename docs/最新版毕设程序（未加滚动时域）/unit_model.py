from config import Config
import shutil
import timetable_utils as utils
import time

# 上行晚点单元模型
def up_delay_model(timetable_data, event_activity_model, upside_delay_data):
    # 初始化计划时刻表数据
    start1 = time.time()
    timetable_data.load_and_process_upside_data(Config.UP_FILE_PATH, Config.BASE_DATE)
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.upside_train_events,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.upside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    abs_objective = event_activity_model.abs_objective(timetable_data.upside_train_events)
    event_activity_model.add_objective(abs_objective)

    # step4:添加基础约束、晚点约束、偏差解耦约束
    event_activity_model.add_base_constraints(timetable_data.upside_train_events, timetable_data.upside_train_ids,timetable_data.upside_train_origins,timetable_data.upside_train_destinations,timetable_data.upside_train_event_time,timetable_data.upside_train_routes,timetable_data.upside_section_min_running_time,timetable_data.upside_train_stops,timetable_data.upside_station_min_dwell_time,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair,timetable_data.upside_arr_order_single,timetable_data.upside_dep_order_single)
    event_activity_model.add_primary_delay_constraints(upside_delay_data, timetable_data.upside_train_event_time)
    event_activity_model.add_abs_constraints(timetable_data.upside_train_events, timetable_data.upside_train_event_time)

    start2 = time.time()
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()

    # 输出调整后的上行时刻表数据
    start3 = time.time()
    utils.output_data(Config.AJUSTED_UP_FILE_PATH, objective_value, event_start_time)
    start4 = time.time()
    print("上行晚点建模时间：", start2 - start1, "秒")
    print("上行晚点求解时间：", start3 - start2, "秒")
    print("上行晚点输出时间：", start4 - start3, "秒")
# 下行晚点单元模型
def down_delay_model(timetable_data, event_activity_model, downside_delay_data):
    start1 = time.time()
    # 初始化计划时刻表数据
    timetable_data.load_and_process_downside_data(Config.DOWN_FILE_PATH, Config.BASE_DATE)
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.downside_train_events,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.downside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    abs_objective = event_activity_model.abs_objective(timetable_data.downside_train_events)
    event_activity_model.add_objective(abs_objective)

    # step4:添加基础约束、晚点约束、偏差解耦约束
    event_activity_model.add_base_constraints(timetable_data.downside_train_events, timetable_data.downside_train_ids,timetable_data.downside_train_origins,timetable_data.downside_train_destinations,timetable_data.downside_train_event_time,timetable_data.downside_train_routes,timetable_data.downside_section_min_running_time,timetable_data.downside_train_stops,timetable_data.downside_station_min_dwell_time,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair,timetable_data.downside_arr_order_single,timetable_data.downside_dep_order_single)
    event_activity_model.add_primary_delay_constraints(downside_delay_data, timetable_data.downside_train_event_time)
    event_activity_model.add_abs_constraints(timetable_data.downside_train_events, timetable_data.downside_train_event_time)

    start2 = time.time()
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()
    start3 = time.time()
    # 输出调整后的下行时刻表数据
    utils.output_data(Config.AJUSTED_DOWN_FILE_PATH, objective_value, event_start_time)
    start4 = time.time()
    print("下行晚点建模时间：", start2 - start1, "秒")
    print("下行晚点求解时间：", start3 - start2, "秒")
    print("下行晚点输出时间：", start4 - start3, "秒")

       
# 上行限速单元模型
def up_limitation_model(timetable_data, event_activity_model, limitation):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_upside_data(Config.UP_FILE_PATH, Config.BASE_DATE)
    speedLimitedSections, limitedSpeeds, speedLimitedTimes = utils.speed_limitation_scenarios(limitation) 

    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.upside_train_events,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.upside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    abs_objective = event_activity_model.abs_objective(timetable_data.upside_train_events)
    event_activity_model.add_objective(abs_objective)

    # step4:添加基础约束、偏差解耦约束、限速约束
    event_activity_model.add_base_constraints(timetable_data.upside_train_events, timetable_data.upside_train_ids,timetable_data.upside_train_origins,timetable_data.upside_train_destinations,timetable_data.upside_train_event_time,timetable_data.upside_train_routes,timetable_data.upside_section_min_running_time,timetable_data.upside_train_stops,timetable_data.upside_station_min_dwell_time,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair,timetable_data.upside_arr_order_single,timetable_data.upside_dep_order_single)
    event_activity_model.add_abs_constraints(timetable_data.upside_train_events, timetable_data.upside_train_event_time)
    event_activity_model.add_speed_limitation_constraints(speedLimitedSections, limitedSpeeds, speedLimitedTimes, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
        
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()
   
    # 输出调整后的上行时刻表数据
    utils.output_data(Config.AJUSTED_UP_FILE_PATH, objective_value, event_start_time)

# 下行限速单元模型
def down_limitation_model(timetable_data, event_activity_model, limitation):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_downside_data(Config.DOWN_FILE_PATH, Config.BASE_DATE)
    speedLimitedSections, limitedSpeeds, speedLimitedTimes = utils.speed_limitation_scenarios(limitation)        
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.downside_train_events,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.downside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    abs_objective = event_activity_model.abs_objective(timetable_data.downside_train_events)
    event_activity_model.add_objective(abs_objective)

    # step4:添加基础约束、偏差解耦约束、限速约束
    event_activity_model.add_base_constraints(timetable_data.downside_train_events,timetable_data.downside_train_ids,timetable_data.downside_train_origins,timetable_data.downside_train_destinations,timetable_data.downside_train_event_time,timetable_data.downside_train_routes,timetable_data.downside_section_min_running_time,timetable_data.downside_train_stops,timetable_data.downside_station_min_dwell_time,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair,timetable_data.downside_arr_order_single,timetable_data.downside_dep_order_single)
    event_activity_model.add_abs_constraints(timetable_data.downside_train_events, timetable_data.downside_train_event_time)
    event_activity_model.add_speed_limitation_constraints(speedLimitedSections, limitedSpeeds, speedLimitedTimes, timetable_data.downside_train_event_time, timetable_data.downside_train_ids, timetable_data.downside_train_routes)
        
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()
   
    # 输出调整后的下行时刻表数据
    utils.output_data(Config.AJUSTED_DOWN_FILE_PATH, objective_value, event_start_time)

# 上行中断单元模型
def up_interrupt_model(timetable_data, event_activity_model, interrupt):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_upside_data(Config.UP_FILE_PATH, Config.BASE_DATE)
    interval_interrupt_section, interval_interrupt_time = utils.initialize_interval_interrupt_scenarios(interrupt)
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.upside_train_events,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.upside_train_events)
    #event_activity_model.initialize_cancellation_variables(timetable_data.upside_train_events)

    # step3:目标函数——计划与调整后的偏差最小+取消列车数最少
    abs = event_activity_model.abs_objective(timetable_data.upside_train_events)
    #cal_delay = event_activity_model.cal_delay_objective(timetable_data.upside_train_events)
    #cancellation = event_activity_model.cancellation_objective(timetable_data.upside_train_events)
    #event_activity_model.add_objective(cal_delay + cancellation)
    event_activity_model.add_objective(abs)


    # step4:添加基础约束、偏差解耦约束、中断约束
    event_activity_model.add_base_constraints(timetable_data.upside_train_events, timetable_data.upside_train_ids,timetable_data.upside_train_origins,timetable_data.upside_train_destinations,timetable_data.upside_train_event_time,timetable_data.upside_train_routes,timetable_data.upside_section_min_running_time,timetable_data.upside_train_stops,timetable_data.upside_station_min_dwell_time,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair,timetable_data.upside_arr_order_single,timetable_data.upside_dep_order_single)
    event_activity_model.add_abs_constraints(timetable_data.upside_train_events, timetable_data.upside_train_event_time)
    event_activity_model.add_interval_interrupt_constraints(interval_interrupt_section, interval_interrupt_time, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
    #event_activity_model.add_cancellation_constraints(timetable_data.upside_train_ids, timetable_data.upside_train_origins, timetable_data.upside_train_stops, timetable_data.upside_train_event_time, timetable_data.upside_train_routes)
    
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()
        
    # 输出调整后的上行时刻表数据
    utils.output_data(Config.AJUSTED_UP_FILE_PATH, objective_value, event_start_time)

# 下行中断单元模型
def down_interrupt_model(timetable_data, event_activity_model, interrupt):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_downside_data(Config.DOWN_FILE_PATH, Config.BASE_DATE)
    interval_interrupt_section, interval_interrupt_time = utils.initialize_interval_interrupt_scenarios(interrupt)

    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.downside_train_events,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.downside_train_events)
    event_activity_model.initialize_cancellation_variables(timetable_data.downside_train_events)

    # step3:目标函数——计划与调整后的偏差最小+取消列车数最少
    #abs = event_activity_model.abs_objective(timetable_data.downside_train_events)
    cal_delay = event_activity_model.cal_delay_objective(timetable_data.downside_train_events)
    cancellation = event_activity_model.cancellation_objective(timetable_data.downside_train_events)
    event_activity_model.add_objective(cal_delay + cancellation)

    # step4:添加基础约束、偏差解耦约束、中断约束
    event_activity_model.add_base_constraints(timetable_data.downside_train_events, timetable_data.downside_train_ids,timetable_data.downside_train_origins,timetable_data.downside_train_destinations,timetable_data.downside_train_event_time,timetable_data.downside_train_routes,timetable_data.downside_section_min_running_time,timetable_data.downside_train_stops,timetable_data.downside_station_min_dwell_time,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair,timetable_data.downside_arr_order_single,timetable_data.downside_dep_order_single)
    event_activity_model.add_abs_constraints(timetable_data.downside_train_events, timetable_data.downside_train_event_time)
    event_activity_model.add_interval_interrupt_constraints(interval_interrupt_section, interval_interrupt_time, timetable_data.downside_train_event_time, timetable_data.downside_train_ids)
    event_activity_model.add_cancellation_constraints(timetable_data.downside_train_ids, timetable_data.downside_train_origins, timetable_data.downside_train_stops, timetable_data.downside_train_event_time, timetable_data.downside_train_routes)
    
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()

    # 输出调整后的上行时刻表数据
    utils.output_data(Config.AJUSTED_DOWN_FILE_PATH, objective_value, event_start_time)

# 上行晚点+限速
def up_delay_limitation_model(timetable_data, event_activity_model, upside_delay_data,limitation):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_upside_data(Config.UP_FILE_PATH, Config.BASE_DATE)
    speedLimitedSections, limitedSpeeds, speedLimitedTimes = utils.speed_limitation_scenarios(limitation) 
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.upside_train_events,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.upside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    abs_objective = event_activity_model.abs_objective(timetable_data.upside_train_events)
    #delay_objective = event_activity_model.delay_objective(timetable_data.upside_train_events)
    event_activity_model.add_objective(abs_objective)

    # step4:添加基础约束、晚点约束、偏差解耦约束
    event_activity_model.add_base_constraints(timetable_data.upside_train_events, timetable_data.upside_train_ids,timetable_data.upside_train_origins,timetable_data.upside_train_destinations,timetable_data.upside_train_event_time,timetable_data.upside_train_routes,timetable_data.upside_section_min_running_time,timetable_data.upside_train_stops,timetable_data.upside_station_min_dwell_time,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair,timetable_data.upside_arr_order_single,timetable_data.upside_dep_order_single)
    event_activity_model.add_primary_delay_constraints(upside_delay_data, timetable_data.upside_train_event_time)
    event_activity_model.add_abs_constraints(timetable_data.upside_train_events, timetable_data.upside_train_event_time)
    event_activity_model.add_speed_limitation_constraints(speedLimitedSections, limitedSpeeds, speedLimitedTimes, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
        

    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()

    # 输出调整后的上行时刻表数据
    utils.output_data(Config.AJUSTED_UP_FILE_PATH, objective_value, event_start_time)    

# 上行限速+中断
def up_limitation_interrupt_model(timetable_data, event_activity_model, interrupt, limitation):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_upside_data(Config.UP_FILE_PATH, Config.BASE_DATE)

    interval_interrupt_section, interval_interrupt_time = utils.initialize_interval_interrupt_scenarios(interrupt)    
    speedLimitedSections, limitedSpeeds, speedLimitedTimes = utils.speed_limitation_scenarios(limitation)
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.upside_train_events,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.upside_train_events)
    event_activity_model.initialize_cancellation_variables(timetable_data.upside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    #abs_objective = event_activity_model.abs_objective(timetable_data.upside_train_events)
    #delay_objective = event_activity_model.delay_objective(timetable_data.upside_train_events)
    cal_delay = event_activity_model.cal_delay_objective(timetable_data.upside_train_events)
    cancellation = event_activity_model.cancellation_objective(timetable_data.upside_train_events)
    event_activity_model.add_objective(cal_delay + cancellation)
    #event_activity_model.add_objective(delay_objective)

    # step4:添加基础约束、晚点约束、偏差解耦约束
    event_activity_model.add_base_constraints(timetable_data.upside_train_events, timetable_data.upside_train_ids,timetable_data.upside_train_origins,timetable_data.upside_train_destinations,timetable_data.upside_train_event_time,timetable_data.upside_train_routes,timetable_data.upside_section_min_running_time,timetable_data.upside_train_stops,timetable_data.upside_station_min_dwell_time,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair,timetable_data.upside_arr_order_single,timetable_data.upside_dep_order_single)
    #event_activity_model.add_primary_delay_constraints(upside_delay_data, timetable_data.upside_train_event_time)
    event_activity_model.add_abs_constraints(timetable_data.upside_train_events, timetable_data.upside_train_event_time)
    event_activity_model.add_speed_limitation_constraints(speedLimitedSections, limitedSpeeds, speedLimitedTimes, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
    event_activity_model.add_interval_interrupt_constraints(interval_interrupt_section, interval_interrupt_time, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
    event_activity_model.add_cancellation_constraints(timetable_data.upside_train_ids, timetable_data.upside_train_origins, timetable_data.upside_train_stops, timetable_data.upside_train_event_time, timetable_data.upside_train_routes)
        
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()

    # 输出调整后的上行时刻表数据
    utils.output_data(Config.AJUSTED_UP_FILE_PATH, objective_value, event_start_time)    

# 下行晚点+限速单元模型
def down_delay_limitation_model(timetable_data, event_activity_model, limitation, downside_delay_data):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_downside_data(Config.DOWN_FILE_PATH, Config.BASE_DATE)
    speedLimitedSections, limitedSpeeds, speedLimitedTimes = utils.speed_limitation_scenarios(limitation)        
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.downside_train_events,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.downside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    abs_objective = event_activity_model.abs_objective(timetable_data.downside_train_events)
    event_activity_model.add_objective(abs_objective)

    # step4:添加基础约束、偏差解耦约束、限速约束
    event_activity_model.add_base_constraints(timetable_data.downside_train_events,timetable_data.downside_train_ids,timetable_data.downside_train_origins,timetable_data.downside_train_destinations,timetable_data.downside_train_event_time,timetable_data.downside_train_routes,timetable_data.downside_section_min_running_time,timetable_data.downside_train_stops,timetable_data.downside_station_min_dwell_time,timetable_data.downside_arr_order_pair,timetable_data.downside_dep_order_pair,timetable_data.downside_arr_order_single,timetable_data.downside_dep_order_single)
    event_activity_model.add_abs_constraints(timetable_data.downside_train_events, timetable_data.downside_train_event_time)
    event_activity_model.add_speed_limitation_constraints(speedLimitedSections, limitedSpeeds, speedLimitedTimes, timetable_data.downside_train_event_time, timetable_data.downside_train_ids, timetable_data.downside_train_routes)
    event_activity_model.add_primary_delay_constraints(downside_delay_data, timetable_data.downside_train_event_time)
        
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()
   
    # 输出调整后的下行时刻表数据
    utils.output_data(Config.AJUSTED_DOWN_FILE_PATH, objective_value, event_start_time)

# 上行晚点+中断
def up_delay_interrupt_model(timetable_data, event_activity_model, interrupt, upside_delay_data):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_upside_data(Config.UP_FILE_PATH, Config.BASE_DATE)
    interval_interrupt_section, interval_interrupt_time = utils.initialize_interval_interrupt_scenarios(interrupt)    
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.upside_train_events,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.upside_train_events)
    event_activity_model.initialize_cancellation_variables(timetable_data.upside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    #abs_objective = event_activity_model.abs_objective(timetable_data.upside_train_events)
    #delay_objective = event_activity_model.delay_objective(timetable_data.upside_train_events)
    cal_delay = event_activity_model.cal_delay_objective(timetable_data.upside_train_events)
    cancellation = event_activity_model.cancellation_objective(timetable_data.upside_train_events)
    event_activity_model.add_objective(cal_delay + cancellation)
    #event_activity_model.add_objective(delay_objective)

    # step4:添加基础约束、晚点约束、偏差解耦约束
    event_activity_model.add_base_constraints(timetable_data.upside_train_events, timetable_data.upside_train_ids,timetable_data.upside_train_origins,timetable_data.upside_train_destinations,timetable_data.upside_train_event_time,timetable_data.upside_train_routes,timetable_data.upside_section_min_running_time,timetable_data.upside_train_stops,timetable_data.upside_station_min_dwell_time,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair,timetable_data.upside_arr_order_single,timetable_data.upside_dep_order_single)
    event_activity_model.add_primary_delay_constraints(upside_delay_data, timetable_data.upside_train_event_time)
    event_activity_model.add_abs_constraints(timetable_data.upside_train_events, timetable_data.upside_train_event_time)
    event_activity_model.add_interval_interrupt_constraints(interval_interrupt_section, interval_interrupt_time, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
    event_activity_model.add_cancellation_constraints(timetable_data.upside_train_ids, timetable_data.upside_train_origins, timetable_data.upside_train_stops, timetable_data.upside_train_event_time, timetable_data.upside_train_routes)
        
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()

    # 输出调整后的上行时刻表数据
    utils.output_data(Config.AJUSTED_UP_FILE_PATH, objective_value, event_start_time)

# 上行晚点+限速+中断
def up_delay_delay_limitation_interrupt_model(timetable_data, event_activity_model, interrupt, limitation, upside_delay_data):
    # 初始化计划时刻表数据
    timetable_data.load_and_process_upside_data(Config.UP_FILE_PATH, Config.BASE_DATE)

    interval_interrupt_section, interval_interrupt_time = utils.initialize_interval_interrupt_scenarios(interrupt)    
    speedLimitedSections, limitedSpeeds, speedLimitedTimes = utils.speed_limitation_scenarios(limitation)
        
    # step1:创建模型
    event_activity_model.create_modle()

    # step2:决策变量（到发时刻、到发顺序、晚点时间、偏差）
    event_activity_model.initialize_base_variables(timetable_data.upside_train_events,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair)
    event_activity_model.initialize_abs_variables(timetable_data.upside_train_events)
    event_activity_model.initialize_cancellation_variables(timetable_data.upside_train_events)

    # step3:目标函数——计划与调整后的偏差最小
    #abs_objective = event_activity_model.abs_objective(timetable_data.upside_train_events)
    #delay_objective = event_activity_model.delay_objective(timetable_data.upside_train_events)
    cal_delay = event_activity_model.cal_delay_objective(timetable_data.upside_train_events)
    cancellation = event_activity_model.cancellation_objective(timetable_data.upside_train_events)
    event_activity_model.add_objective(cal_delay + cancellation)
    #event_activity_model.add_objective(delay_objective)

    # step4:添加基础约束、晚点约束、偏差解耦约束
    event_activity_model.add_base_constraints(timetable_data.upside_train_events, timetable_data.upside_train_ids,timetable_data.upside_train_origins,timetable_data.upside_train_destinations,timetable_data.upside_train_event_time,timetable_data.upside_train_routes,timetable_data.upside_section_min_running_time,timetable_data.upside_train_stops,timetable_data.upside_station_min_dwell_time,timetable_data.upside_arr_order_pair,timetable_data.upside_dep_order_pair,timetable_data.upside_arr_order_single,timetable_data.upside_dep_order_single)
    event_activity_model.add_primary_delay_constraints(upside_delay_data, timetable_data.upside_train_event_time)
    event_activity_model.add_abs_constraints(timetable_data.upside_train_events, timetable_data.upside_train_event_time)
    event_activity_model.add_speed_limitation_constraints(speedLimitedSections, limitedSpeeds, speedLimitedTimes, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
    event_activity_model.add_interval_interrupt_constraints(interval_interrupt_section, interval_interrupt_time, timetable_data.upside_train_event_time, timetable_data.upside_train_ids, timetable_data.upside_train_routes)
    event_activity_model.add_cancellation_constraints(timetable_data.upside_train_ids, timetable_data.upside_train_origins, timetable_data.upside_train_stops, timetable_data.upside_train_event_time, timetable_data.upside_train_routes)
        
    # step5:求解模型(得到目标函数值和调整后的时刻)
    objective_value, event_start_time = event_activity_model.solve()

    # 输出调整后的上行时刻表数据
    utils.output_data(Config.AJUSTED_UP_FILE_PATH, objective_value, event_start_time) 

# 输出不需要调整的上行时刻表
def ajusted_up_timetable():
    output_path = Config.AJUSTED_UP_FILE_PATH
    try:
        shutil.copyfile(Config.UP_FILE_PATH, output_path)
        print(f"上行计划时刻表已成功保存至 {output_path}。")
    except Exception as e:
        print(f"复制文件时出现错误: {e}")  

# 输出不需要调整的下行时刻表
def ajusted_down_timetable():
    output_path = Config.AJUSTED_DOWN_FILE_PATH
    try:
        shutil.copyfile(Config.DOWN_FILE_PATH, output_path)
        print(f"下行计划时刻表已成功保存至 {output_path}。")
    except Exception as e:
        print(f"复制文件时出现错误: {e}")