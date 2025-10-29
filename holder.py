from decimal import Decimal
# 移除已弃用的symbol模块导入
from longport.openapi import TradeContext, Config, OrderType, OrderSide, TimeInForceType
import yaml
import json
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('holder')

def load_config():
    """加载配置文件"""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        raise

def create_trade_context(config_data):
    """创建TradeContext实例"""
    try:
        config = Config(
            app_key=config_data['longport']['app_key'],
            app_secret=config_data['longport']['app_secret'],
            access_token=config_data['longport']['access_token']
        )
        return TradeContext(config)
    except KeyError as e:
        logger.error(f"配置文件缺少必要的密钥: {e}")
        raise
    except Exception as e:
        logger.error(f"创建TradeContext实例失败: {e}")
        raise

def positions_to_dict(response):
    """将StockPositionsResponse对象转换为符合API文档格式的字典"""
    # 辅助函数：将Decimal等特殊类型转换为可JSON序列化的类型
    def convert_value(value):
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        elif hasattr(value, 'value'):
            return convert_value(value.value)
        elif hasattr(value, '__str__'):
            return str(value)
        return value
    
    # 按照API文档格式组织结果
    result = {
        "code": 0,  # 模拟API返回的成功状态码
        "data": {
            "list": []
        }
    }
    
    try:
        # 处理每个channel
        for channel in response.channels:
            channel_data = {
                "account_channel": convert_value(channel.account_channel),
                "stock_info": []
            }
            
            # 处理每个position
            for pos in channel.positions:
                stock_info = {
                    "symbol": convert_value(pos.symbol),
                    "symbol_name": convert_value(pos.symbol_name),
                    "currency": convert_value(pos.currency),
                    "quantity": convert_value(pos.quantity),
                    "market": convert_value(pos.market),
                    "available_quantity": convert_value(pos.available_quantity),
                    "cost_price": convert_value(pos.cost_price)
                }
                
                # 处理可选字段
                if hasattr(pos, 'init_quantity') and pos.init_quantity is not None:
                    stock_info['init_quantity'] = convert_value(pos.init_quantity)
                
                channel_data["stock_info"].append(stock_info)
            
            result["data"]["list"].append(channel_data)
        
        return result
        
    except AttributeError as e:
        logger.error(f"处理持仓数据时属性错误: {e}")
        result["code"] = -1
        result["data"] = {"error": str(e)}
        return result
    except Exception as e:
        logger.error(f"转换持仓数据时发生错误: {e}")
        result["code"] = -1
        result["data"] = {"error": str(e)}
        return result

def display_positions_summary(positions_data):
    """显示持仓摘要信息"""
    if positions_data["code"] != 0:
        logger.error(f"获取持仓数据失败: {positions_data['data'].get('error', '未知错误')}")
        return
    
    all_stocks = []
    total_value = 0.0
    
    # 收集所有股票信息
    for channel in positions_data["data"]["list"]:
        all_stocks.extend(channel["stock_info"])
    
    # 计算统计信息并显示
    print(f"\n{'='*60}")
    print(f"{'持仓概览':^60}")
    print(f"{'='*60}")
    print(f"{'股票代码':<15}{'股票名称':<25}{'持仓数量':<12}{'成本价':<10}")
    print(f"{'-'*60}")
    
    for stock in all_stocks:
        symbol = stock.get('symbol', '未知')
        name = stock.get('symbol_name', '未知名称')
        quantity = stock.get('quantity', 0)
        cost_price = stock.get('cost_price', 0)
        currency = stock.get('currency', '')
        
        # 尝试计算持仓价值（如果有足够信息）
        position_value = float(quantity) * float(cost_price) if quantity and cost_price else 0
        total_value += position_value
        
        # 格式化输出，控制名称长度
        name_display = (name[:22] + '...') if len(name) > 25 else name
        print(f"{symbol:<15}{name_display:<25}{quantity:<12}{cost_price:<10}{currency}")
    
    print(f"{'-'*60}")
    print(f"持仓总数: {len(all_stocks)}只")
    print(f"{'='*60}")

def main():
    """主函数"""
    try:
        # 加载配置
        config_data = load_config()
        
        # 创建TradeContext
        ctx = create_trade_context(config_data)
        
        # 获取持仓信息
        logger.info("正在获取持仓信息...")
        resp = ctx.stock_positions()
        
        # 转换为API文档格式的字典
        positions_data = positions_to_dict(resp)
        
        # 打印完整的JSON格式（可选，用于调试）
        print("\n完整持仓数据 (JSON格式):")
        print(json.dumps(positions_data, ensure_ascii=False, indent=2))
        
        # 显示格式化的持仓摘要
        display_positions_summary(positions_data)
        
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        raise

if __name__ == "__main__":
    main()
