from longport.openapi import QuoteContext, Config
import yaml

# 从YAML文件读取配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config_data = yaml.safe_load(f)

# 创建Config对象
config = Config(
    app_key=config_data['longport']['app_key'],
    app_secret=config_data['longport']['app_secret'],
    access_token=config_data['longport']['access_token']
)

# 创建QuoteContext
ctx = QuoteContext(config)

# 从配置中获取股票代码列表
stock_symbols = [stock['symbol'] for stock in config_data['stocks'] if stock.get('watch', True)]
print(f"从配置文件中获取的股票列表: {stock_symbols}")

def quote_to_dict(quote):
    """将SecurityQuote对象转换为字典"""
    # 辅助函数：将可能的datetime对象转换为字符串
    def convert_timestamp(timestamp):
        if hasattr(timestamp, 'strftime'):
            return timestamp.strftime('%Y-%m-%d %H:%M:%S')
        return str(timestamp)
    
    # 尝试直接使用对象的属性构建字典
    quote_dict = {
        'symbol': quote.symbol,
        'last_done': float(quote.last_done),
        'prev_close': float(quote.prev_close),
        'open': float(quote.open),
        'high': float(quote.high),
        'low': float(quote.low),
        'timestamp': convert_timestamp(quote.timestamp),
        'volume': int(quote.volume),
        'turnover': float(quote.turnover),
        'trade_status': str(quote.trade_status)
    }
    
    # 处理盘前数据
    if quote.pre_market_quote:
        quote_dict['pre_market_quote'] = {
            'last_done': float(quote.pre_market_quote.last_done),
            'timestamp': convert_timestamp(quote.pre_market_quote.timestamp),
            'volume': int(quote.pre_market_quote.volume),
            'turnover': float(quote.pre_market_quote.turnover),
            'high': float(quote.pre_market_quote.high),
            'low': float(quote.pre_market_quote.low),
            'prev_close': float(quote.pre_market_quote.prev_close)
        }
    
    # 处理盘后数据
    if quote.post_market_quote:
        quote_dict['post_market_quote'] = {
            'last_done': float(quote.post_market_quote.last_done),
            'timestamp': convert_timestamp(quote.post_market_quote.timestamp),
            'volume': int(quote.post_market_quote.volume),
            'turnover': float(quote.post_market_quote.turnover),
            'high': float(quote.post_market_quote.high),
            'low': float(quote.post_market_quote.low),
            'prev_close': float(quote.post_market_quote.prev_close)
        }
    
    return quote_dict

# 获取行情数据
resp = ctx.quote(stock_symbols)
print("\n原始行情数据:")
print(resp[0])

# 转换为字典并打印
print("\n转换为字典后:")
quote_dict = quote_to_dict(resp[0])
print(quote_dict)
import json
print(json.dumps(quote_dict, indent=2))

# 计算涨跌幅
if quote_dict['prev_close'] > 0:
    change_percent = ((quote_dict['last_done'] - quote_dict['prev_close']) / quote_dict['prev_close']) * 100
    print(f"\n涨跌幅: {change_percent:.2f}%")