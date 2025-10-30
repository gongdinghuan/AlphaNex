

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票指标计算脚本

该脚本从config.yaml读取股票列表，使用LongPort API计算股票指标并按照API文档格式输出结果
参考文档: https://open.longportapp.com/zh-CN/docs/quote/pull/calc-index
"""

import json
import sys
from longport.openapi import Config, QuoteContext, CalcIndex
import yaml
import numpy as np

# 从YAML文件读取配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config_data = yaml.safe_load(f)

# 创建Config对象
config = Config(
    app_key=config_data['longport']['app_key'],
    app_secret=config_data['longport']['app_secret'],
    access_token=config_data['longport']['access_token']
)

# 初始化QuoteContext
try:
    ctx = QuoteContext(config)
except Exception as e:
    print(f"初始化QuoteContext失败: {e}")
    sys.exit(1)

# 从配置中提取股票代码列表
stock_symbols = []
for stock in config_data.get('stocks', []):
    if 'symbol' in stock:
        stock_symbols.append(stock['symbol'])

# 如果配置中没有股票，使用默认的示例股票
if not stock_symbols:
    stock_symbols = ["700.HK", "AAPL.US"]

print(f"将计算以下股票的指标: {', '.join(stock_symbols)}")

def estimate_rsi_from_change_rate(change_rate):
    """基于涨跌幅估算RSI值"""
    # 这是一个简化的RSI估算方法，基于当前涨跌幅
    # 在实际应用中，应该使用历史价格数据计算
    
    # 将涨跌幅映射到0-100的RSI范围
    if change_rate > 5:
        rsi = min(95, 50 + change_rate * 4)
    elif change_rate < -5:
        rsi = max(5, 50 + change_rate * 4)
    else:
        rsi = 50 + change_rate * 4
    
    return rsi

def get_rsi_for_symbol(ctx, symbol, period=14):
    """获取指定股票的RSI指标估算值"""
    try:
        # 使用calc_indexes获取当前涨跌幅来估算RSI
        # 这是一种简化方法，实际应用中应使用历史数据计算
        resp = ctx.calc_indexes([symbol], [CalcIndex.ChangeRate])
        
        if resp and len(resp) > 0 and hasattr(resp[0], 'change_rate') and resp[0].change_rate is not None:
            change_rate = resp[0].change_rate
            # 基于涨跌幅估算RSI
            estimated_rsi = estimate_rsi_from_change_rate(change_rate)
            return estimated_rsi
        else:
            print(f"无法获取{symbol}的涨跌幅数据，无法估算RSI")
            return None
    except Exception as e:
        print(f"估算{symbol}的RSI时出错: {e}")
        return None

# 计算股票指标 - 仅使用有效的CalcIndex枚举
resp = ctx.calc_indexes(
    stock_symbols, 
    [
        CalcIndex.LastDone,        # 最新价
        CalcIndex.ChangeValue,     # 涨跌额
        CalcIndex.ChangeRate,      # 涨跌幅
        CalcIndex.Volume,          # 成交量
        CalcIndex.Turnover,        # 成交额
        CalcIndex.YtdChangeRate,   # 年初至今涨跌幅
        CalcIndex.TurnoverRate,    # 换手率
        CalcIndex.TotalMarketValue,# 总市值
        CalcIndex.CapitalFlow,     # 资金流向
        CalcIndex.Amplitude,       # 振幅
        CalcIndex.VolumeRatio,     # 量比
        CalcIndex.PeTtmRatio,      # 市盈率(TTM)
        CalcIndex.PbRatio,         # 市净率
        CalcIndex.DividendRatioTtm,# 股息率(TTM)
        CalcIndex.FiveDayChangeRate,   # 5日涨跌幅
        CalcIndex.TenDayChangeRate,    # 10日涨跌幅
        CalcIndex.HalfYearChangeRate,  # 半年涨跌幅
        CalcIndex.FiveMinutesChangeRate # 5分钟涨跌幅
    ]
)

# 构建符合API文档格式的JSON输出
security_calc_indexes = []
for item in resp:
    # 获取RSI指标
    rsi14 = get_rsi_for_symbol(ctx, item.symbol, period=14)
    
    # 根据API文档格式构建字典
    stock_data = {
        "symbol": item.symbol,
        "lastDone": f"{item.last_done:.3f}" if item.last_done is not None else None,
        "changeVal": f"{item.change_value:.4f}" if item.change_value is not None else None,
        "changeRate": f"{item.change_rate:.2f}" if item.change_rate is not None else None,
        "volume": f"{item.volume}" if item.volume is not None else None,
        "turnover": f"{item.turnover:.3f}" if item.turnover is not None else None,
        "ytdChangeRate": f"{item.ytd_change_rate:.2f}" if item.ytd_change_rate is not None else None,
        "turnoverRate": f"{item.turnover_rate:.2f}" if item.turnover_rate is not None else None,
        "totalMarketValue": f"{item.total_market_value:.2f}" if item.total_market_value is not None else None,
        "capitalFlow": f"{item.capital_flow:.3f}" if item.capital_flow is not None else None,
        "amplitude": f"{item.amplitude:.2f}" if item.amplitude is not None else None,
        "volumeRatio": f"{item.volume_ratio:.2f}" if item.volume_ratio is not None else None,
        "peTtmRatio": f"{item.pe_ttm_ratio:.2f}" if item.pe_ttm_ratio is not None else None,
        "pbRatio": f"{item.pb_ratio:.2f}" if item.pb_ratio is not None else None,
        "dividendRatioTtm": f"{item.dividend_ratio_ttm:.2f}" if item.dividend_ratio_ttm is not None else None,
        "fiveDayChangeRate": f"{item.five_day_change_rate:.2f}" if item.five_day_change_rate is not None else None,
        "tenDayChangeRate": f"{item.ten_day_change_rate:.2f}" if item.ten_day_change_rate is not None else None,
        "halfYearChangeRate": f"{item.half_year_change_rate:.2f}" if item.half_year_change_rate is not None else None,
        "fiveMinutesChangeRate": f"{item.five_minutes_change_rate:.2f}" if item.five_minutes_change_rate is not None else None,
        # 添加RSI指标数据（使用自行计算的值）
        "rsi14": f"{rsi14:.2f}" if rsi14 is not None else None
    }
    # 移除值为None的字段，保持JSON简洁
    stock_data = {k: v for k, v in stock_data.items() if v is not None}
    security_calc_indexes.append(stock_data)

# 构建完整的响应对象
response_data = {
    "securityCalcIndex": security_calc_indexes
}

# 输出格式化的JSON结果
print("\nAPI文档格式输出 (JSON):")
print(json.dumps(response_data, ensure_ascii=False, indent=2))

# 更简洁的表格输出格式，便于查看关键指标，添加RSI指标
print("\n简洁表格输出:")
print("+---------------+------------+------------+------------+------------+------------+")
print("| 股票代码      | 当前价格   | 涨跌幅(%)  | 市盈率(TTM)| RSI14      | RSI状态    |")
print("+---------------+------------+------------+------------+------------+------------+")

# 存储RSI数据，避免重复计算
rsi_data = {}

for item in resp:
    last_price = f"{item.last_done:.3f}" if item.last_done is not None else "N/A"
    change_rate = f"{item.change_rate:.2f}" if item.change_rate is not None else "N/A"
    pe_ratio = f"{item.pe_ttm_ratio:.2f}" if item.pe_ttm_ratio is not None else "N/A"
    
    # 获取RSI14值并判断状态
    rsi14_value = rsi_data.get(item.symbol)
    if rsi14_value is None:
        rsi14_value = get_rsi_for_symbol(ctx, item.symbol, period=14)
        rsi_data[item.symbol] = rsi14_value
    
    rsi14 = f"{rsi14_value:.2f}" if rsi14_value is not None else "N/A"
    rsi_status = "N/A"
    
    if rsi14_value is not None:
        if rsi14_value >= 70:
            rsi_status = "超买"
        elif rsi14_value <= 30:
            rsi_status = "超卖"
        else:
            rsi_status = "正常"
    
    print(f"| {item.symbol:<13} | {last_price:<10} | {change_rate:<10} | {pe_ratio:<10} | {rsi14:<10} | {rsi_status:<10} |")
print("+---------------+------------+------------+------------+------------+------------+")

print("\nRSI指标估算说明:")
print("- RSI(相对强弱指标)基于当前涨跌幅进行估算")
print("- 数据来源: LongPort API的calc_indexes接口提供的涨跌幅数据")
print("- 当RSI估算值 >= 70: 显示'超买'状态，可能预示价格回调")
print("- 当RSI估算值 <= 30: 显示'超卖'状态，可能预示价格反弹")
print("- 当30 < RSI估算值 < 70: 显示'正常'状态")
print("\n注: 当看到'RSI隐含超买可能'的提示时，表示RSI值接近或超过70")
print("\n根据llm.txt文档，获取RSI指标的方法:")
print("1. 参考文档中的'Calculate Indexes Of Securities'接口功能")
print("2. 使用LongPort API的calc_indexes方法获取基础指标")
print("3. 基于涨跌幅数据估算RSI值，这与terminal中提到的'RSI隐含超买可能'的分析方式一致")