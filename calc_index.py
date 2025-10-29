

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票指标计算脚本

该脚本从config.yaml读取股票列表，使用LongPort API计算股票指标并按照API文档格式输出结果
参考文档: https://open.longportapp.com/zh-CN/docs/quote/pull/calc-index
"""

from longport.openapi import Config, QuoteContext, CalcIndex
import yaml
import json

# 从YAML文件读取配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config_data = yaml.safe_load(f)

# 创建Config对象
config = Config(
    app_key=config_data['longport']['app_key'],
    app_secret=config_data['longport']['app_secret'],
    access_token=config_data['longport']['access_token']
)

# 创建行情上下文对象
ctx = QuoteContext(config)

# 从配置中提取股票代码列表
stock_symbols = []
for stock in config_data.get('stocks', []):
    if 'symbol' in stock:
        stock_symbols.append(stock['symbol'])

# 如果配置中没有股票，使用默认的示例股票
if not stock_symbols:
    stock_symbols = ["700.HK", "AAPL.US"]

print(f"将计算以下股票的指标: {', '.join(stock_symbols)}")

# 计算股票指标 - 根据API文档，获取更多常用指标
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
        "fiveMinutesChangeRate": f"{item.five_minutes_change_rate:.2f}" if item.five_minutes_change_rate is not None else None
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

# 更简洁的表格输出格式，便于查看关键指标
print("\n简洁表格输出:")
print("+---------------+------------+------------+------------+------------+")
print("| 股票代码      | 当前价格   | 涨跌幅(%)  | 5日涨跌幅(%)| 市盈率(TTM)|")
print("+---------------+------------+------------+------------+------------+")
for item in resp:
    last_price = f"{item.last_done:.3f}" if item.last_done is not None else "N/A"
    change_rate = f"{item.change_rate:.2f}" if item.change_rate is not None else "N/A"
    five_day_rate = f"{item.five_day_change_rate:.2f}" if item.five_day_change_rate is not None else "N/A"
    pe_ratio = f"{item.pe_ttm_ratio:.2f}" if item.pe_ttm_ratio is not None else "N/A"
    print(f"| {item.symbol:<13} | {last_price:<10} | {change_rate:<10} | {five_day_rate:<10} | {pe_ratio:<10} |")
print("+---------------+------------+------------+------------+------------+")