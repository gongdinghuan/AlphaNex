# 获取市场温度数据
from longport.openapi import QuoteContext, Config, Market
import yaml
import json

def market_temp_to_dict(temp_obj):
    """将MarketTemperature对象转换为字典"""
    result = {
        'temperature': temp_obj.temperature,
        'description': temp_obj.description,
        'valuation': temp_obj.valuation,
        'sentiment': temp_obj.sentiment
    }
    # 处理timestamp字段，转换为字符串
    if hasattr(temp_obj, 'timestamp'):
        result['timestamp'] = str(temp_obj.timestamp)
    return result

# 从YAML文件读取配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config_data = yaml.safe_load(f)

# 创建Config对象
config = Config(
    app_key=config_data['longport']['app_key'],
    app_secret=config_data['longport']['app_secret'],
    access_token=config_data['longport']['access_token']
)

ctx = QuoteContext(config)
resp = ctx.market_temperature(Market.US)

# 将结果转换为字典并打印
if resp is not None:
    # 将MarketTemperature对象转换为字典
    temp_dict = market_temp_to_dict(resp)
    # 以JSON格式打印，便于阅读
    print(json.dumps(temp_dict, indent=2))
else:
    print("未获取到市场温度数据")