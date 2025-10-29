from decimal import Decimal
from longport.openapi import TradeContext, Config, OrderType, OrderSide, TimeInForceType
import yaml
import logging
from datetime import datetime
import sys
import prettytable

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从YAML文件读取配置
def load_config():
    """从配置文件加载LongPort API配置"""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        return config_data
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        raise

# 获取账户持仓
def get_positions(ctx):
    """获取账户所有持仓信息"""
    try:
        # 使用正确的方法获取持仓列表
        resp = ctx.stock_positions()
        # 提取所有持仓到列表
        positions = []
        for channel in resp.channels:
            positions.extend(channel.positions)
        logger.info(f"获取到 {len(positions)} 个持仓")
        return positions
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return []

# 卖出指定股票
def sell_stock(ctx, symbol, quantity):
    """以市价单卖出指定股票"""
    try:
        logger.info(f"准备卖出 {symbol}，数量: {quantity}")
        
        # 使用市价单卖出
        resp = ctx.submit_order(
            symbol,
            OrderType.MO,  # 市价单
            OrderSide.Sell,  # 卖出
            Decimal(str(quantity)),
            TimeInForceType.Day,  # 当日有效
            remark=f"批量卖出 {symbol}",
        )
        
        logger.info(f"卖出订单提交成功: {symbol}, 订单ID: {resp.order_id}")
        return resp
    except Exception as e:
        logger.error(f"卖出 {symbol} 失败: {e}")
        return None

