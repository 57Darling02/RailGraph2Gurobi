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
        #self.model = gp.Model('timetable_rescheduling')
        # self.model.setParam('MIPGap', 0.01)
        # self.model.setParam('Method', 0)  # 0=原始单纯形法，1=对偶单纯形法
        # self.model.setParam('NoRelHeurTime', 80)  # 0=原始单纯形法，1=对偶单纯形法

        self.model = gp.Model("large_problem.lp")


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



  