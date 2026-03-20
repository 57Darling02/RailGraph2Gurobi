class Config:
    UP_FILE_PATH = '上行计划时刻表.xlsx'
    DOWN_FILE_PATH = '下行计划时刻表.xlsx'
    AJUSTED_UP_FILE_PATH = '调整后的上行时刻表.xlsx'
    AJUSTED_DOWN_FILE_PATH = '调整后的下行时刻表.xlsx'
    BASE_DATE = '2024-06-15'
    #晚点信息
    #PRIMARY_DELAY_SCENARIOS = [('G1566', '徐州东', 'dep', 3600)]
    #PRIMARY_DELAY_SCENARIOS = [('G376', '滕州东', 'arr', 1800)]
    #PRIMARY_DELAY_SCENARIOS = [('G130', '曲阜东', 'dep', 3000)]
    #PRIMARY_DELAY_SCENARIOS = [('G2661', '济南西', 'dep', 6000)]
    #PRIMARY_DELAY_SCENARIOS = [('G113', '泰安', 'arr', 2400)]
    PRIMARY_DELAY_SCENARIOS = [('G2661', 'jinanxi', 'dep', 60000),
                               ('G113', 'taian', 'arr', 24000)]
    #PRIMARY_DELAY_SCENARIOS = [('G1566', '徐州东', 'dep', 3600),('G376', '滕州东', 'arr', 1800),('G130', '曲阜东', 'dep', 3000),('G2661', '济南西', 'dep', 6000),('G113', '泰安', 'arr', 2400)]
    
    #降雨
    #PRIMARY_DELAY_SCENARIOS = [('G181', '泰安', 'arr', 1200)]
    #SPEED_LIMITATION_SCENARIOS = {('枣庄', '滕州东'): (2280, (48000, 51600)), ('滕州东', '枣庄'): (2280, (48000, 51600))}
    #SPEED_LIMITATION_SCENARIOS = {('滕州东', '枣庄'): (2280, (48000, 51600))}
    
    #大风（7.50-8.20限速，8.20-8.50中断）
    #PRIMARY_DELAY_SCENARIOS = [('G2661', '济南西', 'dep', 3600)]
    #SPEED_LIMITATION_SCENARIOS = {('滕州东', '曲阜东'): (1140, (28200, 30000))}
    #INTERVAL_INTERRUPT_SCENARIOS = {('滕州东', '曲阜东'): (30000, 31800)}

    # 接触网挂异物
    #PRIMARY_DELAY_SCENARIOS = [('G16', '滕州东', 'arr', 1200)]
    #INTERVAL_INTERRUPT_SCENARIOS = {('曲阜东', '泰安'): (56400,58200)}
    #SPEED_LIMITATION_SCENARIOS = {('泰安', '曲阜东'): (900, (56400,58200))}

    # 叠加场景
    #PRIMARY_DELAY_SCENARIOS = [('G110', '滕州东', 'dep', 1200)]
    #INTERVAL_INTERRUPT_SCENARIOS = {('泰安', '济南西'): (37800, 39600)}
    #SPEED_LIMITATION_SCENARIOS = {('济南西', '泰安'): (360, (37800, 39600)), ('徐州东', '枣庄'): (480, (39000, 42600))}
    #PRIMARY_DELAY_SCENARIOS = []
    SPEED_LIMITATION_SCENARIOS = {}
    INTERVAL_INTERRUPT_SCENARIOS = {}