# 获取订单列表
def get_order_list(ctx, status=None, symbol=None, show_all=False):
    """
    获取订单列表
    
    Args:
        ctx: TradeContext 对象
        status: 订单状态过滤（可选）
        symbol: 股票代码过滤（可选）
        show_all: 是否显示所有订单（包括历史订单）
    
    Returns:
        list: 订单列表
    """
    try:
        orders = []
        
        # 获取今日订单
        logger.info("尝试获取今日订单...")
        try:
            today_orders = ctx.today_orders()
            
            # 详细检查返回对象的结构
            logger.info(f"今日订单对象类型: {type(today_orders)}")
            
            # 检查对象的所有属性
            if hasattr(today_orders, '__dict__'):
                logger.debug(f"今日订单对象属性: {list(today_orders.__dict__.keys())}")
            else:
                logger.debug(f"今日订单对象可用属性和方法: {dir(today_orders)}")
            
            # 检查是否是列表类型
            if isinstance(today_orders, list):
                orders.extend(today_orders)
                logger.info(f"今日订单直接是列表，包含 {len(today_orders)} 个订单")
                
                # 记录第一个订单的结构信息用于调试
                if today_orders and len(today_orders) > 0:
                    first_order = today_orders[0]
                    if hasattr(first_order, '__dict__'):
                        logger.debug(f"第一个订单对象的属性: {list(first_order.__dict__.keys())}")
            # 检查是否有channels属性
            elif hasattr(today_orders, 'channels'):
                logger.info("今日订单对象有channels属性")
                # 检查channels是否是列表
                if isinstance(today_orders.channels, list):
                    for channel in today_orders.channels:
                        # 检查channel是否有orders属性
                        if hasattr(channel, 'orders'):
                            orders.extend(channel.orders)
                            logger.info(f"从channels中获取到 {len(channel.orders)} 个订单")
                # 检查channels是否直接有orders属性
                elif hasattr(today_orders.channels, 'orders'):
                    orders.extend(today_orders.channels.orders)
                    logger.info(f"从channels.orders中获取到 {len(today_orders.channels.orders)} 个订单")
            # 检查是否有orders属性
            elif hasattr(today_orders, 'orders'):
                orders.extend(today_orders.orders)
                logger.info(f"从orders属性中获取到 {len(today_orders.orders)} 个订单")
            else:
                # 尝试作为迭代器处理
                try:
                    iter_count = 0
                    for item in today_orders:
                        orders.append(item)
                        iter_count += 1
                        # 限制迭代次数以避免无限循环
                        if iter_count > 1000:
                            logger.warning("迭代订单数量超过1000，可能存在问题")
                            break
                    if iter_count > 0:
                        logger.info(f"成功将今日订单作为迭代器处理，获取到 {iter_count} 个订单")
                    else:
                        logger.warning("无法识别今日订单响应格式，尝试作为单个对象添加")
                        orders.append(today_orders)
                except Exception as inner_e:
                    logger.warning(f"无法迭代今日订单结果: {inner_e}")
        except Exception as inner_e:
            logger.error(f"获取今日订单失败: {inner_e}")
            import traceback
            logger.debug(f"详细错误信息: {traceback.format_exc()}")
        
        # 如果需要，也获取历史订单
        if show_all:
            logger.info("尝试获取历史订单...")
            try:
                history_orders = ctx.history_orders()
                
                # 详细检查历史订单对象的结构
                logger.info(f"历史订单对象类型: {type(history_orders)}")
                
                # 类似的结构检查逻辑
                if isinstance(history_orders, list):
                    orders.extend(history_orders)
                    logger.info(f"历史订单直接是列表，包含 {len(history_orders)} 个订单")
                elif hasattr(history_orders, 'channels'):
                    if isinstance(history_orders.channels, list):
                        for channel in history_orders.channels:
                            if hasattr(channel, 'orders'):
                                orders.extend(channel.orders)
                                logger.info(f"从历史订单channels中获取到 {len(channel.orders)} 个订单")
                    elif hasattr(history_orders.channels, 'orders'):
                        orders.extend(history_orders.channels.orders)
                        logger.info(f"从历史订单channels.orders中获取到 {len(history_orders.channels.orders)} 个订单")
                elif hasattr(history_orders, 'orders'):
                    orders.extend(history_orders.orders)
                    logger.info(f"从历史订单orders属性中获取到 {len(history_orders.orders)} 个订单")
                else:
                    # 尝试作为迭代器处理历史订单
                    try:
                        iter_count = 0
                        for item in history_orders:
                            orders.append(item)
                            iter_count += 1
                            if iter_count > 1000:
                                logger.warning("迭代历史订单数量超过1000，可能存在问题")
                                break
                        if iter_count > 0:
                            logger.info(f"成功将历史订单作为迭代器处理，获取到 {iter_count} 个订单")
                    except Exception as inner_e:
                        logger.warning(f"无法迭代历史订单结果: {inner_e}")
            except Exception as inner_e:
                logger.error(f"获取历史订单失败: {inner_e}")
                import traceback
                logger.debug(f"详细错误信息: {traceback.format_exc()}")
        
        logger.info(f"获取订单完成，原始订单数: {len(orders)}")
        
        # 验证并清理订单列表
        valid_orders = []
        for order in orders:
            try:
                # 验证订单对象的有效性
                if not hasattr(order, 'order_id'):
                    logger.warning(f"跳过无效订单对象(无order_id): {type(order)}")
                    continue
                valid_orders.append(order)
            except Exception as inner_e:
                logger.error(f"验证订单对象时出错: {inner_e}")
        
        logger.info(f"订单验证完成，有效订单数: {len(valid_orders)}")
        
        # 应用过滤条件
        if status:
            filtered_orders = []
            for order in valid_orders:
                try:
                    order_status = getattr(order, 'status', None)
                    if order_status is not None and str(order_status).upper() == status.upper():
                        filtered_orders.append(order)
                except Exception as inner_e:
                    logger.warning(f"过滤订单状态时出错: {inner_e}")
            valid_orders = filtered_orders
            logger.info(f"应用状态过滤后，订单数: {len(valid_orders)}")
        
        if symbol:
            filtered_orders = []
            for order in valid_orders:
                try:
                    order_symbol = getattr(order, 'symbol', None)
                    if order_symbol is not None and str(order_symbol).upper() == symbol.upper():
                        filtered_orders.append(order)
                except Exception as inner_e:
                    logger.warning(f"过滤订单股票代码时出错: {inner_e}")
            valid_orders = filtered_orders
            logger.info(f"应用股票代码过滤后，订单数: {len(valid_orders)}")
        
        logger.info(f"最终获取到 {len(valid_orders)} 个符合条件的订单")
        return valid_orders
    except Exception as e:
        logger.error(f"获取订单列表失败: {e}")
        import traceback
        logger.error(f"详细错误信息: {traceback.format_exc()}")
        return []

# 根据订单ID查询订单状态
def get_order_status(ctx, order_id):
    """
    获取指定订单的状态详情
    
    Args:
        ctx: TradeContext 对象
        order_id: 订单ID
    
    Returns:
        object: 订单详情对象
    """
    try:
        # 使用正确的order_detail方法
        logger.info(f"尝试使用 order_detail 方法获取订单 {order_id} 的详情")
        order = ctx.order_detail(order_id)
        
        if order:
            logger.info(f"成功获取订单 {order_id} 的详情")
        else:
            logger.warning(f"未找到订单 {order_id}")
        
        return order
    except Exception as e:
        logger.error(f"获取订单状态失败: {e}")
        return None

