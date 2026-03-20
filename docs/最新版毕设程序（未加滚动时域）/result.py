import pandas as pd
import os
from datetime import datetime

def time_to_minutes(t_str):
    """精确处理时间格式（支持HH:MM:SS和HH:MM）"""
    try:
        if pd.isnull(t_str) or t_str.strip() == '':
            return 0
        parts = t_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 60 + m + round(s/60)  # 秒转分钟（四舍五入）
    except Exception as e:
        print(f"时间转换错误: {t_str} - {str(e)}")
        return 0

def analyze_timetable(plan_path, adjusted_path):
    # 读取数据
    plan_df = pd.read_excel(plan_path, sheet_name='Sheet1')
    adjusted_df = pd.read_excel(adjusted_path, sheet_name='Sheet1')

    # 转换时间列
    time_cols = ['arrival_time', 'departure_time']
    for df in [plan_df, adjusted_df]:
        for col in time_cols:
            df[f'{col}_min'] = df[col].astype(str).apply(time_to_minutes)

    # 找出被取消的列车
    canceled_trains = list(set(plan_df['train_ID']) - set(adjusted_df['train_ID']))

    # 合并数据
    merged_df = pd.merge(
        plan_df[['train_ID', 'station'] + [f'{c}_min' for c in time_cols]],
        adjusted_df[['train_ID', 'station'] + [f'{c}_min' for c in time_cols]],
        on=['train_ID', 'station'],
        suffixes=('_plan', '_adjusted'),
        how='left'
    )

    # 过滤无效数据
    merged_df = merged_df.dropna(subset=[f'{c}_min_adjusted' for c in time_cols])

    # 计算晚点时间（精确到分钟）
    for ttype in ['arrival', 'departure']:
        merged_df[f'{ttype}_late'] = (
            merged_df[f'{ttype}_time_min_adjusted'] - 
            merged_df[f'{ttype}_time_min_plan']
        ).clip(lower=0)
        # 新增总偏差计算（绝对值）
        merged_df[f'{ttype}_deviation'] = abs(
            merged_df[f'{ttype}_time_min_adjusted'] - 
            merged_df[f'{ttype}_time_min_plan']
        )

    # 总晚点时间
    total_late_time = merged_df['arrival_late'].sum() + merged_df['departure_late'].sum()
    
    # 总偏差时间
    total_deviation_time = merged_df['arrival_deviation'].sum() + merged_df['departure_deviation'].sum()

    # 总晚点列车数（至少有一个晚点）
    late_trains = merged_df.groupby('train_ID').apply(
        lambda x: (x['arrival_late'] > 0).any() or (x['departure_late'] > 0).any()
    ).reset_index(name='is_late')
    total_late_train_count = late_trains[late_trains['is_late']].shape[0]
    late_train_list = late_trains[late_trains['is_late']]['train_ID'].tolist()

    # 终点站晚点列车数
    plan_end_stations = plan_df.groupby('train_ID').last().reset_index()[['train_ID', 'station']]
    plan_end_stations.columns = ['train_ID', 'end_station']
    merged_end = pd.merge(merged_df, plan_end_stations, on='train_ID')
    end_station_rows = merged_end[merged_end['station'] == merged_end['end_station']]
    end_late_train_list = end_station_rows[end_station_rows['arrival_late'] > 0]['train_ID'].unique().tolist()
    end_late_count = len(end_late_train_list)

    # 各车站晚点列车数
    station_late = merged_df.groupby('station').apply(
        lambda x: x.loc[(x['arrival_late'] > 0) | (x['departure_late'] > 0), 'train_ID'].unique()
    ).reset_index(name='late_trains')
    station_late['count'] = station_late['late_trains'].apply(len)

    # 各车站总晚点时间
    station_total_late = merged_df.groupby('station').apply(
        lambda x: x['arrival_late'].sum() + x['departure_late'].sum()
    ).reset_index(name='total_late_time')
        # 确定车站顺序
    if '上行' in os.path.basename(adjusted_path):
        station_order = ['徐州东', '枣庄', '滕州东', '曲阜东', '泰安', '济南西']
    else:
        station_order = ['济南西', '泰安', '曲阜东', '滕州东', '枣庄', '徐州东']

    # 排序车站数据
    station_late['station'] = pd.Categorical(station_late['station'], categories=station_order, ordered=True)
    station_late = station_late.sort_values('station')
    
    station_total_late['station'] = pd.Categorical(station_total_late['station'], categories=station_order, ordered=True)
    station_total_late = station_total_late.sort_values('station')

    # 输出结果
    print(f"1. 总晚点时间: {total_late_time} 分钟")
    print(f"2. 总偏差时间: {total_deviation_time} 分钟") 
    print(f"\n3. 总晚点列车数: {total_late_train_count}")
    print("晚点列车列表:", late_train_list)
    print(f"\n终点站晚点列车数: {end_late_count}")
    print("终点站晚点列车列表:", end_late_train_list)
    print("\n4. 各车站晚点列车数:")
    for _, row in station_late.iterrows():
        print(f"车站 {row['station']}: {row['count']} 列, 晚点列车: {row['late_trains']}")
    print("\n5. 各车站总晚点时间:")
    for _, row in station_total_late.iterrows():
        print(f"车站 {row['station']}: {row['total_late_time']} 分钟")
    print(f"\n6. 取消的列车总数: {len(canceled_trains)}")
    print("取消的列车列表:", canceled_trains)

    # 生成动态文件名
    base_name = os.path.splitext(os.path.basename(adjusted_path))[0]
    output_path = f"{base_name}_分析结果_{datetime.now().strftime('%Y%m%d%H%M')}.xlsx"
    
    # 保存结果
    with pd.ExcelWriter(output_path) as writer:
        pd.DataFrame({'总晚点时间（分钟）': [total_late_time], '总偏差时间（分钟）': [total_deviation_time]}).to_excel(writer, sheet_name='总指标', index=False)
        pd.DataFrame({'总晚点列车数': [total_late_train_count], '晚点列车列表': [late_train_list]}).to_excel(writer, sheet_name='总晚点列车', index=False)
        station_late.to_excel(writer, sheet_name='车站晚点列车数', index=False)
        station_total_late.to_excel(writer, sheet_name='车站总晚点时间', index=False)
        pd.DataFrame({'取消的列车': canceled_trains}).to_excel(writer, sheet_name='取消的列车', index=False)
    return output_path  # 返回结果路径供可视化使用

# 使用示例
plan_path = '上行计划时刻表.xlsx'
adjusted_path = '调整后的上行时刻表.xlsx'
result_path = analyze_timetable(plan_path, adjusted_path)