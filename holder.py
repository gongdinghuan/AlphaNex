from decimal import Decimal
# 移除已弃用的symbol模块导入
from longport.openapi import TradeContext, QuoteContext, Config, OrderType, OrderSide, TimeInForceType
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

def create_contexts(config_data, only_trade=False):
    """创建TradeContext和可选的QuoteContext实例，添加增强的重试机制和资源管理
    
    Args:
        config_data: 配置数据
        only_trade: 是否只创建TradeContext，默认为False
        
    Returns:
        tuple: (trade_ctx, quote_ctx) 或 (trade_ctx, None)
    """
    max_retries = 5
    base_retry_interval = 5  # 基础重试间隔秒数
    
    for attempt in range(max_retries):
        try:
            config = Config(
                app_key=config_data['longport']['app_key'],
                app_secret=config_data['longport']['app_secret'],
                access_token=config_data['longport']['access_token']
            )
            
            # 创建TradeContext
            logger.info(f"正在创建TradeContext，尝试次数: {attempt + 1}")
            trade_ctx = TradeContext(config)
            logger.info("TradeContext创建成功")
            
            # 如果只需要TradeContext，直接返回
            if only_trade:
                logger.info("仅创建TradeContext模式")
                return trade_ctx, None
            
            # 否则尝试创建QuoteContext
            try:
                logger.info("正在创建QuoteContext...")
                quote_ctx = QuoteContext(config)
                logger.info("QuoteContext创建成功")
                return trade_ctx, quote_ctx
            except Exception as quote_e:
                logger.warning(f"创建QuoteContext失败: {quote_e}，仅返回TradeContext")
                return trade_ctx, None
                
        except KeyError as e:
            logger.error(f"配置文件缺少必要的密钥: {e}")
            raise
        except Exception as e:
            if "connections limitation" in str(e) and attempt < max_retries - 1:
                # 指数退避策略，每次重试间隔增加
                retry_interval = base_retry_interval * (2 ** attempt)
                logger.warning(f"创建Context实例失败，连接数限制被达到，将在{retry_interval}秒后重试: {e}")
                logger.info(f"尝试次数: {attempt + 1}/{max_retries}")
                import time
                time.sleep(retry_interval)
            else:
                logger.error(f"创建Context实例失败: {e}")
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

def get_real_time_quotes(quote_ctx, symbols):
    """
    获取实时行情数据 - 优化版本，减少连接使用
    
    Args:
        quote_ctx: QuoteContext实例
        symbols: 股票代码列表
    
    Returns:
        dict: 以股票代码为键的行情数据字典
    """
    if not symbols:
        logger.warning("没有股票代码需要获取行情数据")
        return {}
    
    # 只获取必要的行情数据，减少连接负载
    quote_map = {}
    
    try:
        logger.info(f"获取行情数据，股票数量: {len(symbols)}")
        
        # 一次性获取所有股票行情，LongPort API应该能够处理这个请求
        quotes = quote_ctx.quote(symbols)
        
        # 处理返回结果
        for quote in quotes:
            symbol = str(quote.symbol)
            last_price = float(quote.last_done) if hasattr(quote, 'last_done') and quote.last_done else None
            prev_close = float(quote.prev_close) if hasattr(quote, 'prev_close') and quote.prev_close else None
            
            # 计算涨跌幅
            change_percent = None
            if last_price and prev_close and prev_close > 0:
                change_percent = ((last_price - prev_close) / prev_close) * 100
            
            # 只存储必要的数据
            quote_map[symbol] = {
                'last_price': last_price,
                'prev_close': prev_close,
                'change_percent': change_percent
            }
            logger.debug(f"股票 {symbol} 的行情数据: 现价={last_price}, 昨收={prev_close}, 涨跌幅={change_percent}%")
        
        # 检查是否有股票没有获取到行情
        missing_symbols = [s for s in symbols if s not in quote_map]
        if missing_symbols:
            logger.warning(f"以下股票未获取到行情数据: {missing_symbols}")
        
        # 只返回有效数据的条目
        valid_quote_map = {k: v for k, v in quote_map.items() if v['last_price'] is not None}
        logger.info(f"行情数据获取完成，成功数量: {len(valid_quote_map)}/{len(symbols)}")
        return valid_quote_map
        
    except Exception as e:
        logger.error(f"获取行情数据失败: {e}")
        return {}