# 格式化订单状态显示
def format_order_status(order):
    """
    格式化订单状态信息为易读的字典
    
    Args:
        order: 订单对象
    
    Returns:
        格式化后的订单信息字典
    """
    try:
        # 获取订单ID
        order_id = str(getattr(order, 'order_id', 'N/A'))
        
        # 获取股票信息
        symbol = str(getattr(order, 'symbol', 'N/A'))
        stock_name = str(getattr(order, 'stock_name', 'N/A'))
        
        # 使用OrderFormatter格式化各种字段
        side = OrderFormatter.format_side(getattr(order, 'side', 'N/A'))
        order_type = OrderFormatter.format_order_type(getattr(order, 'order_type', 'N/A'))
        status = OrderFormatter.format_status(getattr(order, 'status', 'N/A'))
        
        # 获取价格信息 - 尝试多种可能的属性名
        submitted_price = 0
        executed_price = 0
        
        # 尝试获取提交价格
        for price_attr in ['submitted_price', 'price', 'order_price', 'limit_price']:
            if hasattr(order, price_attr):
                try:
                    submitted_price = float(getattr(order, price_attr, 0))
                    break
                except:
                    continue
        
        # 尝试获取成交价格
        for price_attr in ['executed_price', 'avg_price', 'filled_price']:
            if hasattr(order, price_attr):
                try:
                    executed_price = float(getattr(order, price_attr, 0))
                    break
                except:
                    continue
        
        # 获取数量信息 - 尝试多种可能的属性名
        submitted_quantity = 0
        executed_quantity = 0
        
        # 尝试获取提交数量
        for qty_attr in ['submitted_quantity', 'quantity', 'order_quantity', 'original_quantity']:
            if hasattr(order, qty_attr):
                try:
                    submitted_quantity = int(getattr(order, qty_attr, 0))
                    break
                except:
                    continue
        
        # 尝试获取成交数量
        for qty_attr in ['executed_quantity', 'filled_quantity', 'executed_qty']:
            if hasattr(order, qty_attr):
                try:
                    executed_quantity = int(getattr(order, qty_attr, 0))
                    break
                except:
                    continue
        
        # 获取时间信息（尝试多种可能的时间属性）
        submitted_at = "N/A"
        for time_attr in ['submitted_at', 'created_at', 'updated_at', 'timestamp']:
            time_value = getattr(order, time_attr, None)
            if time_value:
                try:
                    if isinstance(time_value, (int, float)):
                        submitted_at = datetime.fromtimestamp(int(time_value)).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        submitted_at = str(time_value)
                    break
                except Exception as e:
                    logger.warning(f"格式化时间出错: {e}")
                    continue
        
        updated_at = submitted_at  # 默认使用提交时间
        for time_attr in ['updated_at', 'modified_at', 'last_updated']:
            time_value = getattr(order, time_attr, None)
            if time_value and time_value != getattr(order, 'submitted_at', None):
                try:
                    if isinstance(time_value, (int, float)):
                        updated_at = datetime.fromtimestamp(int(time_value)).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        updated_at = str(time_value)
                    break
                except Exception as e:
                    logger.warning(f"格式化更新时间出错: {e}")
                    continue
        
        # 获取其他信息
        currency = str(getattr(order, 'currency', 'N/A'))
        remark = str(getattr(order, 'remark', '无'))
        
        # 构建格式化的订单信息
        formatted = {
            "订单ID": order_id,
            "股票代码": symbol,
            "股票名称": stock_name,
            "买卖方向": side,
            "订单类型": order_type,
            "提交价格": submitted_price,
            "提交数量": submitted_quantity,
            "成交价格": executed_price,
            "成交数量": executed_quantity,
            "订单状态": status,
            "提交时间": submitted_at,
            "更新时间": updated_at,
            "币种": currency,
            "备注": remark
        }
        
        # 添加错误信息（如果有）
        if hasattr(order, 'msg') and getattr(order, 'msg', None):
            formatted["错误信息"] = str(getattr(order, 'msg'))
        
        return formatted
    except Exception as e:
        logger.error(f"格式化订单信息出错: {e}")
        # 返回基本信息作为后备
        return {
            "订单ID": str(getattr(order, 'order_id', 'N/A')),
            "股票代码": str(getattr(order, 'symbol', 'N/A')),
            "股票名称": str(getattr(order, 'stock_name', 'N/A')),
            "买卖方向": "未知",
            "订单类型": "未知",
            "提交价格": 0,
            "提交数量": 0,
            "成交价格": 0,
            "成交数量": 0,
            "订单状态": "未知",
            "提交时间": "未知",
            "更新时间": "未知",
            "币种": "N/A",
            "备注": "格式化出错"
        }

