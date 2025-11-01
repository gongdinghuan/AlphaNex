#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票账户收益率可视化Web应用

该应用基于Flask构建，整合了account.py和可视化功能，提供直观的账户收益率展示界面。
"""

from flask import Flask, render_template, jsonify, request
import pandas as pd
import matplotlib
# 设置Matplotlib使用非交互式后端避免线程问题
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64
import os
import datetime
import threading
import time
import subprocess
import sqlite3
from account import AccountInfoFormatter  # 导入账户信息格式化类

# 创建Flask应用实例
app = Flask(__name__)

# 设置中文显示
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号
plt.rcParams['font.family'] = ['Arial Unicode MS', 'SimHei', 'Heiti TC', 'sans-serif']

# 数据库文件路径
DB_PATH = 'account_data.db'
# CSV日志文件路径（作为备份）
CSV_LOG_PATH = '/Users/gongdinghuan/PycharmProjects/AlphaNex/account_daily_log.csv'


def run_account_script():
    """
    运行account.py脚本
    """
    try:
        # 获取当前脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        account_script_path = os.path.join(script_dir, 'account.py')
        
        print(f"[{datetime.datetime.now()}] 开始运行account.py...")
        # 运行account.py脚本
        result = subprocess.run(['python3', account_script_path], 
                              capture_output=True, 
                              text=True,
                              cwd=script_dir)
        
        print(f"[{datetime.datetime.now()}] account.py运行完成")
        print(f"STDOUT: {result.stdout}")
        if result.stderr:
            print(f"STDERR: {result.stderr}")
            
    except Exception as e:
        print(f"[{datetime.datetime.now()}] 运行account.py时出错: {e}")


def scheduled_runner():
    """
    定时运行account.py的后台线程函数
    """
    while True:
        try:
            # 运行account.py
            run_account_script()
            # 每10分钟运行一次
            print(f"[{datetime.datetime.now()}] 等待10分钟后再次运行account.py...")
            time.sleep(600)  # 600秒 = 10分钟
        except Exception as e:
            print(f"[{datetime.datetime.now()}] 定时任务出错: {e}")
            # 出错后等待1分钟再尝试
            time.sleep(60)


def start_scheduler():
    """
    启动定时任务线程
    """
    scheduler_thread = threading.Thread(target=scheduled_runner, daemon=True)
    scheduler_thread.start()
    print(f"[{datetime.datetime.now()}] 定时任务已启动，将每10分钟运行一次account.py")


def get_account_data():
    """
    获取最新的账户数据（优先从数据库读取）
    
    Returns:
        dict: 账户信息和当日表现数据
    """
    # 优先从数据库读取
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 查询最新的一条记录
            cursor.execute('''
                SELECT date, timestamp, net_assets, yesterday_net_assets, daily_profit, 
                       daily_return_rate, total_cash, buy_power, risk_level
                FROM account_logs 
                ORDER BY timestamp DESC LIMIT 1
            ''')
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # 格式化账户信息
                daily_return_rate_str = result[5]
                daily_return_rate = float(daily_return_rate_str.replace('%', '')) if daily_return_rate_str else 0.0
                
                account_data = {
                    'currency': 'HKD',  # 假设主币种是HKD
                    'total_cash': float(result[6]),
                    'net_assets': float(result[2]),
                    'buy_power': float(result[7]),
                    'risk_level': result[8],
                    'risk_level_desc': '安全' if result[8] == 0 else '未知',
                    'performance': {
                        'daily_profit': float(result[4]),
                        'daily_return_rate': daily_return_rate
                    }
                }
                
                print(f"从数据库成功读取账户数据")
                return account_data
    except Exception as e:
        print(f"从数据库读取账户数据时出错: {e}")
    
    # 如果数据库读取失败，回退到原始方法
    try:
        formatter = AccountInfoFormatter()
        accounts = formatter.get_account_balance()
        
        if not accounts:
            return None
        
        account = accounts[0]  # 假设只有一个账户
        performance = formatter.calculate_daily_performance(float(account.net_assets))
        
        # 格式化账户信息
        account_data = {
            'currency': account.currency,
            'total_cash': float(account.total_cash),
            'net_assets': float(account.net_assets),
            'buy_power': float(account.buy_power),
            'risk_level': account.risk_level,
            'risk_level_desc': formatter.format_risk_level(account.risk_level),
            'performance': performance
        }
        
        return account_data
    except Exception as e:
        print(f"获取账户数据时出错: {e}")
        return None


def generate_echarts_data(time_range='all'):
    """
    生成ECharts所需的收益率数据（优先从数据库读取）
    
    Args:
        time_range: 时间范围，可选值：'week', 'month', 'all'
    
    Returns:
        dict: 包含标签和数值的字典
    """
    # 优先从数据库读取
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 根据时间范围设置过滤条件
            now = datetime.datetime.now()
            if time_range == 'week':
                cutoff_date = (now - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
            elif time_range == 'month':
                cutoff_date = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
            else:  # 'all'
                cutoff_date = '1900-01-01'  # 一个很早的日期
            
            # 查询数据
            cursor.execute('''
                SELECT date, daily_return_rate 
                FROM account_logs 
                WHERE date >= ? 
                ORDER BY timestamp ASC
            ''', (cutoff_date,))
            
            results = cursor.fetchall()
            conn.close()
            
            if results:
                # 提取数据
                labels = [result[0] for result in results]
                # 处理包含%符号的收益率字符串
                values = []
                for r in results:
                    try:
                        # 移除%符号并转换为float
                        rate_str = r[1].replace('%', '') if isinstance(r[1], str) else str(r[1])
                        values.append(float(rate_str))
                    except (ValueError, AttributeError):
                        values.append(0.0)  # 转换失败时使用默认值
                
                print(f"从数据库成功读取图表数据，共{len(results)}条记录")
                return {
                    'labels': labels,
                    'values': values
                }
    except Exception as e:
        print(f"从数据库读取图表数据时出错: {e}")
    
    # 如果数据库读取失败，回退到从CSV文件读取
    try:
        # 读取CSV文件
        df = pd.read_csv(CSV_LOG_PATH)
        
        # 处理时间戳数据
        df['datetime'] = pd.to_datetime(df['时间戳'], errors='coerce')
        
        # 处理收益率数据，将百分比字符串转换为浮点数
        df['当日收益率数值'] = df['当日收益率'].str.replace('%', '').astype(float)
        
        # 根据时间范围过滤数据
        if time_range == 'week':
            # 筛选最近一周的数据
            week_ago = datetime.datetime.now() - datetime.timedelta(days=7)
            df = df[df['datetime'] >= week_ago]
        elif time_range == 'month':
            # 筛选最近一个月的数据
            month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
            df = df[df['datetime'] >= month_ago]
        # 'all' 不进行过滤
        
        # 确保数据按时间排序
        df = df.sort_values('datetime')
        
        # 格式化日期为统一的时间戳格式，确保时间轴显示完整
        labels = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()
        
        # 获取收益率数值，并处理NaN值
        values = df['当日收益率数值'].fillna(0).tolist()
        
        return {
            'labels': labels,
            'values': values
        }
    except Exception as e:
        print(f"生成ECharts数据时出错: {e}")
        return {
            'labels': [],
            'values': []
        }


def generate_echarts_cumulative_data():
    """
    生成ECharts所需的累计收益率数据（优先从数据库读取）
    
    Returns:
        dict: 包含标签和数值的字典
    """
    # 优先从数据库读取
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 查询所有数据按时间排序，包含时间戳以获得精确时间
            cursor.execute('''
                SELECT timestamp, date, net_assets, yesterday_net_assets
                FROM account_logs 
                ORDER BY timestamp ASC
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            if results and len(results) > 1:
                # 提取数据
                # 使用时间戳作为标签以确保一致性
                labels = []
                for r in results:
                    try:
                        # 尝试多种时间戳格式
                        if isinstance(r[0], str):
                            # 如果是字符串，尝试直接转换为datetime
                            try:
                                ts = datetime.datetime.fromisoformat(r[0].replace('Z', '+00:00'))
                            except ValueError:
                                # 尝试其他格式
                                ts = datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S')
                            labels.append(ts.strftime('%Y-%m-%d %H:%M:%S'))
                        else:
                            # 如果是数字，作为timestamp处理
                            labels.append(datetime.datetime.fromtimestamp(float(r[0])).strftime('%Y-%m-%d %H:%M:%S'))
                    except Exception:
                        # 如果解析失败，使用日期字段
                        labels.append(r[1])
                net_assets = [float(r[2]) for r in results]
                
                # 找到有效的基准值 - 优先使用第一个记录的yesterday_net_assets，如果有值且大于0
                initial_assets = None
                for r in results:
                    if r[3] and float(r[3]) > 0:
                        initial_assets = float(r[3])
                        break
                
                # 如果找不到有效的yesterday_net_assets，则使用第一个记录的net_assets作为基准
                if initial_assets is None:
                    initial_assets = net_assets[0]
                
                # 计算累计收益率
                cumulative_returns = [((assets - initial_assets) / initial_assets) * 100 for assets in net_assets]
                
                print(f"从数据库成功读取累计收益率数据，共{len(results)}条记录，使用基准值: {initial_assets}")
                return {
                    'labels': labels,
                    'values': cumulative_returns
                }
    except Exception as e:
        print(f"从数据库读取累计收益率数据时出错: {e}")
    
    # 如果数据库读取失败，回退到从CSV文件读取
    try:
        # 读取CSV文件
        df = pd.read_csv(CSV_LOG_PATH)
        
        # 处理时间戳数据
        df['datetime'] = pd.to_datetime(df['时间戳'], errors='coerce')
        
        # 确保数据按时间排序
        df = df.sort_values('datetime')
        
        # 找到有效的基准值 - 优先使用第一个有效的昨日净资产
        initial_assets = None
        valid_yesterday_assets = df[df['昨日净资产'] > 0]['昨日净资产']
        if not valid_yesterday_assets.empty:
            initial_assets = valid_yesterday_assets.iloc[0]
        else:
            # 如果没有有效的昨日净资产，使用第一个记录的净资产
            initial_assets = df['净资产'].iloc[0]
        
        # 计算累计收益率（相对于基准值）
        df['累计收益率百分比'] = ((df['净资产'] - initial_assets) / initial_assets) * 100
        
        # 格式化日期为统一的时间戳格式
        labels = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()
        
        # 获取累计收益率数值，并处理NaN值
        values = df['累计收益率百分比'].fillna(0).tolist()
        
        print(f"从CSV成功读取累计收益率数据，使用基准值: {initial_assets}")
        return {
            'labels': labels,
            'values': values
        }
    except Exception as e:
        print(f"生成累计收益率数据时出错: {e}")
        return {
            'labels': [],
            'values': []
        }


# 累计收益率图表已替换为ECharts数据生成函数 generate_echarts_cumulative_data


def calculate_statistics():
    """
    计算收益率统计信息
    
    Returns:
        dict: 统计信息字典
    """
    try:
        # 读取CSV文件
        df = pd.read_csv(CSV_LOG_PATH)
        
        # 处理收益率数据，将百分比字符串转换为浮点数
        df['当日收益率数值'] = df['当日收益率'].str.replace('%', '').astype(float) / 100
        
        # 处理时间戳数据用于排序
        df['datetime'] = pd.to_datetime(df['时间戳'], errors='coerce')
        
        # 确保数据按时间排序
        df_sorted = df.sort_values('datetime')
        
        # 获取最新的净资产和最早的昨日净资产
        latest_net_assets = df_sorted['净资产'].iloc[-1]  # 最新净资产
        earliest_yesterday_assets = df_sorted['昨日净资产'].iloc[0]  # 最早的昨日净资产
        
        # 计算统计信息
        stats = {
            'average_return': df['当日收益率数值'].mean() * 100,
            'max_return': df['当日收益率数值'].max() * 100,
            'min_return': df['当日收益率数值'].min() * 100,
            'positive_days': (df['当日收益率数值'] > 0).sum(),
            'negative_days': (df['当日收益率数值'] < 0).sum(),
            'total_days': len(df),
            'win_rate': (df['当日收益率数值'] > 0).sum() / len(df) * 100,
            'std_return': df['当日收益率数值'].std() * 100,  # 收益率标准差
            'cumulative_return': ((latest_net_assets - earliest_yesterday_assets) / earliest_yesterday_assets) * 100  # 累计收益率（最新净资产与最早昨日净资产对比）
        }
        
        return stats
    except Exception as e:
        print(f"计算统计信息时出错: {e}")
        return None


@app.route('/')
def index():
    """首页路由，显示账户信息和收益率图表"""
    # 获取账户数据
    account_data = get_account_data()
    
    # 计算统计信息
    statistics = calculate_statistics()
    
    # 获取ECharts所需的默认数据
    return_data = generate_echarts_data('all')
    cumulative_data = generate_echarts_cumulative_data()
    
    # 渲染模板
    return render_template('dashboard.html', 
                          account_data=account_data,
                          statistics=statistics,
                          return_labels=return_data['labels'],
                          daily_return_data=return_data['values'],
                          cumulative_labels=cumulative_data['labels'],
                          cumulative_return_data=cumulative_data['values'],
                          current_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


@app.route('/chart')
def get_chart():
    """获取指定时间范围的收益率数据（ECharts格式）"""
    # 获取时间范围参数
    time_range = request.args.get('range', 'all')
    
    # 生成ECharts数据
    data = generate_echarts_data(time_range)
    
    return jsonify(data)


@app.route('/refresh')
def refresh_data():
    """刷新数据"""
    # 获取最新账户数据
    account_data = get_account_data()
    
    # 计算最新统计信息
    statistics = calculate_statistics()
    
    return jsonify({
        'account_data': account_data,
        'statistics': statistics,
        'current_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


# 创建templates目录
if not os.path.exists('templates'):
    os.makedirs('templates')


# 创建HTML模板
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write('''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>股票账户收益率可视化</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background-color: #f8f9fa;
            margin: 0;
            padding: 0;
        }}
        .header {{
            background-color: #343a40;
            color: white;
            padding: 1rem 0;
            margin-bottom: 2rem;
        }}
        .card {{
            margin-bottom: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 15px rgba(0, 0, 0, 0.1);
        }}
        .card-header {{
            background-color: #007bff;
            color: white;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-weight: bold;
        }}
        .card-body {{
            padding: 1.5rem;
        }}
        .stat-value {{
            font-size: 1.5rem;
            font-weight: bold;
        }}
        .positive {{
            color: #28a745;
        }}
        .negative {{
            color: #dc3545;
        }}
        .neutral {{
            color: #6c757d;
        }}
        .chart-container {{
            position: relative;
            height: 400px;
            margin-bottom: 1rem;
        }}
        .btn-group .btn {{
            margin-right: 0.5rem;
            margin-bottom: 0.5rem;
        }}
        .refresh-btn {{
            float: right;
        }}
        .risk-level-safe {{
            color: #28a745;
        }}
        .risk-level-normal {{
            color: #ffc107;
        }}
        .risk-level-warning {{
            color: #fd7e14;
        }}
        .risk-level-danger {{
            color: #dc3545;
        }}
        .update-time {{
            font-size: 0.9rem;
            color: #6c757d;
            text-align: right;
            margin-top: 0.5rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1 class="text-center">股票账户收益率可视化</h1>
        </div>
    </div>

    <div class="container">
        <!-- 刷新时间和按钮 -->
        <div class="row mb-4">
            <div class="col-md-12">
                <button id="refresh-btn" class="btn btn-primary refresh-btn">
                    <i class="bi bi-arrow-clockwise"></i> 刷新数据
                </button>
                <div class="update-time" id="update-time">最后更新: {{ current_time }}</div>
            </div>
        </div>

        <!-- 账户概览卡片 -->
        <div class="row">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">账户概览</div>
                    <div class="card-body">
                        {% if account_data %}
                        <div class="row mb-3">
                            <div class="col-6">
                                <div class="text-muted">净资产</div>
                                <div class="stat-value">{{ "{:,.2f}".format(account_data.net_assets) }} {{ account_data.currency }}</div>
                            </div>
                            <div class="col-6">
                                <div class="text-muted">现金总额</div>
                                <div class="stat-value">{{ "{:,.2f}".format(account_data.total_cash) }} {{ account_data.currency }}</div>
                            </div>
                        </div>
                        <div class="row mb-3">
                            <div class="col-6">
                                <div class="text-muted">购买力</div>
                                <div class="stat-value">{{ "{:,.2f}".format(account_data.buy_power) }} {{ account_data.currency }}</div>
                            </div>
                            <div class="col-6">
                                <div class="text-muted">风险等级</div>
                                <div class="stat-value risk-level-{{ account_data.risk_level_desc }}">{{ account_data.risk_level_desc }}</div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-6">
                                <div class="text-muted">当日盈亏</div>
                                <div class="stat-value 
                                    {% if account_data.performance.daily_profit > 0 %}positive
                                    {% elif account_data.performance.daily_profit < 0 %}negative
                                    {% else %}neutral{% endif %}">
                                    {{ "{:+.2f}".format(account_data.performance.daily_profit) }} {{ account_data.currency }}
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="text-muted">当日收益率</div>
                                <div class="stat-value 
                                    {% if account_data.performance.daily_return_rate > 0 %}positive
                                    {% elif account_data.performance.daily_return_rate < 0 %}negative
                                    {% else %}neutral{% endif %}">
                                    {{ "{:+.2f}% ".format(account_data.performance.daily_return_rate) }}
                                    {% if account_data.performance.daily_return_rate > 0 %}<i class="bi bi-arrow-up"></i>
                                    {% elif account_data.performance.daily_return_rate < 0 %}<i class="bi bi-arrow-down"></i>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                        {% else %}
                        <p class="text-center text-muted">无法获取账户信息</p>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <!-- 统计信息卡片 -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">收益统计</div>
                    <div class="card-body">
                        {% if statistics %}
                        <div class="row mb-3">
                            <div class="col-6">
                                <div class="text-muted">平均收益率</div>
                                <div class="stat-value 
                                    {% if statistics.average_return > 0 %}positive
                                    {% elif statistics.average_return < 0 %}negative
                                    {% else %}neutral{% endif %}">
                                    {{ "{:+.2f}% ".format(statistics.average_return) }}
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="text-muted">累计收益率</div>
                                <div class="stat-value 
                                    {% if statistics.cumulative_return > 0 %}positive
                                    {% elif statistics.cumulative_return < 0 %}negative
                                    {% else %}neutral{% endif %}">
                                    {{ "{:+.2f}% ".format(statistics.cumulative_return) }}
                                </div>
                            </div>
                        </div>
                        <div class="row mb-3">
                            <div class="col-6">
                                <div class="text-muted">最大单日收益</div>
                                <div class="stat-value positive">+{{ "{:.2f}% ".format(statistics.max_return) }}</div>
                            </div>
                            <div class="col-6">
                                <div class="text-muted">最大单日亏损</div>
                                <div class="stat-value negative">{{ "{:.2f}% ".format(statistics.min_return) }}</div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-6">
                                <div class="text-muted">胜率</div>
                                <div class="stat-value">{{ "{:.2f}% ".format(statistics.win_rate) }}</div>
                            </div>
                            <div class="col-6">
                                <div class="text-muted">数据天数</div>
                                <div class="stat-value">{{ statistics.total_days }} 天</div>
                            </div>
                        </div>
                        {% else %}
                        <p class="text-center text-muted">无法获取统计信息</p>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>

        <!-- 收益率图表 -->
        <div class="row">
            <div class="col-md-12">
                <div class="card">
                    <div class="card-header">
                        收益率变化趋势
                        <div class="btn-group float-right" role="group">
                            <button type="button" class="btn btn-sm btn-outline-light time-range-btn" data-range="week">最近一周</button>
                            <button type="button" class="btn btn-sm btn-outline-light time-range-btn" data-range="month">最近一月</button>
                            <button type="button" class="btn btn-sm btn-outline-light time-range-btn" data-range="all">全部数据</button>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            {% if return_chart %}
                            <img id="return-chart" src="data:image/png;base64,{{ return_chart }}" class="img-fluid" alt="收益率变化趋势图">
                            {% else %}
                            <p class="text-center text-muted">无法生成图表</p>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 累计收益率图表 -->
        <div class="row">
            <div class="col-md-12">
                <div class="card">
                    <div class="card-header">累计收益率变化</div>
                    <div class="card-body">
                        <div class="chart-container">
                            {% if cumulative_chart %}
                            <img id="cumulative-chart" src="data:image/png;base64,{{ cumulative_chart }}" class="img-fluid" alt="累计收益率变化趋势图">
                            {% else %}
                            <p class="text-center text-muted">无法生成图表</p>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 时间范围按钮点击事件
        document.querySelectorAll('.time-range-btn').forEach(btn => {{
            btn.addEventListener('click', function() {{
                const range = this.getAttribute('data-range');
                
                // 显示加载状态
                document.getElementById('return-chart').src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" font-size="16">加载中...</text></svg>';
                
                // 请求新的图表
                fetch(`/chart?range=${{range}}`)  
                    .then(response => response.json())
                    .then(data => {{
                        document.getElementById('return-chart').src = 'data:image/png;base64,' + data.chart;
                    }})
                    .catch(error => {{
                        console.error('获取图表失败:', error);
                        document.getElementById('return-chart').src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" font-size="16">加载失败</text></svg>';
                    }});
            }});
        }});
        
        // 刷新按钮点击事件
        document.getElementById('refresh-btn').addEventListener('click', function() {{
            // 显示加载状态
            this.disabled = true;
            this.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 刷新中...';
            
            // 请求刷新数据
            fetch('/refresh')
                .then(response => response.json())
                .then(data => {{
                    // 更新时间
                    document.getElementById('update-time').textContent = '最后更新: ' + data.current_time;
                    
                    // 如果有新的账户数据，更新账户信息
                    if (data.account_data) {{
                        updateAccountInfo(data.account_data);
                    }}
                    
                    // 如果有新的统计数据，更新统计信息
                    if (data.statistics) {{
                        updateStatistics(data.statistics);
                    }}
                    
                    // 刷新图表
                    fetch('/chart?range=all')
                        .then(response => response.json())
                        .then(chartData => {{
                            document.getElementById('return-chart').src = 'data:image/png;base64,' + chartData.chart;
                        }});
                }})
                .catch(error => {{
                    console.error('刷新数据失败:', error);
                }})
                .finally(() => {{
                    // 恢复按钮状态
                    this.disabled = false;
                    this.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 刷新数据';
                }});
        }});
        
        // 更新账户信息
        function updateAccountInfo(accountData) {{
            // 这里可以根据实际需要更新账户信息部分
            console.log('更新账户信息:', accountData);
        }}
        
        // 更新统计信息
        function updateStatistics(statistics) {{
            // 这里可以根据实际需要更新统计信息部分
            console.log('更新统计信息:', statistics);
        }}
    </script>
</body>
</html>
''')


if __name__ == '__main__':
    # 启动定时任务
    start_scheduler()
    
    # 在开发环境下运行应用，使用端口5001避免冲突
    print("启动股票账户收益率可视化Web应用...")
    print("请访问 http://127.0.0.1:5001 查看应用")
    print("按 Ctrl+C 停止服务器")
    app.run(debug=False, host='0.0.0.0', port=5001)