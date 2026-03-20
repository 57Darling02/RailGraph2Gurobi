import timetable_utils as utils
import config
import pandas as pd

class TimetableData:
    # 初始化时刻表数据
    def __init__(self):
        # 初始化上行列车原始数据
        self.upside_initial_planning_events = None      # 上行列车计划事件列表 [('G2', 'Station1', 'arr'), ……, ('G6', 'Station4', 'dep')]
        self.upside_initial_planning_time = None        # 上行列车计划事件时间字典 {('G2', 'Station1', 'arr'): 36000.0, ……, ('G6', 'Station4', 'dep'): 38520.0}
        
        # 初始化上行列车调整后数据
        self.upside_ajustment_timetable = None          # 上行列车调整后时刻表数据

        # 初始化上行列车阶段数据
        self.upside_train_ids = None                    # 上行列车车次号列表 ['G2', 'G4', 'G6']
        self.upside_train_routes = None                 # 上行列车途径车站字典 {'G2': ['Station1', 'Station2', 'Station3', 'Station4'], 'G4': ['Station1', 'Station2', 'Station3', 'Station4'], 'G6': ['Station1', 'Station2', 'Station3', 'Station4']}
        self.upside_train_origins = None                # 上行列车始发站字典 {'G2': 'Station1', 'G4': 'Station1', 'G6': 'Station1'}
        self.upside_train_destinations = None           # 上行列车终点站字典 {'G2': 'Station4', 'G4': 'Station4', 'G6': 'Station4'}
        self.upside_train_stops = None                  # 上行列车停站字典 {'G2': [], 'G4': ['Station2'], 'G6': ['Station3']}
        self.upside_nonstop_stations = None             # 上行列车通过车站字典 {'G2': ['Station1', 'Station2', 'Station3', 'Station4'], 'G4': ['Station1', 'Station3', 'Station4'], 'G6': ['Station1', 'Station2', 'Station4']}
        self.upside_train_events = None                 # 上行列车事件列表 [('G2', 'Station1', 'arr'), ……, ('G6', 'Station4', 'dep')]
        self.upside_train_event_time = None             # 上行列车事件时间字典 {('G2', 'Station1', 'arr'): 36000.0, ……, ('G6', 'Station4', 'dep'): 38520.0}
        self.upside_section_running_time = None         # 上行区间运行时间字典 {('Station1', 'Station2'): [540.0, 600.0, 600.0], ('Station2', 'Station3'): [780.0, 720.0, 780.0], ('Station3', 'Station4'): [540.0, 480.0, 540.0]}
        self.upside_section_min_running_time = None     # 上行区间最小运行时间字典 {('Station1', 'Station2'): 540.0, ('Station2', 'Station3'): 720.0, ('Station3', 'Station4'): 480.0}
        self.upside_train_dwell_time = None             # 上行列车停站时间字典 {('G4', 'Station2'): 120.0, ('G6', 'Station3'): 120.0}
        self.upside_station_dwell_time = None           # 上行车站停站时间字典 {'Station2': [120.0], 'Station3': [120.0]}
        self.upside_station_min_dwell_time = None       # 上行车站最小停站时间字典 {'Station2': 120.0, 'Station3': 120.0}
        self.upside_arr_order_pair = None               # 上行列车到达顺序(包含越行)列表 [('G2', 'G4', 'Station1', 'arr'), ('G4', 'G2', 'Station1', 'arr'),……, ('G6', 'G4', 'Station4', 'arr')]
        self.upside_dep_order_pair = None               # 上行列车出发顺序(包含越行)列表 [('G2', 'G4', 'Station1', 'dep'), ('G4', 'G2', 'Station1', 'dep'),……, ('G6', 'G4', 'Station4', 'dep')]
        self.upside_arr_order_single = None             # 上行列车到达顺序（不含越行）列表 [('G2', 'G4', 'Station1', 'arr'), ('G2', 'G4', 'Station2', 'arr'),……, ('G4', 'G6', 'Station4', 'arr')]
        self.upside_dep_order_single = None             # 上行列车出发顺序（不含越行）列表 [('G2', 'G4', 'Station1', 'dep'), ('G2', 'G4', 'Station2', 'dep'),……, ('G4', 'G6', 'Station4', 'dep')]

        # 初始化下行列车原始数据
        self.downside_initial_planning_events = None      # 下行列车计划事件列表 
        self.downside_initial_planning_time = None        # 下行列车计划事件时间字典
        
        # 初始化下行列车调整后数据
        self.downside_ajustment_timetable = None          # 下行列车调整后时刻表数据

        # 初始化下行列车数据
        self.downside_train_ids = None                  # 下行列车车次号列表 
        self.downside_train_routes = None               # 下行列车途径车站字典
        self.downside_train_origins = None              # 下行列车始发站字典 
        self.downside_train_destinations = None         # 下行列车终点站字典 
        self.downside_train_stops = None                # 下行列车停站字典
        self.downside_nonstop_stations = None           # 下行列车通过车站字典 
        self.downside_train_events = None               # 下行列车事件列表 
        self.downside_train_event_time = None           # 下行列车事件时间字典 
        self.downside_section_running_time = None       # 下行区间运行时间字典          
        self.downside_section_min_running_time = None   # 下行区间最小运行时间字典 
        self.downside_train_dwell_time = None           # 下行列车停站时间字典 
        self.downside_station_dwell_time = None         # 下行车站停站时间字典 
        self.downside_station_min_dwell_time = None     # 下行车站最小停站时间字典 
        self.downside_arr_order_pair = None             # 下行列车到达顺序(包含越行)列表 
        self.downside_dep_order_pair = None             # 下行列车出发顺序(包含越行)列表 
        self.downside_arr_order_single = None           # 下行列车到达顺序（不含越行）列表 
        self.downside_dep_order_single = None           # 下行列车出发顺序（不含越行）列表 
    
    # 处理上行原始计划时刻表数据,仅得到事件及时间字典
    def initial_upside_planning_data(self, up_file_path, base_date):
        data = utils.read_excel(up_file_path)
        base_time = utils.set_base_time(base_date)
        processed_data = utils.convert_time_to_seconds(data, base_time)
        self.upside_initial_planning_events, self.upside_initial_planning_time = self.get_train_event_time(processed_data)
        #print(self.upside_initial_planning_events)
        #print(self.upside_initial_planning_time)

    # 调整后的总时刻表：初始与原始计划时刻表一致，后续用阶段数据覆盖
    def initial_upside_ajustment_data(self):
        self.upside_ajustment_timetable = self.upside_initial_planning_time.copy()

    # 处理下行原始计划时刻表数据,仅得到事件及时间字典
    def initial_downside_planning_data(self, down_file_path, base_date):
        data = utils.read_excel(down_file_path)
        base_time = utils.set_base_time(base_date)
        processed_data = utils.convert_time_to_seconds(data, base_time)
        self.downside_initial_planning_events, self.downside_initial_planning_time = self.get_train_event_time(processed_data)

    # 调整后的总时刻表：初始与原始计划时刻表一致，后续用阶段数据覆盖
    def initial_downside_ajustment_data(self):
        self.downside_ajustment_timetable = self.downside_initial_planning_time.copy()

    # 加载并处理上行时刻表数据
    def load_and_process_upside_data(self, up_file_path, base_date):
        data = utils.read_excel(up_file_path)
        base_time = utils.set_base_time(base_date)
        processed_data = utils.convert_time_to_seconds(data, base_time)
        self.upside_train_ids = self.get_unique_train_ids(processed_data)
        #print(self.upside_train_ids)
        self.upside_train_routes = self.get_train_routes(processed_data, self.upside_train_ids)
        #print(self.upside_train_routes)
        self.upside_train_origins, self.upside_train_destinations = self.get_train_origins_and_destinations(processed_data, self.upside_train_ids)
        #print(self.upside_train_origins)
        #print(self.upside_train_destinations)
        self.upside_train_stops = self.get_train_stops(self.upside_train_ids, processed_data)
        #print(self.upside_train_stops)
        self.upside_nonstop_stations = self.get_train_nonstop_stations(self.upside_train_ids, processed_data)
        #print(self.upside_nonstop_stations)
        self.upside_train_events, self.upside_train_event_time = self.get_train_event_time(processed_data)
        #print(self.upside_train_events)
        #print(self.upside_train_event_time)
        self.upside_section_running_time = self.get_section_running_time(processed_data, self.upside_train_ids)
        #print(self.upside_section_running_time)
        #self.upside_section_min_running_time = {('徐州东', '枣庄'): 660.0, ('枣庄', '滕州东'): 360.0, ('滕州东', '曲阜东'): 540.0, ('曲阜东', '泰安'): 720.0, ('泰安', '济南西'): 600.0}
        self.upside_section_min_running_time = self.get_section_min_time(self.upside_section_running_time)
        #print(self.upside_section_min_running_time)
        self.upside_train_dwell_time = self.get_train_dwell_time(self.upside_train_ids, processed_data)
        #print(self.upside_train_dwell_time)
        self.upside_station_dwell_time = self.get_station_dwell_time(processed_data, self.upside_train_ids)
        #print(self.upside_station_dwell_time)
        self.upside_station_min_dwell_time = self.get_station_min_time(self.upside_station_dwell_time)
        print(self.upside_station_min_dwell_time)
        self.upside_arr_order_pair, self.upside_dep_order_pair, self.upside_arr_order_single, self.upside_dep_order_single = self.get_train_order(self.upside_train_ids, self.upside_train_routes)
        #print(self.upside_arr_order_pair)
        #print(self.upside_dep_order_pair)
        #print(self.upside_arr_order_single)
        #print(self.upside_dep_order_single)

    # 加载并处理下行时刻表数据
    def load_and_process_downside_data(self, down_file_path, base_date):
        data = utils.read_excel(down_file_path)
        base_time = utils.set_base_time(base_date)
        processed_data = utils.convert_time_to_seconds(data, base_time)
        self.downside_train_ids = self.get_unique_train_ids(processed_data)
        #print(self.downside_train_ids)
        self.downside_train_routes = self.get_train_routes(processed_data, self.downside_train_ids)
        #print(self.downside_train_routes)
        self.downside_train_origins, self.downside_train_destinations = self.get_train_origins_and_destinations(processed_data, self.downside_train_ids)
        #print(self.down_train_origins)
        #print(self.down_train_destinations)
        self.downside_train_stops = self.get_train_stops(self.downside_train_ids, processed_data)
        #print(self.train_stops)
        self.downside_train_events, self.downside_train_event_time = self.get_train_event_time(processed_data)
        #print(self.downside_train_events)
        #print(self.downside_train_event_time)
        self.downside_section_running_time = self.get_section_running_time(processed_data, self.downside_train_ids)
        #print(self.downside_section_running_time)
        self.downside_section_min_running_time = self.get_section_min_time(self.downside_section_running_time)
        #print(self.downside_section_min_running_time)
        self.downside_train_dwell_time = self.get_train_dwell_time(self.downside_train_ids, processed_data)
        #print(self.downside_train_dwell_time)
        self.downside_station_dwell_time = self.get_station_dwell_time(processed_data, self.downside_train_ids)
        #print(self.downside_station_dwell_time)
        self.downside_station_min_dwell_time = self.get_station_min_time(self.downside_station_dwell_time)
        print(self.downside_station_min_dwell_time)
        self.downside_arr_order_pair, self.downside_dep_order_pair, self.downside_arr_order_single, self.downside_dep_order_single = self.get_train_order(self.downside_train_ids, self.downside_train_routes)
        #print(self.downside_arr_order_pair)
        #print(self.downside_dep_order_pair)
        #print(self.downside_arr_order_single)
        #print(self.downside_dep_order_single)
    
    # 获取列车车次号
    def get_unique_train_ids(self, timetable):
        return timetable['train_ID'].unique().tolist()           
    
    # 获取列车途径车站
    def get_train_routes(self, timetable, train_ids):
        train_routes = {}
        for train in train_ids:
            train_routes[train] = timetable[timetable['train_ID'] == train]['station'].tolist()
        return train_routes    
    
    # 获取列车起讫点
    def get_train_origins_and_destinations(self, timetable, train_ids):
        origins, destinations = {}, {}
        for train in train_ids:
            train_data = timetable[timetable['train_ID'] == train]
            origins[train] = train_data['station'].iloc[0]
            destinations[train] = train_data['station'].iloc[-1]
        return origins, destinations 
    
    # 获取列车停站
    def get_train_stops(self, train_ids, timetable):
        train_stops = {}
        for train in train_ids:
            stops = timetable[(timetable['train_ID'] == train) & (timetable['arrival_time'] != timetable['departure_time'])]['station'].tolist()
            train_stops[train] = stops
        return train_stops
    
    # 获取列车通过车站
    def get_train_nonstop_stations(self, train_ids, timetable):
        nonstop_stations = {}
        for train in train_ids:
            nonstop_stations[train] = timetable[(timetable['train_ID'] == train) & (timetable['arrival_time'] == timetable['departure_time'])]['station'].tolist()
        return nonstop_stations

    # 列车事件
    def get_train_event_time(self, timetable):
        train_ids = timetable['train_ID'].unique().tolist() 
        events, time = [], {}
        for train in train_ids:
            train_data = timetable[timetable['train_ID'] == train]
            for _, row in train_data.iterrows():
                # 检查到达时间是否存在
                if pd.notna(row['arrival_time']):
                    arr_event = (train, row['station'], 'arr')
                    events.append(arr_event)
                    time[arr_event] = row['arrival_time']
                # 检查出发时间是否存在
                if pd.notna(row['departure_time']):
                    dep_event = (train, row['station'], 'dep')
                    events.append(dep_event)
                    time[dep_event] = row['departure_time']
        return events, time

    # 获取列车区间运行时间
    def get_section_running_time(self, timetable, train_ids):
        section_time = {}
        for train in train_ids:
            train_data = timetable[timetable['train_ID'] == train]
            stations = train_data['station'].tolist()
            departures = train_data['departure_time'].tolist()
            arrivals = train_data['arrival_time'].tolist()
            for i in range(len(stations) - 1):
                section = (stations[i], stations[i + 1])
                run_time = arrivals[i + 1] - departures[i]
                section_time.setdefault(section, []).append(run_time)
        return section_time
    
    # 获取区间最小运行时间
    def get_section_min_time(self, section_time):
        return {section: min(time) for section, time in section_time.items()}    
    
    # 获取列车停站时间
    def get_train_dwell_time(self, train_ids, timetable):
        dwell_time = {}
        for train in train_ids:
            train_data = timetable[timetable['train_ID'] == train]
            for _, row in train_data.iterrows():
                if row['departure_time'] > row['arrival_time']:
                    dwell_time[(train, row['station'])] = row['departure_time'] - row['arrival_time']
        return dwell_time   
    
    # 获取车站停站时间
    def get_station_dwell_time(self, timetable, train_ids):
        station_time = {}
        for train in train_ids:
            train_data = timetable[timetable['train_ID'] == train]
            for _, row in train_data.iterrows():
                if row['departure_time'] > row['arrival_time']:
                    station_time.setdefault(row['station'], []).append(row['departure_time'] - row['arrival_time'])
        return station_time    

    # 获取车站最小停站时间
    def get_station_min_time(self, station_time):
        return {station: min(time) for station, time in station_time.items()} 

    # 获取列车到达、出发顺序对
    def get_train_order(self, train_ids, train_route):
        arr_order_pair = []
        dep_order_pair = []
        arr_order_single = []
        dep_order_single = []

        for i, tr1 in enumerate(train_ids):
            route_of_tr1 = train_route[tr1]
            for tr2 in train_ids[i+1:]:
                route_of_tr2 = train_route[tr2]
                sub_route_pair = utils.get_same_sub_route(route_of_tr1, route_of_tr2)
                stations = set()

                for s, s_next in sub_route_pair:
                    for station in (s, s_next):
                        if station not in stations:
                            stations.add(station)
                            arr_order_pair.extend([(tr1, tr2, station, 'arr'), (tr2, tr1, station, 'arr')])
                            arr_order_single.append((tr1, tr2, station, 'arr'))
                            dep_order_pair.extend([(tr1, tr2, station, 'dep'), (tr2, tr1, station, 'dep')])
                            dep_order_single.append((tr1, tr2, station, 'dep'))
        return arr_order_pair, dep_order_pair, arr_order_single, dep_order_single

if __name__ == '__main__':
    timetable_data = TimetableData()
    timetable_data.load_and_process_upside_data(config.Config.UP_FILE_PATH, config.Config.BASE_DATE)
    timetable_data.load_and_process_downside_data(config.Config.DOWN_FILE_PATH, config.Config.BASE_DATE)