# 增强版订单状态格式化
class OrderFormatter:
    """
    订单信息格式化工具类
    提供订单状态、类型、方向等信息的格式化功能，并增强属性获取逻辑
    """
    # 订单状态映射表 - 扩展支持更多枚举类型和状态值
    STATUS_MAP = {
        # 直接状态值
        "New": "新建",
        "Filled": "已成交",
        "PartiallyFilled": "部分成交",
        "Cancelled": "已取消",
        "Rejected": "已拒绝",
        "PendingCancel": "取消中",
        "PendingReplace": "修改中",
        "Replaced": "已修改",
        "Expired": "已过期",
        "PendingNew": "待新建",
        "Suspended": "已暂停",
        "Calculated": "已计算",
        "DoneForDay": "当日完成",
        "Restated": "已重申",
        "PendingCancelReplace": "取消修改中",
        "NotReported": "未报",
        # 增加未报相关状态
        "PendingSubmit": "未报",
        "Submitted": "已报",
        "PreSubmitted": "预报",
        "Stopped": "已停止",
        "PartiallyFilledCancelPending": "部分成交已报取消",
        "CancelPending": "已报取消",
        "PartiallyFilledDoneForDay": "部分成交当日有效",
        # 枚举类型表示 - 支持不同格式的枚举
        "OrderStatus.New": "新建",
        "OrderStatus.Filled": "已成交",
        "OrderStatus.PartiallyFilled": "部分成交",
        "OrderStatus.Cancelled": "已取消",
        "OrderStatus.Rejected": "已拒绝",
        "OrderStatus.PendingCancel": "取消中",
        "OrderStatus.PendingReplace": "修改中",
        "OrderStatus.Replaced": "已修改",
        "OrderStatus.Expired": "已过期",
        "OrderStatus.PendingNew": "待新建",
        "OrderStatus.Suspended": "已暂停",
        "OrderStatus.Calculated": "已计算",
        "OrderStatus.DoneForDay": "当日完成",
        "OrderStatus.Restated": "已重申",
        "OrderStatus.PendingCancelReplace": "取消修改中",
        "OrderStatus.NotReported": "未报",
        # 增加未报相关状态的枚举映射
        "OrderStatus.PendingSubmit": "未报",
        "OrderStatus.Submitted": "已报",
        "OrderStatus.PreSubmitted": "预报",
        "OrderStatus.Stopped": "已停止",
        "OrderStatus.PartiallyFilledCancelPending": "部分成交已报取消",
        "OrderStatus.CancelPending": "已报取消",
        "OrderStatus.PartiallyFilledDoneForDay": "部分成交当日有效",
        # 支持其他可能的枚举格式
        "<OrderStatus.New>": "新建",
        "<OrderStatus.Filled>": "已成交",
        "<OrderStatus.PartiallyFilled>": "部分成交",
        # 数字状态码映射
        "0": "新建",
        "1": "已成交",
        "2": "部分成交",
        "3": "已取消",
        "4": "已拒绝",
        "5": "取消中"
    }
    
    # 订单类型映射表 - 扩展支持更多类型
    ORDER_TYPE_MAP = {
        # 简写形式
        "LO": "限价单",
        "MO": "市价单",
        "STP": "止损单",
        "STP_LIMIT": "止损限价单",
        "TRAIL": "跟踪止损单",
        "TRAIL_LIMIT": "跟踪止损限价单",
        # 完整形式
        "Limit": "限价单",
        "Market": "市价单",
        "Stop": "止损单",
        "StopLimit": "止损限价单",
        "MarketOnClose": "收盘市价单",
        "MarketOnOpen": "开盘市价单",
        "TrailingStop": "跟踪止损单",
        "TrailingStopLimit": "跟踪止损限价单",
        "LimitIfTouched": "限价触价单",
        # 枚举类型
        "OrderType.LIMIT": "限价单",
        "OrderType.LO": "限价单",
        "OrderType.MARKET": "市价单",
        "OrderType.MO": "市价单",
        "OrderType.STOP": "止损单",
        "OrderType.STP": "止损单",
        "OrderType.STOP_LIMIT": "止损限价单",
        "OrderType.STP_LIMIT": "止损限价单",
        "OrderType.MARKET_ON_CLOSE": "收盘市价单",
        "OrderType.MARKET_ON_OPEN": "开盘市价单",
        "OrderType.TRAIL": "跟踪止损单",
        "OrderType.TRAIL_LIMIT": "跟踪止损限价单",
        # 支持其他可能的枚举格式
        "<OrderType.LIMIT>": "限价单",
        "<OrderType.MARKET>": "市价单",
        # 数字类型码映射
        "1": "限价单",
        "2": "市价单",
        "3": "止损单",
        "4": "止损限价单"
    }
    
    # 买卖方向映射表 - 扩展支持更多格式
    SIDE_MAP = {
        # 基本方向
        "Buy": "买入",
        "Sell": "卖出",
        "BUY": "买入",
        "SELL": "卖出",
        "B": "买入",
        "S": "卖出",
        # 枚举类型
        "OrderSide.BUY": "买入",
        "OrderSide.Buy": "买入",
        "OrderSide.SELL": "卖出",
        "OrderSide.Sell": "卖出",
        "Side.BUY": "买入",
        "Side.Sell": "卖出",
        # 支持其他可能的枚举格式
        "<OrderSide.BUY>": "买入",
        "<OrderSide.SELL>": "卖出",
        # 数字方向码映射
        "1": "买入",
        "2": "卖出"
    }
    
    @classmethod
    def format_status(cls, status):
        """
        增强的订单状态格式化方法
        支持精确匹配、模糊匹配和关键字匹配，处理各种状态表示形式
        
        Args:
            status: 订单状态对象或字符串
            
        Returns:
            str: 格式化后的中文状态
        """
        try:
            if status is None:
                return "未知"
                
            status_str = str(status).strip()
            logger.debug(f"格式化订单状态: {status_str}")
            
            # 精确匹配
            if status_str in cls.STATUS_MAP:
                logger.debug(f"订单状态精确匹配: {status_str} -> {cls.STATUS_MAP[status_str]}")
                return cls.STATUS_MAP[status_str]
            
            # 移除可能的前缀和后缀
            clean_status = status_str.strip('<>[](){}')
            if clean_status in cls.STATUS_MAP:
                logger.debug(f"订单状态清理后匹配: {clean_status} -> {cls.STATUS_MAP[clean_status]}")
                return cls.STATUS_MAP[clean_status]
                
            # 模糊匹配
            for k, v in cls.STATUS_MAP.items():
                if k in status_str:
                    logger.debug(f"订单状态模糊匹配: {k} in {status_str} -> {v}")
                    return v
            
            # 转换为小写进行关键字匹配
            status_lower = status_str.lower()
            
            # 提取状态关键字 - 优化的关键字识别逻辑
            # 组合关键字优先级匹配
            if "part" in status_lower and "fill" in status_lower:
                return "部分成交"
            elif "fill" in status_lower:
                return "已成交"
            elif "pend" in status_lower:
                # 处理各种pending状态
                if "submit" in status_lower:
                    return "未报"
                elif "cancel" in status_lower:
                    return "已报取消"
                elif "replace" in status_lower:
                    return "修改中"
                return "待处理"
            elif "cancel" in status_lower:
                return "已取消"
            elif "reject" in status_lower:
                return "已拒绝"
            elif "expir" in status_lower:
                return "已过期"
            elif "suspend" in status_lower:
                return "已暂停"
            elif "done" in status_lower and "day" in status_lower:
                return "当日完成"
            elif "replace" in status_lower:
                return "已修改"
            elif "restat" in status_lower:
                return "已重申"
            elif "calcul" in status_lower:
                return "已计算"
            elif "submitt" in status_lower:
                # 更精确的提交状态识别
                if "pre" in status_lower:
                    return "预报"
                return "已报"
            elif "pre" in status_lower:
                return "预报"
            elif "stop" in status_lower:
                return "已停止"
            elif "notreported" in status_lower or "not_report" in status_lower or "not report" in status_lower:
                return "未报"
            elif "new" in status_lower:
                return "新建"
            
            # 尝试基本关键字匹配
            for keyword in ["New", "Filled", "PartiallyFilled", "Cancelled", "Rejected", 
                          "PendingCancel", "PendingReplace", "Expired", "NotReported"]:
                if keyword.lower() in status_lower:
                    result = cls.STATUS_MAP.get(keyword, status_str)
                    logger.debug(f"订单状态关键字匹配: {keyword} -> {result}")
                    return result
            
            logger.debug(f"订单状态未匹配到: {status_str}")
            return status_str
        except Exception as e:
            logger.error(f"格式化订单状态出错: {e}, 状态值: {status}")
            return "未知"
    
    @classmethod
    def format_order_type(cls, order_type):
        """
        格式化订单类型
        支持精确匹配和模糊匹配，处理各种订单类型表示形式
        
        Args:
            order_type: 订单类型对象或字符串
            
        Returns:
            str: 格式化后的中文订单类型
        """
        try:
            if order_type is None:
                return "未知"
                
            type_str = str(order_type).strip()
            logger.debug(f"格式化订单类型: {type_str}")
            
            # 精确匹配
            if type_str in cls.ORDER_TYPE_MAP:
                logger.debug(f"订单类型精确匹配: {type_str} -> {cls.ORDER_TYPE_MAP[type_str]}")
                return cls.ORDER_TYPE_MAP[type_str]
            
            # 移除可能的前缀和后缀
            clean_type = type_str.strip('<>[](){}')
            if clean_type in cls.ORDER_TYPE_MAP:
                logger.debug(f"订单类型清理后匹配: {clean_type} -> {cls.ORDER_TYPE_MAP[clean_type]}")
                return cls.ORDER_TYPE_MAP[clean_type]
                
            # 模糊匹配 - 优化的关键词匹配逻辑
            type_lower = type_str.lower()
            
            # 组合匹配优先级
            if "stop" in type_lower and "limit" in type_lower:
                return "止损限价单"
            elif "trail" in type_lower and "limit" in type_lower:
                return "跟踪止损限价单"
            elif "limit" in type_lower or "lo" in type_lower:
                return "限价单"
            elif "market" in type_lower or "mo" in type_lower:
                # 进一步细分市价单类型
                if "close" in type_lower:
                    return "收盘市价单"
                elif "open" in type_lower:
                    return "开盘市价单"
                return "市价单"
            elif "stop" in type_lower or "stp" in type_lower:
                return "止损单"
            elif "trail" in type_lower:
                return "跟踪止损单"
            elif "touch" in type_lower:
                return "限价触价单"
            
            logger.debug(f"订单类型未匹配到: {type_str}")
            return type_str
        except Exception as e:
            logger.error(f"格式化订单类型出错: {e}, 类型值: {order_type}")
            return "未知"
    
    @classmethod
    def format_side(cls, side):
        """
        格式化买卖方向
        支持精确匹配和模糊匹配，处理各种方向表示形式
        
        Args:
            side: 买卖方向对象或字符串
            
        Returns:
            str: 格式化后的中文买卖方向
        """
        try:
            if side is None:
                return "未知"
                
            side_str = str(side).strip()
            logger.debug(f"格式化买卖方向: {side_str}")
            
            # 精确匹配
            if side_str in cls.SIDE_MAP:
                logger.debug(f"买卖方向精确匹配: {side_str} -> {cls.SIDE_MAP[side_str]}")
                return cls.SIDE_MAP[side_str]
            
            # 移除可能的前缀和后缀
            clean_side = side_str.strip('<>[](){}')
            if clean_side in cls.SIDE_MAP:
                logger.debug(f"买卖方向清理后匹配: {clean_side} -> {cls.SIDE_MAP[clean_side]}")
                return cls.SIDE_MAP[clean_side]
                
            # 模糊匹配
            side_lower = side_str.lower()
            if "buy" in side_lower or side_str == "B":
                return "买入"
            elif "sell" in side_lower or side_str == "S":
                return "卖出"
            
            logger.debug(f"买卖方向未匹配到: {side_str}")
            return side_str
        except Exception as e:
            logger.error(f"格式化买卖方向出错: {e}, 方向值: {side}")
            return "未知"
    
    @classmethod
    def get_order_value(cls, order, attr_name, default=0):
        """
        从订单对象中获取值，尝试多种可能的属性名
        增强的属性获取逻辑，支持多种命名规范和属性变体
        
        Args:
            order: 订单对象
            attr_name: 要获取的属性名
            default: 默认值
            
        Returns:
            获取到的值或默认值
        """
        logger.debug(f"从订单对象获取属性值: {attr_name}")
        
        if order is None:
            logger.warning(f"尝试从None对象获取属性: {attr_name}")
            return default
            
        # 定义属性名变体生成函数
        def get_attr_variants(base_attr):
            """生成属性名的各种变体"""
            variants = [
                base_attr,                      # 原始名称
                base_attr.lower(),              # 全小写
                base_attr.upper(),              # 全大写
                base_attr.replace('_', ''),     # 移除下划线
                base_attr.replace('-', ''),     # 移除连字符
                base_attr.replace('_', '-')     # 下划线替换为连字符
            ]
            
            # 添加驼峰命名变体
            if '_' in base_attr:
                parts = base_attr.split('_')
                # 小驼峰
                camel_case = parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])
                variants.append(camel_case)
                # 大驼峰
                pascal_case = ''.join(word.capitalize() for word in parts)
                variants.append(pascal_case)
            
            # 添加首字母大写变体
            variants.append(base_attr.capitalize())
            
            return list(set(variants))  # 去重
        
        # 生成属性名变体
        possible_attrs = get_attr_variants(attr_name)
        logger.debug(f"尝试的属性名变体: {possible_attrs}")
        
        # 尝试直接从对象获取属性
        for attr in possible_attrs:
            try:
                if hasattr(order, attr):
                    value = getattr(order, attr)
                    logger.debug(f"成功获取属性 {attr}: {value}")
                    
                    if value is None:
                        continue
                        
                    # 尝试转换为数值
                    if isinstance(value, (int, float)):
                        return value
                    try:
                        # 处理字符串表示的数值
                        if isinstance(value, str):
                            # 清理字符串
                            clean_value = value.strip().replace(',', '')
                            return float(clean_value)
                        return float(value)
                    except (ValueError, TypeError):
                        # 如果转换失败，返回原始值
                        return value
            except Exception as e:
                logger.warning(f"获取属性 {attr} 时出错: {e}")
                continue
        
        # 针对特定属性类型的特殊处理
        if attr_name == 'price' or 'price' in attr_name.lower():
            logger.debug(f"尝试获取价格相关属性")
            price_attrs = ['submitted_price', 'executed_price', 'avg_price', 'filled_price', 
                         'price', 'order_price', 'limit_price', 'stop_price']
            for price_attr in price_attrs:
                value = cls.get_order_value(order, price_attr, None)
                if value is not None:
                    return value
        
        if attr_name == 'quantity' or 'quantity' in attr_name.lower() or 'qty' in attr_name.lower():
            logger.debug(f"尝试获取数量相关属性")
            qty_attrs = ['submitted_quantity', 'executed_quantity', 'filled_quantity', 
                        'quantity', 'qty', 'order_quantity', 'original_quantity', 
                        'filled_qty', 'executed_qty']
            for qty_attr in qty_attrs:
                value = cls.get_order_value(order, qty_attr, None)
                if value is not None:
                    return value
        
        if 'time' in attr_name.lower() or 'date' in attr_name.lower():
            logger.debug(f"尝试获取时间相关属性")
            time_attrs = ['created_at', 'submitted_at', 'updated_at', 'timestamp', 
                         'executed_at', 'filled_at', 'cancelled_at', 'rejected_at']
            for time_attr in time_attrs:
                if hasattr(order, time_attr):
                    value = getattr(order, time_attr)
                    if value is not None:
                        return value
        
        # 尝试从字典或类似字典的对象中获取
        try:
            # 检查是否有__dict__属性
            if hasattr(order, '__dict__') and attr_name in order.__dict__:
                return order.__dict__[attr_name]
            
            # 检查是否支持字典访问
            if hasattr(order, 'get') and callable(order.get):
                value = order.get(attr_name)
                if value is not None:
                    return value
                    
            # 检查是否支持索引访问
            if isinstance(order, dict) and attr_name in order:
                return order[attr_name]
                
        except Exception as e:
            logger.warning(f"尝试从字典访问 {attr_name} 时出错: {e}")
        
        logger.debug(f"未找到属性 {attr_name}，返回默认值: {default}")
        return default

