import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import matplotlib.lines as mlines
import matplotlib.dates as mdates


def timetable(file_path_up, file_path_down):
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    df_up = pd.read_excel(file_path_up)
    df_down = pd.read_excel(file_path_down)

    df_up['arrival_time'] = pd.to_datetime(df_up['arrival_time'], format='%H:%M:%S').dt.strftime('%H:%M')
    df_up['departure_time'] = pd.to_datetime(df_up['departure_time'], format='%H:%M:%S').dt.strftime('%H:%M')
    df_down['arrival_time'] = pd.to_datetime(df_down['arrival_time'], format='%H:%M:%S').dt.strftime('%H:%M')
    df_down['departure_time'] = pd.to_datetime(df_down['departure_time'], format='%H:%M:%S').dt.strftime('%H:%M')

    fig, ax = plt.subplots(figsize=(54, 10))

    stations = df_up["station"].unique()
    for station in stations:
        ax.axhline(y=station, color='green', linestyle='--', lw=0.5)
    train_num = 0

    marked_positions_up = []  # 记录上行车次号位置（时间与y坐标）
    marked_positions_down = []  # 记录下行车次号位置（时间与y坐标）

    # 设置位置调整的阈值
    time_threshold = pd.Timedelta(minutes=15)  # 横向时间阈值（如2分钟）

    # 绘制上行运行图及标注车次
    for train in df_up["train_ID"].unique():
        train_num += 1
        train_data = df_up[df_up["train_ID"] == train]
        color = 'red'
        marked_times = set()  # 用于记录已经标注的时间和车站

        # 标注始发站车次
        start_station = train_data.iloc[0]["station"]
        start_time = pd.to_datetime(train_data.iloc[0]["departure_time"], format='%H:%M')
        y_start = stations.tolist().index(start_station)

        # 检查位置重叠，并进行调整
        #while any(abs(start_time - pos[0]) < time_threshold and y_start == pos[1] for pos in marked_positions_up):
        #    y_start -= 0.1  # 向下移动

        marked_positions_up.append((start_time, y_start))

        ax.text(start_time, y_start - 0.2, train, verticalalignment='bottom', horizontalalignment='center', fontsize=5,
                color=color,rotation=270)

        for i in range(len(train_data) - 1):
            prev_departure = pd.to_datetime(train_data.iloc[i]["departure_time"], format='%H:%M')
            current_arrival = pd.to_datetime(train_data.iloc[i + 1]["arrival_time"], format='%H:%M')
            prev_station = train_data.iloc[i]["station"]
            current_station = train_data.iloc[i + 1]["station"]
            ypre_time = stations.tolist().index(prev_station)
            ycurrent_time = stations.tolist().index(current_station)

            # y_start = stations.tolist().index(prev_station)
            # if y_start > stations.tolist().index(current_station):
            #     y_start = stations.tolist().index(current_station)

            # 标注出发和到达时间，仅显示分钟
            if prev_departure != current_arrival:
                if (prev_departure, prev_station) not in marked_times:
                    # 使用 y_start 获取当前的 y 坐标，而非车站名称
                    ax.text(prev_departure + pd.Timedelta(minutes=1), ypre_time - 0.07, prev_departure.strftime('%M'),
                            verticalalignment='bottom', horizontalalignment='right', fontsize=3,
                            color=color)  # y坐标相对y_start减0.1
                    marked_times.add((prev_departure, prev_station))

                if (current_arrival, current_station) not in marked_times:
                    ax.text(current_arrival - pd.Timedelta(minutes=1), ycurrent_time - 0.07,
                            current_arrival.strftime('%M'),
                            verticalalignment='bottom', horizontalalignment='right', fontsize=3,
                            color=color)  # y坐标相对y_start减0.1
                    marked_times.add((current_arrival, current_station))
            ax.plot([prev_departure, current_arrival], [prev_station, current_station], color=color, lw=0.5)

    # 绘制下行运行图及标注车次
    for train in df_down["train_ID"].unique():
        train_data = df_down[df_down["train_ID"] == train]
        color = 'red'
        marked_times = set()  # 用于记录已经标注的时间和车站

        # 标注始发站车次
        start_station = train_data.iloc[0]["station"]
        start_time = pd.to_datetime(train_data.iloc[0]["departure_time"], format='%H:%M')
        y_start = stations.tolist().index(start_station)

        # 检查位置重叠，并进行调整
        #while any(abs(start_time - pos[0]) < time_threshold and y_start == pos[1] for pos in marked_positions_down):
        #    y_start += 0.1  # 向上移动

        marked_positions_down.append((start_time, y_start))

        ax.text(start_time, y_start + 0.05 ,  train, verticalalignment='bottom', horizontalalignment='center', fontsize=5,
                color=color,rotation=270)

        for i in range(len(train_data) - 1):
            prev_departure = pd.to_datetime(train_data.iloc[i]["departure_time"], format='%H:%M')
            current_arrival = pd.to_datetime(train_data.iloc[i + 1]["arrival_time"], format='%H:%M')
            prev_station = train_data.iloc[i]["station"]
            current_station = train_data.iloc[i + 1]["station"]

            if prev_departure != current_arrival:
                if (prev_departure, prev_station) not in marked_times:
                    ax.text(prev_departure + pd.Timedelta(minutes=1), prev_station, prev_departure.strftime('%M'),
                            verticalalignment='bottom', horizontalalignment='left', fontsize=3, color=color)
                    marked_times.add((prev_departure, prev_station))

                if (current_arrival, current_station) not in marked_times:
                    ax.text(current_arrival - pd.Timedelta(minutes=1), current_station, current_arrival.strftime('%M'),
                            verticalalignment='bottom', horizontalalignment='left', fontsize=3, color=color)
                    marked_times.add((current_arrival, current_station))

            ax.plot([prev_departure, current_arrival], [prev_station, current_station], color=color, linestyle='--',
                    lw=0.5)

    ax.set_ylim(stations[0], stations[-1])

    start_time = min(pd.to_datetime(df_up['arrival_time'].min(), format='%H:%M'),
                     pd.to_datetime(df_down['arrival_time'].min(), format='%H:%M'))
    end_time = max(pd.to_datetime(df_up['arrival_time'].max(), format='%H:%M'),
                   pd.to_datetime(df_down['arrival_time'].max(), format='%H:%M'))

    # 刻度调整为最近的整10分钟和整30分钟
    start_time = start_time.replace(minute=(start_time.minute // 10) * 10, second=0)
    current_hour = end_time.hour
    current_minute = end_time.minute

    new_minute = (current_minute // 10 + 1) * 10 % 60
    if new_minute == 0:
        current_hour += 1
    if current_hour == 24:
        current_hour = 0
        end_time += pd.Timedelta(days=1)

    end_time = end_time.replace(hour=current_hour, minute=new_minute, second=0)

    ax.set_xlim(start_time, end_time)

    # 绘制每10分钟的细实线
    for time in pd.date_range(start=start_time, end=end_time, freq='10T'):
        ax.axvline(x=time, color='green', linestyle='-', linewidth=0.5)

    # 绘制每30分钟的粗虚线
    for time in pd.date_range(start=start_time, end=end_time, freq='30T'):
        ax.axvline(x=time, color='green', linestyle='--', linewidth=1.5)

    # 绘制每整点的粗实线
    for time in pd.date_range(start=start_time.replace(minute=0), end=end_time, freq='1H'):
        ax.axvline(x=time, color='green', linestyle='-', linewidth=1.5)

    ax.spines['top'].set_color('green')
    ax.spines['top'].set_linewidth(2)
    ax.spines['bottom'].set_color('green')
    ax.spines['bottom'].set_linewidth(2)
    ax.spines['left'].set_color('green')
    ax.spines['left'].set_linewidth(2)
    ax.spines['right'].set_color('green')
    ax.spines['right'].set_linewidth(2)

    ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax.tick_params(axis='both', which='both', length=0)
    ax.xaxis.set_major_locator(mdates.HourLocator())

    legend_elements = [
        mlines.Line2D([], [], color='red', label='上行列车', linewidth=1),
        mlines.Line2D([], [], color='red', linestyle='--', label='下行列车', linewidth=1)
    ]
    ax.legend(handles=legend_elements, loc='upper left', prop={'size': 5})

    # 移动图名向上1个单位
    ax.set_title("列车运行图", pad=30)  # `pad` 用于调整标题与图形之间的距离，可以适当调整此值

    # 移动X轴标注向下
    ax.tick_params(axis='x', labelsize=10, pad=35)  # `pad` 设置为负值向下移动X轴刻度标签

    plt.grid(True)

    plt.xticks(rotation=0)
    plt.tight_layout()
    image_path = 'high_res_sine_wave.png'


    plt.savefig(image_path, dpi=500)
    plt.show(block=True)
    plt.close()
    return image_path


if __name__ == '__main__':
    # 示例调用
    timetable(r"调整后的下行时刻表.xlsx",r"下行计划时刻表.xlsx")