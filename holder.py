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

def create_contexts(config_data):
    """创建TradeContext和QuoteContext实例"""
    try:
        config = Config(
            app_key=config_data['longport']['app_key'],
            app_secret=config_data['longport']['app_secret'],
            access_token=config_data['longport']['access_token']
        )
        trade_ctx = TradeContext(config)
        quote_ctx = QuoteContext(config)
        return trade_ctx, quote_ctx
    except KeyError as e:
        logger.error(f"配置文件缺少必要的密钥: {e}")
        raise
    except Exception as e:
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
    """获取股票的实时行情数据"""
    if not symbols:
        logger.warning("没有股票代码需要获取行情数据")
        return {}
    
    try:
        logger.info(f"正在获取实时行情数据，股票代码数量: {len(symbols)}, 代码列表: {symbols}")
        
        # 尝试获取行情数据
        quotes = quote_ctx.quote(symbols)
        logger.info(f"成功获取到{len(quotes)}只股票的行情数据")
        
        # 创建symbol到quote的映射，方便查询
        quote_map = {}
        for quote in quotes:
            try:
                symbol = str(quote.symbol)
                # 详细记录每只股票的数据，使用安全的属性访问方式
                last_price = float(quote.last_done) if hasattr(quote, 'last_done') and quote.last_done else None
                prev_close = float(quote.prev_close) if hasattr(quote, 'prev_close') and quote.prev_close else None
                
                # 计算涨跌幅（因为对象没有change_percent属性）
                change_percent = None
                if last_price and prev_close and prev_close > 0:
                    change_percent = ((last_price - prev_close) / prev_close) * 100
                
                # 安全地检查是否有其他可用的价格属性
                if last_price is None:
                    # 尝试其他可能的价格属性名称
                    if hasattr(quote, 'price'):
                        last_price = float(quote.price) if quote.price else None
                    elif hasattr(quote, 'last_price'):
                        last_price = float(quote.last_price) if quote.last_price else None
                
                quote_map[symbol] = {
                    'last_price': last_price,
                    'prev_close': prev_close,
                    'change_percent': change_percent
                }
                logger.debug(f"股票 {symbol} 的行情数据: 现价={last_price}, 昨收={prev_close}, 涨跌幅={change_percent}%")
            except Exception as e:
                logger.error(f"处理股票 {getattr(quote, 'symbol', '未知')} 的行情数据时出错: {e}")
                # 尝试使用更基本的方法提取数据
                try:
                    symbol = str(getattr(quote, 'symbol', '未知'))
                    # 尝试获取任何可用的价格信息
                    price_attrs = ['last_done', 'price', 'last_price']
                    last_price = None
                    for attr in price_attrs:
                        if hasattr(quote, attr) and getattr(quote, attr):
                            try:
                                last_price = float(getattr(quote, attr))
                                break
                            except (ValueError, TypeError):
                                continue
                    
                    prev_close = None
                    if hasattr(quote, 'prev_close') and getattr(quote, 'prev_close'):
                        try:
                            prev_close = float(getattr(quote, 'prev_close'))
                        except (ValueError, TypeError):
                            pass
                    
                    # 计算涨跌幅
                    change_percent = None
                    if last_price and prev_close and prev_close > 0:
                        change_percent = ((last_price - prev_close) / prev_close) * 100
                    
                    if last_price:
                        quote_map[symbol] = {
                            'last_price': last_price,
                            'prev_close': prev_close,
                            'change_percent': change_percent
                        }
                        logger.debug(f"使用备选方法成功获取股票 {symbol} 的价格: {last_price}")
                except Exception as backup_e:
                    logger.error(f"备选方法也失败: {backup_e}")
        
        # 检查是否有股票没有获取到行情
        missing_symbols = [s for s in symbols if s not in quote_map]
        if missing_symbols:
            logger.warning(f"以下股票未获取到行情数据: {missing_symbols}")
        
        # 只返回有效数据的条目
        valid_quote_map = {k: v for k, v in quote_map.items() if v['last_price'] is not None}
        logger.info(f"成功提取了 {len(valid_quote_map)} 只股票的有效行情数据")
        return valid_quote_map
    except Exception as e:
        logger.error(f"获取实时行情数据失败: {e}")
        # 添加详细的错误信息和调试信息
        import traceback
        logger.debug(f"详细错误信息: {traceback.format_exc()}")
        
        # 尝试使用备选方案 - 逐个获取股票行情（如果批量获取失败）
        try:
            quote_map = {}
            for symbol in symbols:
                try:
                    logger.info(f"尝试单独获取股票 {symbol} 的行情数据")
                    quotes = quote_ctx.quote([symbol])
                    if quotes and len(quotes) > 0:
                        quote = quotes[0]
                        symbol_str = str(getattr(quote, 'symbol', symbol))
                        
                        # 安全地获取价格信息
                        last_price = float(quote.last_done) if hasattr(quote, 'last_done') and quote.last_done else None
                        prev_close = float(quote.prev_close) if hasattr(quote, 'prev_close') and quote.prev_close else None
                        
                        # 计算涨跌幅
                        change_percent = None
                        if last_price and prev_close and prev_close > 0:
                            change_percent = ((last_price - prev_close) / prev_close) * 100
                        
                        if last_price:
                            quote_map[symbol_str] = {
                                'last_price': last_price,
                                'prev_close': prev_close,
                                'change_percent': change_percent
                            }
                            logger.debug(f"成功单独获取股票 {symbol} 的行情数据: {last_price}")
                except Exception as single_e:
                    logger.error(f"单独获取股票 {symbol} 的行情数据失败: {single_e}")
            
            if quote_map:
                logger.info(f"备选方案成功获取了 {len(quote_map)} 只股票的行情数据")
            return quote_map
        except Exception as backup_e:
            logger.error(f"备选方案也失败: {backup_e}")
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
        logger.warning("未获取到实时行情数据，将只显示持仓基本信息")
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
        
        if quote_map and symbol in quote_map:
            last_price = quote_map[symbol]['last_price']
            change_percent = quote_map[symbol]['change_percent']
            price_status = "✓" if last_price is not None else "?"
        else:
            logger.debug(f"未找到股票 {symbol} 的行情数据")
        
        # 计算持仓成本价值和市值
        cost_value = float(quantity) * float(cost_price) if quantity and cost_price else 0
        total_cost_value += cost_value
        
        market_value = float(quantity) * float(last_price) if quantity and last_price else None
        if market_value is not None:
            total_market_value += market_value
        
        # 计算盈亏
        profit_loss = market_value - cost_value if market_value is not None else None
        profit_loss_percent = (profit_loss / cost_value * 100) if profit_loss is not None and cost_value > 0 else None
        
        # 格式化输出，控制名称长度
        name_display = (name[:17] + '...') if len(name) > 20 else name
        
        # 格式化现价显示
        price_display = f"{last_price:.2f}" if last_price is not None else "N/A"
        
        # 格式化涨跌幅显示
        change_display = "N/A"
        if change_percent is not None:
            change_sign = '+' if change_percent > 0 else ''
            change_display = f"{change_sign}{change_percent:.2f}%"
            # 根据涨跌添加颜色标记
            if change_percent > 0:
                change_display += " ↑"
            elif change_percent < 0:
                change_display += " ↓"
        
        # 格式化市值显示
        market_value_display = f"{market_value:,.2f}" if market_value is not None else "N/A"
        
        # 格式化盈亏显示
        if profit_loss is not None:
            profit_loss_sign = '+' if profit_loss > 0 else ''
            profit_loss_display = f"{profit_loss_sign}{profit_loss:,.2f}"
            # 根据盈亏添加颜色标记
            if profit_loss > 0:
                profit_loss_display += " (赚)"
            elif profit_loss < 0:
                profit_loss_display += " (亏)"
        else:
            profit_loss_display = "N/A"
        
        print(f"{symbol:<15}{name_display:<20}{quantity:<12}{cost_price:<10}{price_display:<10}{change_display:<8}{market_value_display:<12}{profit_loss_display:<10}{currency} {price_status}")
    
    print(f"{'-'*90}")
    print(f"持仓总数: {len(all_stocks)}只")
    print(f"总成本价值: {total_cost_value:,.2f}")
    if total_market_value > 0:
        print(f"总市值: {total_market_value:,.2f}")
        total_profit_loss = total_market_value - total_cost_value
        total_profit_loss_percent = (total_profit_loss / total_cost_value * 100) if total_cost_value > 0 else 0
        profit_loss_sign = '+' if total_profit_loss > 0 else ''
        print(f"总盈亏: {profit_loss_sign}{total_profit_loss:,.2f} ({profit_loss_sign}{total_profit_loss_percent:.2f}%)")
    
    # 显示行情数据状态统计
    if quote_map:
        success_count = sum(1 for symbol in [s.get('symbol') for s in all_stocks] 
                          if symbol in quote_map and quote_map[symbol]['last_price'] is not None)
        print(f"行情数据获取: {success_count}/{len(all_stocks)} 只股票成功")
    
    print(f"{'='*90}")