def display_positions_summary(positions_data, quote_map=None):
    """显示持仓摘要信息"""
    if positions_data["code"] != 0:
        logger.error(f"获取持仓数据失败: {positions_data['data'].get('error', '未知错误')}")
        return
    
    all_stocks = []
    total_cost_value = 0.0
    total_market_value = 0.0
    
    # 收集所有股票信息
    for channel in positions_data["data"]["list"]:
        all_stocks.extend(channel["stock_info"])
    
    # 记录行情数据状态
    has_quote_data = quote_map and len(quote_map) > 0
    if not has_quote_data:
        logger.warning("未获取到实时行情数据，将使用成本价替代现价")
    else:
        logger.info(f"成功获取了 {len(quote_map)} 只股票的实时行情数据")
    
    # 计算统计信息并显示
    print(f"\n{'='*90}")
    print(f"{'持仓概览':^90}")
    print(f"{'='*90}")
    
    # 增加现价列
    print(f"{'股票代码':<15}{'股票名称':<20}{'持仓数量':<12}{'成本价':<10}{'现价':<10}{'涨跌幅':<8}{'市值':<12}{'盈亏':<10}")
    print(f"{'-'*90}")
    
    for stock in all_stocks:
        symbol = stock.get('symbol', '未知')
        name = stock.get('symbol_name', '未知名称')
        quantity = stock.get('quantity', 0)
        cost_price = stock.get('cost_price', 0)
        currency = stock.get('currency', '')
        
        # 尝试获取实时价格和涨跌幅
        last_price = None
        change_percent = None
        price_status = ""
        using_cost_price = False
        
        if quote_map and symbol in quote_map:
            last_price = quote_map[symbol]['last_price']
            change_percent = quote_map[symbol]['change_percent']
            price_status = "✓" if last_price is not None else "?"
        else:
            # 如果没有行情数据，使用成本价作为现价
            logger.debug(f"未找到股票 {symbol} 的行情数据，使用成本价替代")
            last_price = cost_price
            using_cost_price = True
            price_status = "(成本价)"
        
        # 计算持仓成本价值和市值
        cost_value = float(quantity) * float(cost_price) if quantity and cost_price else 0
        total_cost_value += cost_value
        
        # 使用last_price计算市值（可能是实时价或成本价）
        market_value = float(quantity) * float(last_price) if quantity and last_price else 0
        total_market_value += market_value
        
        # 计算盈亏
        profit_loss = market_value - cost_value
        profit_loss_percent = (profit_loss / cost_value * 100) if cost_value > 0 else 0
        
        # 格式化输出，控制名称长度
        name_display = (name[:17] + '...') if len(name) > 20 else name
        
        # 格式化现价显示
        price_display = f"{last_price:.2f}" if last_price is not None else "N/A"
        if using_cost_price:
            price_display += "(成本)"  # 标记使用的是成本价
        
        # 格式化涨跌幅显示
        if using_cost_price:
            change_display = "持平(成本)"  # 使用成本价时涨跌幅为0
        elif change_percent is not None:
            change_sign = '+' if change_percent > 0 else ''
            change_display = f"{change_sign}{change_percent:.2f}%"
            # 根据涨跌添加颜色标记
            if change_percent > 0:
                change_display += " ↑"
            elif change_percent < 0:
                change_display += " ↓"
        else:
            change_display = "N/A"
        
        # 格式化市值显示
        market_value_display = f"{market_value:,.2f}" if market_value is not None else "N/A"
        
        # 格式化盈亏显示
        profit_loss_sign = '+' if profit_loss > 0 else ''
        profit_loss_display = f"{profit_loss_sign}{profit_loss:,.2f}"
        # 根据盈亏添加颜色标记
        if profit_loss > 0:
            profit_loss_display += " (赚)"
        elif profit_loss < 0:
            profit_loss_display += " (亏)"
        else:
            profit_loss_display += " (持平)"
        
        print(f"{symbol:<15}{name_display:<20}{quantity:<12}{cost_price:<10}{price_display:<10}{change_display:<8}{market_value_display:<12}{profit_loss_display:<10}{currency} {price_status}")
    
    print(f"{'-'*90}")
    print(f"持仓总数: {len(all_stocks)}只")
    print(f"总成本价值: {total_cost_value:,.2f}")
    print(f"总市值: {total_market_value:,.2f}")
    
    # 计算并显示总盈亏
    total_profit_loss = total_market_value - total_cost_value
    total_profit_loss_percent = (total_profit_loss / total_cost_value * 100) if total_cost_value > 0 else 0
    profit_loss_sign = '+' if total_profit_loss > 0 else ''
    
    # 判断是否全部使用成本价计算
    if not has_quote_data:
        print(f"总盈亏: {profit_loss_sign}{total_profit_loss:,.2f} ({profit_loss_sign}{total_profit_loss_percent:.2f}%) [使用成本价计算]")
    else:
        print(f"总盈亏: {profit_loss_sign}{total_profit_loss:,.2f} ({profit_loss_sign}{total_profit_loss_percent:.2f}%)")
    
    # 显示行情数据状态统计
    if quote_map:
        success_count = sum(1 for symbol in [s.get('symbol') for s in all_stocks] 
                          if symbol in quote_map and quote_map[symbol]['last_price'] is not None)
        print(f"行情数据获取: {success_count}/{len(all_stocks)} 只股票成功")
    else:
        print("提示: 由于API连接限制，所有价格均使用成本价显示")
    
    print(f"{'='*90}")

