# 获取账户资金
# https://open.longportapp.com/docs/trade/asset/account
from longport.openapi import TradeContext, Config
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
# 使用TradeContext而不是QuoteContext来查询账户余额
ctx = TradeContext(config)
resp = ctx.account_balance()
print(resp)