def main():
    """主函数"""
    try:
        # 增加日志详细程度以便调试
        logging.getLogger('holder').setLevel(logging.DEBUG)
        
        # 加载配置
        config_data = load_config()
        logger.info("配置文件加载成功")
        
        # 创建TradeContext和QuoteContext
        trade_ctx, quote_ctx = create_contexts(config_data)
        logger.info("成功创建TradeContext和QuoteContext实例")
        
        # 获取持仓信息
        logger.info("正在获取持仓信息...")
        resp = trade_ctx.stock_positions()
        logger.info("持仓信息获取成功")
        
        # 转换为API文档格式的字典
        positions_data = positions_to_dict(resp)
        logger.debug(f"持仓数据转换完成，共包含{len(positions_data['data']['list'])}个账户通道")
        
        # 收集所有股票代码
        all_stocks = []
        for channel in positions_data["data"]["list"]:
            all_stocks.extend(channel["stock_info"])
        
        symbols = [stock.get('symbol') for stock in all_stocks if stock.get('symbol')]
        logger.info(f"共发现{len(symbols)}只持仓股票")
        
        # 获取实时行情数据
        quote_map = None
        if symbols:
            logger.info("开始获取实时行情数据...")
            # 添加延迟以防API调用过于频繁
            import time
            time.sleep(0.5)  # 500ms延迟
            quote_map = get_real_time_quotes(quote_ctx, symbols)
            logger.info(f"实时行情数据获取完成，成功获取{len(quote_map) if quote_map else 0}只股票的行情")
        
        # 调试信息：打印quote_map内容
        if quote_map:
            logger.debug(f"行情数据映射内容: {json.dumps(quote_map, ensure_ascii=False, indent=2)}")
        
        # 打印完整的JSON格式（可选，用于调试）
        print("\n完整持仓数据 (JSON格式):")
        print(json.dumps(positions_data, ensure_ascii=False, indent=2))
        
        # 显示格式化的持仓摘要（包含现价）
        display_positions_summary(positions_data, quote_map)
        
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        import traceback
        logger.error(f"详细错误堆栈: {traceback.format_exc()}")
        raise

if __name__ == "__main__":
    main()