# 可视化显示订单列表
def display_orders(orders):
    """
    使用prettytable可视化显示订单列表
    
    Args:
        orders: 订单列表
    """
    if not orders:
        print("没有找到订单")
        return
    
    logger.info(f"准备显示 {len(orders)} 个订单")
    
    # 创建表格
    table = prettytable.PrettyTable()
    table.field_names = ["订单ID", "股票代码", "股票名称", "买卖方向", "订单类型", 
                        "提交价格", "提交数量", "成交数量", "订单状态", "提交时间"]
    
    # 设置表格样式
    table.align["订单ID"] = "l"
    table.align["股票代码"] = "l"
    table.align["股票名称"] = "l"
    table.align["买卖方向"] = "l"
    table.align["订单类型"] = "l"
    table.align["订单状态"] = "l"
    table.align["提交时间"] = "l"
    
    # 添加数据
    success_count = 0
    
    for order in orders:
        try:
            # 使用增强的格式化函数
            formatted = format_order_status(order)
            
            # 确保所有关键字段都使用OrderFormatter处理
            formatted["订单状态"] = OrderFormatter.format_status(getattr(order, 'status', 'N/A'))
            formatted["买卖方向"] = OrderFormatter.format_side(getattr(order, 'side', 'N/A'))
            formatted["订单类型"] = OrderFormatter.format_order_type(getattr(order, 'order_type', 'N/A'))
            
            # 添加到表格
            table.add_row([
                formatted["订单ID"][:10] + "..." if len(formatted["订单ID"]) > 13 else formatted["订单ID"],
                formatted["股票代码"],
                formatted["股票名称"],
                formatted["买卖方向"],
                formatted["订单类型"],
                formatted["提交价格"],
                formatted["提交数量"],
                formatted["成交数量"],
                formatted["订单状态"],
                formatted["提交时间"]
            ])
            success_count += 1
        except Exception as e:
            logger.error(f"添加订单到表格时出错: {e}")
            continue
    
    # 打印表格
    print("\n" + table.get_string())
    
    # 安全计算订单统计信息
    filled_count = 0
    partial_count = 0
    new_count = 0
    cancelled_count = 0
    pending_count = 0
    not_reported_count = 0
    
    for order in orders:
        try:
            # 使用OrderFormatter来判断状态
            status = OrderFormatter.format_status(getattr(order, 'status', None))
            if "已成交" in status:
                filled_count += 1
            elif "部分成交" in status:
                partial_count += 1
            elif "新建" in status:
                new_count += 1
            elif "已取消" in status:
                cancelled_count += 1
            elif "未报" in status:
                not_reported_count += 1
            elif "待处理" in status or "待新建" in status or "已报" in status or "预报" in status:
                pending_count += 1
        except Exception as e:
            logger.warning(f"统计订单状态时出错: {e}")
    
    print(f"\n订单统计: 总订单 {len(orders)} 个, 已成交 {filled_count} 个, 部分成交 {partial_count} 个, "
          f"新建 {new_count} 个, 已取消 {cancelled_count} 个, 未报 {not_reported_count} 个, 待处理 {pending_count} 个")
    
    if success_count < len(orders):
        print(f"注意: 成功显示 {success_count} 个订单, 有 {len(orders) - success_count} 个订单处理失败")