def main():
    """主函数 - 使用优化的create_contexts函数，确保资源正确管理"""
    # 导入所需模块
    import traceback
    import sys
    import time
    import gc
    
    # 增加日志详细程度以便调试
    logging.getLogger('holder').setLevel(logging.INFO)
    
    trade_ctx = None
    quote_ctx = None
    
    try:
        # 加载配置
        config_data = load_config()
        logger.info("配置文件加载成功")
        
        # 使用优化的create_contexts函数，只创建TradeContext
        logger.info("正在创建TradeContext获取持仓信息...")
        trade_ctx, quote_ctx = create_contexts(config_data, only_trade=True)
        logger.info("TradeContext创建成功")
        
        # 获取持仓信息
        logger.info("正在获取持仓信息...")
        resp = trade_ctx.stock_positions()
        logger.info("持仓信息获取成功")
        
        # 转换为API文档格式的字典
        positions_data = positions_to_dict(resp)
        logger.info(f"持仓数据转换完成，共包含{len(positions_data['data']['list'])}个账户通道")
        
        # 收集所有股票代码
        all_stocks = []
        for channel in positions_data["data"]["list"]:
            all_stocks.extend(channel["stock_info"])
        
        logger.info(f"共有{len(all_stocks)}只持仓股票")
        
        # 提取股票代码列表
        symbols = [stock.get('symbol') for stock in all_stocks if stock.get('symbol')]
        logger.info(f"股票代码列表: {symbols}")
        
        # 尝试获取实时行情数据，但优雅处理可能的连接限制
        quote_map = {}
        
        # 清理TradeContext资源，为可能的QuoteContext创建释放连接
        if trade_ctx:
            logger.info("清理TradeContext资源，为获取行情数据做准备...")
            del trade_ctx
            trade_ctx = None
            gc.collect()
            time.sleep(5)  # 给服务器时间回收连接
        
        # 尝试创建QuoteContext获取行情数据
        try:
            logger.info("尝试创建QuoteContext获取实时行情数据...")
            # 使用新的配置对象创建QuoteContext
            config = Config(
                app_key=config_data['longport']['app_key'],
                app_secret=config_data['longport']['app_secret'],
                access_token=config_data['longport']['access_token']
            )
            
            # 创建一个临时的QuoteContext实例
            temp_quote_ctx = QuoteContext(config)
            quote_map = get_real_time_quotes(temp_quote_ctx, symbols)
            logger.info(f"行情数据获取完成，成功获取{len(quote_map)}只股票的行情")
            
            # 立即清理QuoteContext资源
            del temp_quote_ctx
            gc.collect()
            
        except Exception as quote_e:
            if "connections limitation" in str(quote_e):
                logger.warning("由于API连接限制，无法获取实时行情数据")
            else:
                logger.warning(f"获取行情数据时出错: {quote_e}")
            logger.info("将使用成本价替代现价显示")
        
        # 显示持仓摘要
        print("\n完整持仓数据 (JSON格式):")
        print(json.dumps(positions_data, ensure_ascii=False, indent=2))
        display_positions_summary(positions_data, quote_map)
        
        logger.info("程序执行完成")
        
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        logger.error(f"详细错误堆栈: {traceback.format_exc()}")
        sys.exit(1)
    
    finally:
        # 清理资源引用
        if trade_ctx:
            logger.info("删除TradeContext引用")
            del trade_ctx
        if quote_ctx:
            logger.info("删除QuoteContext引用")
            del quote_ctx
        
        # 强制垃圾回收
        logger.info("执行垃圾回收...")
        gc.collect()

if __name__ == "__main__":
    main()
