import gurobipy as gp
from gurobipy import GRB
import math
import timetable_utils as utils

class EventActivityModel:
    def __init__(self):
       self.model = None
       self.event_start_time = None
       self.arr_order = None
       self.dep_order = None
       self.delay = None
       self.abs_delay = None
       self.cancellation = None
       self.calDelays = None
       self.arr_arr_headway = 180
       self.dep_dep_headway = 180
       self.toleranceDelay = 2*3600

    # step1:创建模型
    def create_modle(self):
        self.model = gp.Model('timetable_rescheduling')
        # self.model.setParam('MIPGap', 0.01)
        # self.model.setParam('Method', 0)  # 0=原始单纯形法，1=对偶单纯形法
        # self.model.setParam('NoRelHeurTime', 80)  # 0=原始单纯形法，1=对偶单纯形法



        # self.model.setParam('Cuts', 3)  # 0=关闭所有割平面
        self.model.setParam('Heuristics', 0)  # 0=关闭启发式（0-1之间，0.05表示默认）
        # self.model.setParam('PumpPasses', 10)  # 可行性泵迭代次数（默认0=自动）


    # step2-1:基础决策变量（到发时刻、到发顺序、晚点时间）
    def initialize_base_variables(self, train_events, arr_order_pair, dep_order_pair):
        # 事件发生时刻（到发时刻）
        self.event_start_time = self.model.addVars(train_events, lb=0, ub=86400 * 2, vtype=GRB.INTEGER, name='event_start_time')
        # 事件发生顺序
        self.arr_order = self.model.addVars(arr_order_pair, lb=0, ub=1, vtype=GRB.BINARY, name='arr_order')
        self.dep_order = self.model.addVars(dep_order_pair, lb=0, ub=1, vtype=GRB.BINARY, name='dep_order')
        # 晚点时间
        self.delay = self.model.addVars(train_events, lb=-86400, ub=86400*2, vtype=GRB.INTEGER, name='sum_delay')
    
    # step2-2:偏差决策变量（计划与调整后的偏差）
    def initialize_abs_variables(self, train_events):    
        self.abs_delay = self.model.addVars(train_events, lb=0, ub=86400*2, vtype=GRB.INTEGER, name='abs_delay') 

    # step2-3:取消列车数与取消惩罚时间决策变量
    def initialize_cancellation_variables(self, train_events):
        # 取消列车数
        self.cancellation = self.model.addVars(train_events, lb=0, ub=1, vtype=GRB.BINARY, name='cancellation')
        # 取消列车的惩罚时间
        self.calDelays = self.model.addVars(train_events, lb=0, ub=86400, vtype=GRB.INTEGER, name='cal_delays')

    # step3:添加目标函数
    def add_objective(self,objective_value):
        self.model.setObjective(objective_value, GRB.MINIMIZE)

    # step3-1:目标函数——总晚点时间
    def delay_objective(self, train_events): 
        obj_delay = gp.quicksum(self.delay[e] for e in train_events)
        return obj_delay

    # step3-2:目标函数——计划与调整后的偏差
    def abs_objective(self, train_events): 
        obj_abs_delay = gp.quicksum(self.abs_delay[e] for e in train_events)
        return obj_abs_delay

    # step3-3:目标函数——包含取消决策的计划与调整后的偏差最小
    def cal_delay_objective(self, train_events): 
        obj_calDelays = gp.quicksum(self.calDelays[e] for e in train_events)
        return obj_calDelays

    # step3-4:目标函数——取消列车数
    def cancellation_objective(self, train_events):   
        obj_cancellation = gp.quicksum(1000*self.cancellation[e] for e in train_events)
        return obj_cancellation

    # step4-1:基础约束
    def add_base_constraints(self, train_events, train_ids, train_origins, train_destinations, train_event_time, train_routes, section_min_running_time, train_stops, station_min_dwell_time, arr_order_pair, dep_order_pair, arr_order_single, dep_order_single):
        self.delay_constraints(train_events, train_event_time)
        # 始发站到达约束
        self.origin_arrival_constraints(train_ids, train_event_time)
        # 不能早于计划发车时刻发车
        self.departure_time_constraints(train_ids, train_origins, train_stops, train_event_time)
        # 逻辑约束（出发时刻>到达时刻）
        self.logical_constraints(train_ids, train_routes)
        # 列车最小停站时间约束
        self.train_dwell_time_constraints(train_ids, train_stops, station_min_dwell_time)
        # 区间最小运行时分约束
        self.minimum_running_time_constraints(train_ids, train_routes, section_min_running_time)
        # 到达间隔约束
        self.arr_arr_headway_constraints(arr_order_pair, train_origins, train_event_time)
        # 出发间隔约束
        self.dep_dep_headway_constraints(dep_order_pair, train_destinations, train_event_time)   
        # 到达顺序
        self.arr_order_0_1_constraints(arr_order_single) 
        # 出发顺序
        self.dep_order_0_1_constraints(dep_order_single)
        # 到发顺序
        self.dep_arr_order_constraints(arr_order_pair, dep_order_pair, train_origins, train_routes)
    
    # step4-2:晚点约束
    def add_primary_delay_constraints(self, delay_data, train_event_time):
        for e in delay_data.keys():    
            self.model.addConstr(self.event_start_time[e] - train_event_time[e] >= delay_data[e], name='event_primary_delay_{}_{}_{}'.format(e[0], e[1], e[2]))

    # step4-3:限速约束
    def add_speed_limitation_constraints(self, speedLimitedSections, limitedSpeeds, speedLimitedTimes, train_event_time, train_ids, train_routes):
        trainIdSet = train_ids
        for i in range(len(speedLimitedSections)):
            section = speedLimitedSections[i]
            speedLimitedTime = speedLimitedTimes[i]
            limitedSpeed = limitedSpeeds[i]
            traverseSectionTrainIds = utils.getTrainIdsTraverseSection(section, train_ids, train_routes)
            for tr in trainIdSet:
                if tr not in traverseSectionTrainIds: continue
                start_s = section[0]
                end_s = section[1]
                e_start_s = (tr, start_s, 'dep')
                e_end_s = (tr, end_s, 'arr')
                if (train_event_time[e_end_s]-speedLimitedTime[0] > 0) and (speedLimitedTime[1] - train_event_time[e_start_s] > 0):
                    e1 = (tr, section[0], 'dep')
                    e2 = (tr, section[1], 'arr')
                    self.model.addConstr(self.event_start_time[e2] - self.event_start_time[e1] >= (train_event_time[e2] - train_event_time[e1]) + limitedSpeed, name='speed_limited_{}_{}_{}'.format(tr,section[0],section[1]))

    # step4-4:中断约束
    
    def add_interval_interrupt_constraints(self, interval_interrupt_section, interval_interrupt_time, train_event_time, train_ids, train_routes):
        trainEventPlanTime = train_event_time
        # 遍历每个区段及其对应的中断时间
        for section, (start, end) in zip(interval_interrupt_section, interval_interrupt_time):
            dep_station = section[0]
            arr_station = section[1]
            # 获取经过该区段的列车ID
            traverse_train_ids = utils.getTrainIdsTraverseSection(section, train_ids, train_routes)
            for tr in traverse_train_ids:
                if (trainEventPlanTime[tr, dep_station, 'dep'] < end) and (start < trainEventPlanTime[tr, arr_station, 'arr']):
                    self.model.addConstr(self.event_start_time[tr, dep_station, 'dep'] >= end)
                    self.model.addConstr(self.event_start_time[tr, arr_station, 'arr'] >= end)

    # step4-5:目标函数为计划与调整后的偏差解耦约束
    def add_abs_constraints(self, train_events, train_event_time):
        for e in train_events:
            self.model.addConstr(self.delay[e] == self.event_start_time[e]-train_event_time[e], name='event_delay_{}_{}_{}'.format(e[0],e[1],e[2]))
            self.model.addConstr(self.abs_delay[e] >= self.delay[e], name='event_abs_delay_bound0_{}_{}_{}'.format(e[0],e[1],e[2]))
            self.model.addConstr(self.abs_delay[e] >= -self.delay[e], name='event_abs_delay_bound1_{}_{}_{}'.format(e[0],e[1],e[2]))  
            self.model.addConstr(self.abs_delay[e] >= 0, name='event_abs_delay_bound1_{}_{}_{}'.format(e[0],e[1],e[2]))

    # step4-6：加入取消决策后，需要补充的约束
    def add_cancellation_constraints(self, train_ids, train_origins, train_stops, train_event_time, train_routes):
        self.cal_departure_time_constraints(train_ids, train_origins, train_stops, train_event_time)
        self.origin_toleranceDelay_constraints(train_ids, train_origins)
        self.cancellation_constraints(train_ids, train_origins, train_routes)
        self.cancellation_delay_constraints(train_ids, train_routes)

    def load_sol_simple_format(self, sol_file_path):
        with open(sol_file_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 2:
                    continue  # 跳过格式不对行
                var_name, var_value_str = parts
                try:
                    var_value = float(var_value_str)
                except ValueError:
                    continue  # 如果值解析错误 跳过

                var = self.model.getVarByName(var_name)
                if var is not None:
                    var.start = var_value
                else:
                    print(f"Warning: Variable '{var_name}' not found in model.")

    # step5:求解模型
    def solve(self):


        self.model.write("large_problem.lp")
        self.model.update()
        self.load_sol_simple_format("solution3.sol")
        self.model.update()

        self.model.optimize()
        objective_value = None
        event_start_time = None
        if self.model.status == GRB.OPTIMAL:
            self.model.write("solution3.sol")
            objective_value = self.model.objVal
            event_start_time = self.model.getAttr('x', self.event_start_time)
        else:
            if self.model.status == GRB.INFEASIBLE:
                # 分析不可行原因
                self.model.computeIIS()
                self.model.write("model.ilp")  # 生成冲突约束文件
                raise Exception(f"模型不可行，冲突约束已保存至 model.ilp")
            else:
                raise Exception(f"求解失败，状态码: {self.model.status}")
        return objective_value, event_start_time

    def delay_constraints(self, train_events, train_event_time):
        for e in train_events:
            self.model.addConstr(self.delay[e] >= self.event_start_time[e]-train_event_time[e], name='event_delay_{}_{}_{}'.format(e[0],e[1],e[2])) 
            self.model.addConstr(self.delay[e] >= 0, name='event_delay_{}_{}_{}'.format(e[0],e[1],e[2]))        

    # 始发站到达事件约束,与计划到达时刻保持一致
    def origin_arrival_constraints(self, train_ids, train_event_time):
        for tr in train_ids:
            e = (tr, 'station1', 'arr')
            if (e in train_event_time) and (train_event_time[e] is not None) and not math.isnan(train_event_time[e]):
                self.model.addConstr(self.event_start_time[e] == train_event_time[e], name=f"arrival_at_origin_station_{tr}")
            else:
               continue

    # 不允许早发
    def departure_time_constraints(self, train_ids, train_origins, train_stops, train_event_time):
        for tr in train_ids:
            origin = train_origins[tr]
            e = (tr, origin, 'dep')
            self.model.addConstr(self.event_start_time[e] - train_event_time[e] >= 0, name='origin_dep_{}_{}_{}'.format(e[0], e[1], e[2]))
            stops = train_stops[tr]
            for s in stops:
                e = (tr, s, 'dep')
                self.model.addConstr(self.event_start_time[e] - train_event_time[e] >= 0, name='stops_dep_{}_{}_{}'.format(e[0], e[1], e[2]))
    
    # 列车最小停站时间约束
    def train_dwell_time_constraints(self, train_ids, train_stops, station_min_dwell_time):
        for tr in train_ids:
            stops = train_stops[tr]
            for s in stops:
                e1 = (tr, s, 'arr')
                e2 = (tr, s, 'dep')
                # 检查键是否存在
                #self.model.addConstr(self.event_start_time[e2] - self.event_start_time[e1] >= station_min_dwell_time[s], name='station_min_dwell_time_{}_{}'.format(tr,s))    
                self.model.addConstr(self.event_start_time[e2] - self.event_start_time[e1] >= 2*60, name='station_min_dwell_time_{}_{}'.format(tr,s))
                
    # 区间最小运行时分约束
    def minimum_running_time_constraints(self, train_ids, train_routes, section_min_time):
        for tr in train_ids:
            route = train_routes[tr]
            for i in range(len(route)):
                s = route[i]
                j = i + 1
                if j < len(route):
                    s_next = route[j]
                    e1 = (tr, s, 'dep')
                    e2 = (tr, s_next, 'arr')
                    self.model.addConstr(
                        self.event_start_time[e2] - self.event_start_time[e1] >= section_min_time[(s, s_next)],
                        name='minimum_running_time_{}_{}_{}'.format(tr, s, s_next))  

    # 逻辑约束（出发时刻>到达时刻）
    def logical_constraints(self, train_ids, train_routes):
        for tr in train_ids:
            route = train_routes[tr]
            for i in range(len(route) - 1):
                s = route[i]
                e1 = (tr, s, 'arr')
                e2 = (tr, s, 'dep')
                # 检查键是否存在
                self.model.addConstr(self.event_start_time[e2] - self.event_start_time[e1] >= 0, name='dep_greater_than_arr_{}_{}'.format(tr, s))

    # 列车最小到达间隔约束
    def arr_arr_headway_constraints(self, arr_order_pair, train_origins, train_event_time):
        M2 = 100000
        for p in arr_order_pair:
            tr1 = p[0]
            tr2 = p[1]
            s = p[2]
            if (s == train_origins[tr1]) or (s == train_origins[tr2]): 
                continue                     
            etype = p[3]
            e1 = (tr1, s, etype)
            e2 = (tr2, s, etype)
            #if train_event_time[e1] - train_event_time[e2] < self.arr_arr_headway:
                #continue
            self.model.addConstr(self.event_start_time[e2] - self.event_start_time[e1] >= self.arr_arr_headway + (self.arr_order[p] - 1) * M2, name='arr_order0_{}_{}_{}'.format(tr1, tr2, s))
            self.model.addConstr(self.event_start_time[e1] - self.event_start_time[e2] >= self.arr_arr_headway - self.arr_order[p] * M2, name='arr_order1_{}_{}_{}'.format(tr1, tr2, s))
    
    # 列车最小出发间隔约束
    def dep_dep_headway_constraints(self, dep_order_pair, train_destinations, train_event_time):
        M2 = 100000
        for p in dep_order_pair:
            tr1 = p[0]
            tr2 = p[1]
            s = p[2]
            if (s == train_destinations[tr1]) or (s == train_destinations[tr2]): 
                continue  
            etype = p[3]
            e1 = (tr1, s, etype)
            e2 = (tr2, s, etype)
            #if train_event_time[e1] - train_event_time[e2] < self.dep_dep_headway:
                #continue
            self.model.addConstr(self.event_start_time[e2] - self.event_start_time[e1] >= self.dep_dep_headway + (self.dep_order[p] - 1) * M2, name='dep_order0_{}_{}_{}'.format(tr1, tr2, s))
            self.model.addConstr(self.event_start_time[e1] - self.event_start_time[e2] >= self.dep_dep_headway - self.dep_order[p] * M2,name='dep_order1_{}_{}_{}'.format(tr1, tr2, s))
    
    # 列车到达顺序的0-1变量约束
    def arr_order_0_1_constraints(self, arr_order_single):
        for p in arr_order_single:
            tr1 = p[0]
            tr2 = p[1]
            s = p[2]
            etype = p[3]
            p_ = (tr2, tr1, s, etype)
            self.model.addConstr(self.arr_order[p] + self.arr_order[p_] == 1, name='arr_order_certain_{}_{}_{}'.format(tr1,tr2,s))

    # 列车出发顺序的0-1变量约束
    def dep_order_0_1_constraints(self, dep_order_single):
        for p in dep_order_single:
            tr1 = p[0]
            tr2 = p[1]
            s = p[2]
            etype = p[3]
            p_ = (tr2, tr1, s, etype)
            self.model.addConstr(self.dep_order[p] + self.dep_order[p_] == 1, name='dep_order_certain_{}_{}_{}'.format(tr1,tr2,s))        
    
    # 上行两列车上一站出发顺序与下一站到达顺序保持一致
    def dep_arr_order_constraints(self, arr_order_pair, dep_order_pair, train_origins, train_routes):
        for p in arr_order_pair:
            tr1 = p[0]
            tr2 = p[1]
            s = p[2]
            if (s == train_origins[tr1]) or (s == train_origins[tr2]):
                continue
            route1 = train_routes[tr1]
            route2 = train_routes[tr2]
            before_s = s
            sameSubRoute = utils.get_same_sub_route(route1, route2)
            for section in sameSubRoute:
                if s == section[1]:
                    before_s = section[0]
                    break
            if before_s == s:
                continue
            p_ = (tr1, tr2, before_s, 'dep')
            if p_ in dep_order_pair:
                self.model.addConstr(self.arr_order[p] == self.dep_order[p_], name='overtaking_{}_{}_{}_{}'.format(tr1,tr2,before_s,s))
    
    # 加入列车取消决策变量，不能早于计划发车时刻发车
    def cal_departure_time_constraints(self, train_ids, train_origins, train_stops, train_event_time):
        M1 = 86400
        for tr in train_ids:
            origin = train_origins[tr]
            e = (tr, origin, 'dep')
            #if e in delay_data.keys():
                #continue
            self.model.addConstr(self.event_start_time[e] - train_event_time[e] >= self.cancellation[e]*M1, name='origin_dep_{}_{}_{}'.format(e[0],e[1],e[2]))
            stops = train_stops[tr]
            for s in stops:
                e = (tr, s, 'dep')
                #if e in delay_data.keys():
                    #continue
                self.model.addConstr(self.event_start_time[e] - train_event_time[e] >= self.cancellation[e]*M1, name='stops_dep_{}_{}_{}'.format(e[0],e[1],e[2]))    
            
    # 始发站超过晚点阈值，取消列车
    def origin_toleranceDelay_constraints(self, train_ids, train_origins):
        M2 = 100000
        for tr in train_ids:
            origin = train_origins[tr]
            e = (tr, origin, 'dep')
            self.model.addConstr(self.abs_delay[e] - self.toleranceDelay >= (self.cancellation[e]-1)*M2, name='event_tolerance_delay_{}_{}_{}'.format(e[0],e[1],e[2]))    
        
    # 取消策略保持一致
    def cancellation_constraints(self, train_ids, train_origins, train_routes):
        for tr in train_ids:
            origin = train_origins[tr]
            route = train_routes[tr]
            e = (tr, origin, 'dep')
            for s in route:
                e1 = (tr, s, 'arr')
                e2 = (tr, s, 'dep')
                self.model.addConstr(self.cancellation[e1] - self.cancellation[e] == 0, name='event_cancellation_{}_{}_{}'.format(e1[0],e1[1],e1[2]))
                self.model.addConstr(self.cancellation[e2] - self.cancellation[e] == 0, name='event_cancellation_{}_{}_{}'.format(e2[0],e2[1],e2[2]))    

    # 列车取消后，计入的目标值为0
    def cancellation_delay_constraints(self, train_ids, train_routes):
        M3 = 86400*2
        for tr in train_ids:
            route = train_routes[tr]
            types = ['arr', 'dep']
            for s in route:
                for ty in types:
                    e = (tr, s, ty)
                    self.model.addConstr(self.calDelays[e] <= (1-self.cancellation[e])*M3, name='event_calculated_delays_0_{}_{}_{}'.format(e[0],e[1],e[2]))
                    self.model.addConstr(self.calDelays[e] <= self.abs_delay[e], name='event_calculated_delays_1_{}_{}_{}'.format(e[0],e[1],e[2]))
                    self.model.addConstr(self.calDelays[e] >= self.abs_delay[e] - self.cancellation[e]*M3, name='event_calculated_delays_2_{}_{}_{}'.format(e[0],e[1],e[2]))



  