# 显示单个订单详情
def display_order_detail(order):
    """
    显示单个订单的详细信息
    
    Args:
        order: 订单对象
    """
    if not order:
        print("未找到订单信息")
        return
    
    formatted = format_order_status(order)
    
    print("\n订单详细信息:")
    print("-" * 60)
    
    # 按照重要性排序显示订单信息
    important_fields = ["订单ID", "股票代码", "股票名称", "买卖方向", "订单状态"]
    other_fields = [f for f in formatted.keys() if f not in important_fields]
    
    for field in important_fields + sorted(other_fields):
        print(f"{field:<12}: {formatted[field]}")
    
    print("-" * 60)

# 卖出所有持仓
def sell_all_positions():
    """卖出账户下所有持仓"""
    try:
        # 加载配置
        config_data = load_config()
        
        # 创建Config对象
        config = Config(
            app_key=config_data['longport']['app_key'],
            app_secret=config_data['longport']['app_secret'],
            access_token=config_data['longport']['access_token']
        )
        
        # 创建TradeContext
        ctx = TradeContext(config)
        logger.info("成功创建交易上下文")
        
        # 获取持仓
        positions = get_positions(ctx)
        
        # 如果没有持仓
        if not positions:
            logger.info("账户没有持仓")
            return
        
        # 遍历持仓并卖出
        success_count = 0
        fail_count = 0
        
        for position in positions:
            symbol = position.symbol
            # 获取可用数量（可卖出的数量）
            available_quantity = position.available_quantity
            
            if available_quantity > 0:
                logger.info(f"找到可卖出持仓: {symbol}, 可用数量: {available_quantity}")
                result = sell_stock(ctx, symbol, available_quantity)
                if result:
                    success_count += 1
                else:
                    fail_count += 1
            else:
                logger.warning(f"持仓 {symbol} 没有可卖出的数量，可用: {available_quantity}")
        
        logger.info(f"批量卖出操作完成: 成功 {success_count} 个, 失败 {fail_count} 个")
        
    except Exception as e:
        logger.error(f"批量卖出过程中发生错误: {e}")

