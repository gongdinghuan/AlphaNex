import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import os

# 设置中文显示 - 使用更通用的字体设置
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号
# 尝试使用系统可用的字体
plt.rcParams['font.family'] = ['Arial Unicode MS', 'SimHei', 'Heiti TC', 'sans-serif']

# 读取CSV文件
csv_path = '/Users/gongdinghuan/PycharmProjects/AlphaNex/account_daily_log.csv'
df = pd.read_csv(csv_path)

# 处理时间戳数据
df['datetime'] = pd.to_datetime(df['时间戳'], errors='coerce')

# 处理收益率数据，将百分比字符串转换为浮点数
df['当日收益率数值'] = df['当日收益率'].str.replace('%', '').astype(float) / 100

# 创建图形
plt.figure(figsize=(14, 8))

# 绘制折线图
plt.plot(df['datetime'], df['当日收益率数值'] * 100, marker='o', linestyle='-', linewidth=2, markersize=5, color='blue')

# 添加网格线
plt.grid(True, linestyle='--', alpha=0.7)

# 设置标题和标签
plt.title('账户实时收益率变化', fontsize=16)
plt.xlabel('时间', fontsize=14)
plt.ylabel('收益率 (%)', fontsize=14)

# 设置x轴日期格式
ax = plt.gca()
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
plt.xticks(rotation=45)

# 设置y轴范围，让图表更美观
min_return = df['当日收益率数值'].min() * 100 - 0.5
max_return = df['当日收益率数值'].max() * 100 + 0.5
plt.ylim(min_return, max_return)

# 添加零线
plt.axhline(y=0, color='r', linestyle='-', alpha=0.3)

# 在每个数据点上标注收益率
for i, row in df.iterrows():
    plt.annotate(f"{row['当日收益率']}", 
                 (row['datetime'], row['当日收益率数值'] * 100),
                 textcoords="offset points", 
                 xytext=(0,10), 
                 ha='center',
                 fontsize=9)

# 调整布局
plt.tight_layout()

# 保存图表
output_path = '/Users/gongdinghuan/PycharmProjects/AlphaNex/daily_return_visualization.png'
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"图表已保存至: {output_path}")

# 显示图表
plt.show()

# 额外的统计信息
print("\n收益率统计信息:")
print(f"平均收益率: {df['当日收益率数值'].mean() * 100:.2f}%")
print(f"最大收益率: {df['当日收益率数值'].max() * 100:.2f}%")
print(f"最小收益率: {df['当日收益率数值'].min() * 100:.2f}%")
print(f"正收益天数: {(df['当日收益率数值'] > 0).sum()} 天")
print(f"负收益天数: {(df['当日收益率数值'] < 0).sum()} 天")