# 列出TradeContext对象的所有可用方法
def explore_trade_context(ctx):
    """
    探索TradeContext对象的所有可用方法和属性
    
    Args:
        ctx: TradeContext 对象
    """
    try:
        # 获取所有方法和属性
        attrs = dir(ctx)
        
        print("\nTradeContext 对象可用的方法和属性:")
        print("-" * 60)
        
        # 过滤出方法（以小写字母开头且不是私有方法）
        methods = []
        for attr in attrs:
            if not attr.startswith('_') and callable(getattr(ctx, attr)):
                methods.append(attr)
        
        # 打印方法列表
        print("可用方法:")
        for method in sorted(methods):
            print(f"  - {method}")
        
        print("-" * 60)
        print(f"总共找到 {len(methods)} 个方法")
        
    except Exception as e:
        logger.error(f"探索TradeContext对象失败: {e}")

# 主函数，支持不同操作模式
def main():
    """
    主函数，支持多种操作模式
    Usage:
        python order.py sell_all      # 卖出所有持仓
        python order.py list_orders   # 列出所有订单
        python order.py order_status <order_id>  # 查询特定订单状态
        python order.py explore       # 探索TradeContext可用方法
    """
    try:
        # 加载配置
        config_data = load_config()
        
        # 创建Config对象
        config = Config(
            app_key=config_data['longport']['app_key'],
            app_secret=config_data['longport']['app_secret'],
            access_token=config_data['longport']['access_token']
        )
        
        # 创建TradeContext
        ctx = TradeContext(config)
        logger.info("成功创建交易上下文")
        
        # 处理命令行参数
        if len(sys.argv) < 2:
            print("请指定操作模式")
            print(main.__doc__)
            return
        
        mode = sys.argv[1]
        
        if mode == "sell_all":
            logger.info("开始执行批量卖出所有持仓操作")
            sell_all_positions()
            logger.info("批量卖出操作结束")
        elif mode == "list_orders":
            # 获取并显示订单列表
            logger.info("开始获取订单列表")
            
            # 解析可选参数
            status = None
            symbol = None
            show_all = False
            
            for i in range(2, len(sys.argv)):
                if sys.argv[i].startswith("status="):
                    status = sys.argv[i].split("=")[1]
                elif sys.argv[i].startswith("symbol="):
                    symbol = sys.argv[i].split("=")[1]
                elif sys.argv[i] == "--all":
                    show_all = True
            
            orders = get_order_list(ctx, status=status, symbol=symbol, show_all=show_all)
            display_orders(orders)
            logger.info("获取订单列表完成")
        elif mode == "order_status":
            # 查询特定订单状态
            if len(sys.argv) < 3:
                print("请提供订单ID")
                print(main.__doc__)
                return
            
            order_id = sys.argv[2]
            logger.info(f"开始查询订单 {order_id} 状态")
            
            order = get_order_status(ctx, order_id)
            display_order_detail(order)
            logger.info(f"查询订单 {order_id} 状态完成")
        elif mode == "explore":
            # 探索TradeContext对象的方法
            logger.info("开始探索TradeContext对象")
            explore_trade_context(ctx)
            logger.info("探索完成")
        else:
            print(f"未知的操作模式: {mode}")
            print(main.__doc__)
            
    except Exception as e:
        logger.error(f"程序执行过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()