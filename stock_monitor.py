#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票监控和自动交易系统

该脚本实现了一个基于LongPort API和DeepSeek AI的股票监控和自动交易系统。
主要功能包括：
1. 实时获取股票行情数据
2. 利用AI分析决策是否买卖或持有
3. 自动执行交易订单
4. 监控股价波动并发出警报
"""

# 导入所需模块
from decimal import Decimal  # 用于精确的十进制运算
import yaml                  # 用于读取配置文件
import time                 # 用于控制程序执行间隔
import logging              # 用于记录日志
import requests             # 用于向AI服务发送HTTP请求
import json                 # 用于处理JSON数据
import os                   # 用于操作系统相关功能
import re                   # 用于正则表达式匹配
from datetime import datetime  # 用于处理日期时间
import concurrent.futures   # 用于并行处理
import threading            # 用于线程同步

# 导入LongPort OpenAPI相关模块
from longport.openapi import QuoteContext, Config, TradeContext, Market, OrderType, OrderSide, TimeInForceType

# 从YAML文件读取配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config_data = yaml.safe_load(f)

# 创建全局配置对象和上下文对象
config = Config(
    app_key=config_data['longport']['app_key'],
    app_secret=config_data['longport']['app_secret'],
    access_token=config_data['longport']['access_token']
)

# 创建全局行情和交易上下文
ctx = QuoteContext(config)
trade_ctx = TradeContext(config)

# 配置日志系统
logging.basicConfig(
    level=logging.DEBUG,  # 设置日志级别为DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # 日志格式
    handlers=[
        logging.FileHandler("stock_monitor.log"),  # 输出到文件
        logging.StreamHandler()  # 输出到控制台
    ]
)
logger = logging.getLogger("StockMonitor")  # 创建日志记录器

# 导入defaultdict用于创建默认字典
from collections import defaultdict

class StockMonitor:
    """
    股票监控主类
    
    负责监控股票价格变化、调用AI进行分析决策、执行交易订单等功能
    """
    
    def __init__(self, config_file="config.yaml"):
        """初始化股票监控器
        
        Args:
            config_file (str): 配置文件路径，默认为"config.yaml"
        """
        self.config_file = config_file           # 配置文件路径
        self.config = self.load_config()        # 加载配置
        self.stock_data = {}                    # 存储各股票的监控数据
        # 初始化历史决策记忆
        self.decision_memory = {}               # 存储各股票的AI决策历史
        # 初始化交易记录（用于利润计算）
        self.transactions = []                  # 所有交易记录
        self.open_positions = defaultdict(list) # 当前未平仓的持仓，按股票代码分组
        self.transaction_history_file = "transaction_history.json"  # 交易历史保存文件
        # 线程锁，用于保护共享资源
        self.transaction_lock = threading.Lock()  # 保护交易记录
        self.position_lock = threading.Lock()     # 保护持仓信息
        self.memory_lock = threading.Lock()       # 保护决策记忆
        # 并行处理配置
        self.max_workers = min(10, len(self.config.get('stocks', [])) + 1)  # 最大线程数，不超过10
        
        self.initialize_stock_data()            # 初始化股票数据
        
        # 加载历史交易记录（如果存在）
        self.load_transactions()
        
        # 创建TradeContext实例
        self.config_obj = Config(
            app_key=self.config['longport']['app_key'],
            app_secret=self.config['longport']['app_secret'],
            access_token=self.config['longport']['access_token']
        )
        self.trade_ctx = TradeContext(self.config_obj)  # 交易上下文对象
        
        logger.info(f"股票监控器已初始化，监控股票数量: {len(self.config['stocks'])}")
        logger.info(f"已加载历史交易记录: {len(self.transactions)}笔")

    def save_transactions(self):
        """保存交易历史到文件
        
        将所有交易记录保存到JSON文件中，以便程序重启后可以恢复交易历史
        """
        try:
            with open(self.transaction_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.transactions, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"已保存交易历史，共 {len(self.transactions)} 笔交易")
        except Exception as e:
            logger.error(f"保存交易历史失败: {e}")
    
    def load_transactions(self):
        """从文件加载交易历史
        
        从JSON文件中读取之前保存的交易历史记录
        """
        try:
            if os.path.exists(self.transaction_history_file):
                with open(self.transaction_history_file, 'r', encoding='utf-8') as f:
                    self.transactions = json.load(f)
                
                # 重建未平仓记录
                self.open_positions = defaultdict(list)
                for transaction in self.transactions:
                    if transaction['action'] == 'buy' and not transaction.get('closed', False):
                        self.open_positions[transaction['symbol']].append(transaction)
                
                logger.info(f"已加载 {len(self.transactions)} 笔交易记录")
        except Exception as e:
            logger.error(f"加载交易历史失败: {e}")
            self.transactions = []
            self.open_positions = defaultdict(list)

    def calculate_profit(self, sell_transaction):
        """计算卖出交易的利润
        
        根据卖出交易信息，匹配合适的买入交易，计算利润
        
        Args:
            sell_transaction (dict): 卖出交易记录
            
        Returns:
            dict: 包含利润信息的字典
        """
        symbol = sell_transaction['symbol']
        sell_quantity = sell_transaction['quantity']
        sell_price = sell_transaction['price']
        remaining_quantity = sell_quantity
        
        profit_details = {
            'total_profit': 0,
            'total_profit_percent': 0,
            'matched_buys': [],
            'unmatched_quantity': 0
        }
        
        # 如果该股票没有未平仓记录，返回0利润
        if symbol not in self.open_positions or not self.open_positions[symbol]:
            profit_details['unmatched_quantity'] = sell_quantity
            logger.warning(f"卖出 {symbol} 时没有找到对应的买入记录，数量: {sell_quantity}")
            return profit_details
        
        # 尝试匹配买入记录（使用先进先出FIFO原则）
        matched_buys = []
        for buy_transaction in list(self.open_positions[symbol]):
            if remaining_quantity <= 0:
                break
                
            # 可以匹配的数量
            match_quantity = min(remaining_quantity, buy_transaction['quantity'])
            
            # 计算这部分匹配的利润
            buy_cost = buy_transaction['price'] * match_quantity
            sell_revenue = sell_price * match_quantity
            profit = sell_revenue - buy_cost
            profit_percent = (profit / buy_cost) * 100 if buy_cost > 0 else 0
            
            # 记录匹配信息
            match_info = {
                'buy_order_id': buy_transaction['order_id'],
                'buy_price': buy_transaction['price'],
                'match_quantity': match_quantity,
                'profit': profit,
                'profit_percent': profit_percent
            }
            matched_buys.append(match_info)
            
            # 更新利润总计
            profit_details['total_profit'] += profit
            
            # 更新买入记录的剩余数量
            remaining_quantity -= match_quantity
            
            # 如果买入记录全部匹配，标记为已平仓
            if match_quantity == buy_transaction['quantity']:
                buy_transaction['closed'] = True
                self.open_positions[symbol].remove(buy_transaction)
                
                # 更新交易历史中的记录
                for t in self.transactions:
                    if t['order_id'] == buy_transaction['order_id']:
                        t['closed'] = True
                        break
            else:
                # 部分匹配，更新买入记录数量
                buy_transaction['quantity'] -= match_quantity
                
                # 更新交易历史中的记录
                for t in self.transactions:
                    if t['order_id'] == buy_transaction['order_id']:
                        t['quantity'] -= match_quantity
                        break
        
        # 如果卖出数量没有完全匹配
        if remaining_quantity > 0:
            profit_details['unmatched_quantity'] = remaining_quantity
            logger.warning(f"卖出 {symbol} 有 {remaining_quantity} 股未找到匹配的买入记录")
        
        profit_details['matched_buys'] = matched_buys
        
        # 计算总收益率（如果有利润）
        if profit_details['total_profit'] != 0:
            total_buy_cost = sum(b['buy_price'] * b['match_quantity'] for b in matched_buys)
            if total_buy_cost > 0:
                profit_details['total_profit_percent'] = (profit_details['total_profit'] / total_buy_cost) * 100
        
        return profit_details

    def display_profit_report(self, report=None):
        """显示利润报告"""
        try:
            logger.info("开始显示利润报告...")
            
            # 如果没有提供报告，自动生成一个
            if report is None:
                logger.info("未提供报告，尝试生成...")
                report = self.generate_profit_report()
                logger.info("利润报告生成完成")
            
            # 确保report是有效的字典
            if not isinstance(report, dict):
                logger.error(f"利润报告格式无效: {type(report)}")
                return
            
            logger.info(f"利润报告包含以下键: {list(report.keys())}")
            
            # 使用get方法安全获取值，设置默认值
            total_tx = report.get('total_transactions', 0)
            realized_profit = report.get('realized_profit', 0.0)
            
            # 特别处理unrealized_profit键
            if 'unrealized_profit' not in report:
                logger.warning("报告中未找到'unrealized_profit'键，设置为0")
                unrealized_profit = 0.0
            else:
                unrealized_profit = report['unrealized_profit']
            
            profit_by_stock = report.get('profit_by_stock', {})
            transaction_details = report.get('transaction_details', [])
            
            print("\n===== 利润报告 =====")
            print(f"总交易数: {total_tx}")
            print(f"已实现利润: ${realized_profit:.2f}")
            print(f"未实现利润: ${unrealized_profit:.2f}")
            print(f"总利润: ${(realized_profit + unrealized_profit):.2f}")
            
            if profit_by_stock:
                print("\n各股票利润:")
                for stock, profit in profit_by_stock.items():
                    print(f"  {stock}: ${profit:.2f}")
            
            if transaction_details:
                print("\n最近交易详情:")
                # 只显示最近的10条交易
                for tx in transaction_details[-10:]:
                    stock_code = tx.get('stock_code', '未知')
                    tx_type = tx.get('transaction_type', '未知')
                    quantity = tx.get('quantity', 0)
                    price = tx.get('price', 0.0)
                    timestamp = tx.get('timestamp', '未知时间')
                    profit = tx.get('profit', 0.0)
                    
                    print(f"  [{timestamp}] {stock_code} - {tx_type} {quantity}股 @ ${price:.2f}")
                    if profit != 0:
                        print(f"    利润: ${profit:.2f}")
            
            print("====================\n")
            logger.info("利润报告显示完成")
        except KeyError as e:
            logger.error(f"显示利润报告时出现键错误: {e}")
        except Exception as e:
            logger.error(f"显示利润报告时出错: {str(e)}")
            logger.error(f"错误类型: {type(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    def generate_profit_report(self):
        """生成利润报告"""
        try:
            # 确保所有必要的字典都已初始化
            if not hasattr(self, 'transactions'):
                self.transactions = []
                self.logger.warning("交易记录列表未初始化，已创建空列表")
            
            if not hasattr(self, 'open_positions'):
                self.open_positions = defaultdict(list)
                self.logger.warning("未平仓持仓字典未初始化，已创建空字典")
            
            # 初始化报告数据结构
            report = {
                'total_transactions': 0,
                'realized_profit': 0.0,
                'unrealized_profit': 0.0,
                'profit_by_stock': defaultdict(float),
                'transaction_details': []
            }
            
            # 统计交易总数
            report['total_transactions'] = len(self.transactions)
            
            # 处理交易记录并累加利润
            for tx in self.transactions:
                stock_code = tx.get('symbol', '未知')
                tx_type = tx.get('action', '未知')  # 使用action字段作为交易类型
                
                # 累加每只股票的已实现利润
                if 'profit' in tx and tx['profit'] is not None:
                    report['profit_by_stock'][stock_code] += tx['profit']
                    report['realized_profit'] += tx['profit']
                
                # 添加交易详情
                report['transaction_details'].append({
                    'stock_code': stock_code,
                    'transaction_type': tx_type,
                    'quantity': tx.get('quantity', 0),
                    'price': tx.get('price', 0.0),
                    'timestamp': tx.get('timestamp', ''),
                    'profit': tx.get('profit', 0.0) if 'profit' in tx and tx['profit'] is not None else 0.0
                })
            
            # 计算未实现利润（当前设为0）
            report['unrealized_profit'] = 0.0
            
            return report
        except Exception as e:
            self.logger.error(f"生成利润报告时出错: {str(e)}")
            # 返回一个最小化的报告作为后备
            return {
                'total_transactions': 0,
                'realized_profit': 0.0,
                'unrealized_profit': 0.0,
                'profit_by_stock': {},
                'transaction_details': []
            }

    def load_config(self):
        """加载YAML配置文件
        
        Returns:
            dict: 配置信息字典
            
        Raises:
            Exception: 配置文件加载失败时抛出异常
        """
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"配置文件加载成功: {self.config_file}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
    
    def initialize_stock_data(self):
        """初始化股票数据字典
        
        根据配置文件中的股票列表，初始化每只股票的监控参数
        包括阈值、初始动作、前一次价格、上次警报时间和持仓等信息
        """
        for stock in self.config['stocks']:
            # 检查是否需要监控该股票（默认为True）
            if stock.get('watch', True):
                self.stock_data[stock['symbol']] = {
                    'threshold': stock.get('threshold', 3.0),      # 价格变动警报阈值（百分比）
                    'initial_action': stock.get('initial_action', 'hold'),  # 初始动作
                    'previous_price': None,                       # 前一次记录的价格
                    'last_alert_time': None,                      # 上次发出警报的时间
                    'position': 0                                 # 持仓价值
                }
                # 初始化该股票的历史决策记忆
                self.decision_memory[stock['symbol']] = []

    def quote_to_dict(self, quote):
        """将SecurityQuote对象转换为字典
        
        将LongPort API返回的SecurityQuote对象转换为标准Python字典格式，
        方便后续处理和存储
        
        Args:
            quote: SecurityQuote对象
            
        Returns:
            dict: 转换后的行情数据字典
        """
        # 辅助函数：将可能的datetime对象转换为字符串
        def convert_timestamp(timestamp):
            if hasattr(timestamp, 'strftime'):
                return timestamp.strftime('%Y-%m-%d %H:%M:%S')
            return str(timestamp)
        
        # 尝试直接使用对象的属性构建字典
        quote_dict = {
            'symbol': quote.symbol,                     # 股票代码
            'last_done': float(quote.last_done),        # 最新成交价
            'prev_close': float(quote.prev_close),      # 昨日收盘价
            'open': float(quote.open),                  # 开盘价
            'high': float(quote.high),                  # 最高价
            'low': float(quote.low),                    # 最低价
            'timestamp': convert_timestamp(quote.timestamp),  # 时间戳
            'volume': int(quote.volume),                # 成交量
            'turnover': float(quote.turnover),          # 成交额
            'trade_status': str(quote.trade_status)     # 交易状态
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


    def get_real_time_quote(self, symbol):
        """获取实时行情数据
        
        通过LongPort API获取指定股票的实时行情数据，如果获取失败则使用模拟数据
        
        Args:
            symbol (str): 股票代码
            
        Returns:
            dict: 包含股票行情信息的字典
        """
        try:
            # 使用LongPort API获取真实行情数据
            resp = ctx.quote([symbol])
            quote_dict = self.quote_to_dict(resp[0])
            #logger.debug(f"获取{symbol}行情数据成功: {quote_dict}")
            
            # 使用真实数据构建返回值
            change_percent = ((quote_dict['last_done'] - quote_dict['prev_close']) / quote_dict['prev_close']) * 100
            
            quote = {
                'symbol': symbol,                           # 股票代码
                'last_price': quote_dict['last_done'],      # 最新价格
                'previous_close': quote_dict['prev_close'], # 前收盘价
                'change_percent': change_percent,           # 涨跌幅百分比
                'timestamp': datetime.now().isoformat()     # 时间戳
            }
            
            return quote
        except Exception as e:
            logger.error(f"获取{symbol}行情数据失败: {e}")
            # 失败时使用模拟数据作为后备
            import random
            mock_price = random.uniform(10, 200)
            mock_previous_close = mock_price * random.uniform(0.95, 1.05)
            mock_change_percent = ((mock_price - mock_previous_close) / mock_previous_close) * 100
            
            quote = {
                'symbol': symbol,
                'last_price': mock_price,
                'previous_close': mock_previous_close,
                'change_percent': mock_change_percent,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.warning(f"使用模拟数据: {quote}")
            return quote
    
    def market_temp_to_dict(self, temp_obj):
        """将MarketTemperature对象转换为字典
        
        将LongPort API返回的MarketTemperature对象转换为标准Python字典格式
        
        Args:
            temp_obj: MarketTemperature对象
            
        Returns:
            dict: 转换后的市场温度数据字典
        """
        result = {
            'temperature': temp_obj.temperature,    # 市场温度值
            'description': temp_obj.description,    # 市场温度描述
            'valuation': temp_obj.valuation,        # 市场估值
            'sentiment': temp_obj.sentiment         # 市场情绪
        }
        # 处理timestamp字段，转换为字符串
        if hasattr(temp_obj, 'timestamp'):
            result['timestamp'] = str(temp_obj.timestamp)
        return result
    
    def get_current_positions(self):
        """获取当前实际持仓信息
        
        通过交易上下文获取账户当前的实际持仓情况
        
        Returns:
            dict: 以股票代码为键的持仓信息字典
        """
        try:
            resp = self.trade_ctx.stock_positions()
            positions_dict = self.positions_to_dict(resp)
            
            # 提取所有持仓到一个字典中，以股票代码为键
            positions = {}
            for channel in positions_dict['channels']:
                for pos in channel['positions']:
                    positions[pos['symbol']] = {
                        'quantity': pos['quantity'],                # 总持仓数量
                        'available_quantity': pos['available_quantity'],  # 可用数量
                        'cost_price': pos['cost_price'],            # 成本价
                        'currency': pos['currency']                 # 货币单位
                    }
            
            logger.debug(f"获取当前持仓: {positions}")
            return positions
        except Exception as e:
            logger.error(f"获取当前持仓失败: {e}")
            return {}
    
    def save_decision_memory(self, symbol, instruction, reason, price):
        """保存决策到历史记忆
        
        将AI的交易决策保存到历史记录中，用于后续分析和决策参考
        
        Args:
            symbol (str): 股票代码
            instruction (str): 交易指令（buy/sell/hold）
            reason (str): 决策理由
            price (float): 决策时的价格
        """
        decision = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # 决策时间
            'instruction': instruction,                                   # 交易指令
            'reason': reason,                                             # 决策理由
            'price': price                                                # 决策价格
        }
        
        # 使用线程锁保护共享资源
        with self.memory_lock:
            # 保存到记忆中，限制记忆长度为20条
            if symbol in self.decision_memory:
                self.decision_memory[symbol].append(decision)
                # 保持记忆长度不超过20条
                if len(self.decision_memory[symbol]) > 20:
                    self.decision_memory[symbol] = self.decision_memory[symbol][-20:]
            else:
                self.decision_memory[symbol] = [decision]
        
        logger.debug(f"保存决策到历史记忆: {symbol} - {decision}")

    def get_last_buy_price_info(self, symbol, current_price):
        """获取最近一次买入价格信息并计算与现价的差距
        
        Args:
            symbol (str): 股票代码
            current_price (float): 当前价格
            
        Returns:
            str: 格式化的最近买入价格信息和差距分析
        """
        # 使用线程锁保护共享资源
        with self.transaction_lock:
            # 从交易历史中筛选该股票的所有买入交易
            buy_transactions = [t for t in self.transactions 
                               if t['symbol'] == symbol and t['action'] == 'buy']
        
        # 如果没有买入交易记录
        if not buy_transactions:
            return "- 最近买入价格: 无交易记录\n"
        
        # 按时间戳排序，获取最近的买入交易
        buy_transactions.sort(key=lambda x: x['timestamp'], reverse=True)
        last_buy = buy_transactions[0]
        
        last_buy_price = last_buy['price']
        last_buy_date = last_buy['timestamp'][:10]  # 提取日期部分
        
        # 计算价格差距和百分比
        price_diff = current_price - last_buy_price
        price_diff_percent = (price_diff / last_buy_price) * 100 if last_buy_price > 0 else 0
        
        # 根据差距大小生成操作建议参考
        suggestion = ""
        if price_diff_percent > 10:
            suggestion = "- 操作参考: 当前价格大幅高于最近买入价，考虑止盈或持有\n"
        elif price_diff_percent > 5:
            suggestion = "- 操作参考: 当前价格高于最近买入价，可考虑部分止盈\n"
        elif price_diff_percent > 0:
            suggestion = "- 操作参考: 当前价格略高于最近买入价，可继续持有\n"
        elif price_diff_percent > -5:
            suggestion = "- 操作参考: 当前价格略低于最近买入价，可考虑适当加仓\n"
        elif price_diff_percent > -10:
            suggestion = "- 操作参考: 当前价格低于最近买入价，需要谨慎考虑加仓时机\n"
        else:
            suggestion = "- 操作参考: 当前价格大幅低于最近买入价，建议观望或小额试探性加仓\n"
        
        # 构建完整信息
        info = f"- 最近买入价格: {last_buy_price:.2f} (日期: {last_buy_date})\n"
        info += f"- 价格差距: {price_diff:+.2f} ({price_diff_percent:+.2f}%)\n"
        info += suggestion
        
        return info

    def analyze_with_deepseek(self, stock_data, quote):
        """使用Deepseek进行决策分析，返回明确的交易指令
        
        调用DeepSeek AI接口，基于当前股票数据、持仓情况、股票指标和历史决策记录，
        分析并生成交易决策（买入/卖出/持有）
        
        Args:
            stock_data (dict): 股票监控数据
            quote (dict): 实时行情数据
            
        Returns:
            dict: 包含指令、理由和数量的决策字典
        """
        try:
            api_key = self.config['deepseek']['api_key']
            api_url = self.config['deepseek']['api_url']
            
            # 获取市场温度信息（如果可用）
            market_temperature = None
            try:
                resp = ctx.market_temperature(Market.US)
                if resp:
                    market_temperature = self.market_temp_to_dict(resp)

                    logger.debug(f"获取市场温度: {market_temperature['temperature']}")
            except Exception as temp_e:
                logger.warning(f"获取市场温度失败: {temp_e}")
            
            # 获取实际持仓信息
            positions = self.get_current_positions()
            stock_position = positions.get(quote['symbol'], {})
            
            # 获取股票指标数据
            stock_indexes = None
            try:
                from longport.openapi import CalcIndex
                resp = ctx.calc_indexes(
                    [quote['symbol']], 
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
                if resp and len(resp) > 0:
                    stock_indexes = resp[0]
                    logger.debug(f"获取股票指标成功: {quote['symbol']}")
            except Exception as idx_e:
                logger.warning(f"获取股票指标失败: {idx_e}")
            
            # 获取账户资金信息（添加资金限额功能）
            account_balance = None
            fund_limit = self.config.get('fund_limit', 0)  # 从配置获取资金限额，默认为0表示不限制
            available_funds = 0
            
            try:
                resp = self.trade_ctx.account_balance()
                if resp and len(resp) > 0:
                    # 获取可用资金
                    for cash_info in resp[0].cash_infos:
                        # 假设主币种是HKD，这里可以根据实际情况调整
                        if cash_info.currency == 'HKD' or cash_info.currency == 'USD':
                            available_funds += float(cash_info.available_cash)
                    account_balance = {
                        'available_funds': available_funds,
                        'fund_limit': fund_limit
                    }
                    logger.debug(f"获取账户资金信息: 可用资金={available_funds}, 资金限额={fund_limit}")
            except Exception as acc_e:
                logger.warning(f"获取账户资金信息失败: {acc_e}")
            
            # 准备历史决策信息
            history_info = ""
            if self.decision_memory.get(quote['symbol']):
                history_info = "\n历史决策记录:\n"
                # 只显示最近的5条决策记录，避免prompt过长
                recent_decisions = self.decision_memory[quote['symbol']][-5:]
                for idx, decision in enumerate(recent_decisions, 1):
                    history_info += f"- 时间: {decision['timestamp']}, 指令: {decision['instruction']}, 理由: {decision['reason']}\n"
            #阈值设置: {stock_data['threshold']}%
            # 准备股票指标信息
            index_info = ""
            if stock_indexes:
                index_info = "\n股票指标信息:\n"
                if hasattr(stock_indexes, 'pe_ttm_ratio') and stock_indexes.pe_ttm_ratio is not None:
                    index_info += f"- 市盈率(TTM): {stock_indexes.pe_ttm_ratio:.2f}\n"
                if hasattr(stock_indexes, 'pb_ratio') and stock_indexes.pb_ratio is not None:
                    index_info += f"- 市净率: {stock_indexes.pb_ratio:.2f}\n"
                if hasattr(stock_indexes, 'dividend_ratio_ttm') and stock_indexes.dividend_ratio_ttm is not None:
                    index_info += f"- 股息率(TTM): {stock_indexes.dividend_ratio_ttm:.2f}%\n"
                if hasattr(stock_indexes, 'five_day_change_rate') and stock_indexes.five_day_change_rate is not None:
                    index_info += f"- 5日涨跌幅: {stock_indexes.five_day_change_rate:.2f}%\n"
                if hasattr(stock_indexes, 'ten_day_change_rate') and stock_indexes.ten_day_change_rate is not None:
                    index_info += f"- 10日涨跌幅: {stock_indexes.ten_day_change_rate:.2f}%\n"
                # 添加5分钟涨跌幅指标
                if hasattr(stock_indexes, 'five_min_change_rate') and stock_indexes.five_min_change_rate is not None:
                    index_info += f"- 5分钟涨跌幅: {stock_indexes.five_min_change_rate:.2f}%\n"
                # 添加成交量指标
                if hasattr(stock_indexes, 'volume') and stock_indexes.volume is not None:
                    index_info += f"- 成交量: {stock_indexes.volume}\n"
                if hasattr(stock_indexes, 'turnover_rate') and stock_indexes.turnover_rate is not None:
                    index_info += f"- 换手率: {stock_indexes.turnover_rate:.2f}%\n"
                if hasattr(stock_indexes, 'volume_ratio') and stock_indexes.volume_ratio is not None:
                    index_info += f"- 量比: {stock_indexes.volume_ratio:.2f}\n"
                if hasattr(stock_indexes, 'amplitude') and stock_indexes.amplitude is not None:
                    index_info += f"- 振幅: {stock_indexes.amplitude:.2f}%\n"
                if hasattr(stock_indexes, 'capital_flow') and stock_indexes.capital_flow is not None:
                    index_info += f"- 资金流向: {stock_indexes.capital_flow:.3f}\n"
                if hasattr(stock_indexes, 'ytd_change_rate') and stock_indexes.ytd_change_rate is not None:
                    index_info += f"- 年初至今涨跌幅: {stock_indexes.ytd_change_rate:.2f}%\n"
            
            # 准备发送给Deepseek的提示信息
            # 构建资金信息文本
            fund_info = ""
            if account_balance:
                fund_info = "\n资金信息:\n"
                fund_info += f"- 账户可用资金: {account_balance['available_funds']:.2f}\n"
                if account_balance['fund_limit'] > 0:
                    fund_info += f"- 交易资金限额: {account_balance['fund_limit']:.2f}\n"
                    # 计算建议使用的最大金额（例如：资金限额的30%用于单笔交易）
                    max_single_transaction = account_balance['fund_limit'] * 0.3
                    fund_info += f"- 单笔交易建议最大金额: {max_single_transaction:.2f}\n"
            # 获取最近一次买入价格信息和差距分析
            last_buy_info = self.get_last_buy_price_info(quote['symbol'], quote['last_price'])
            
            # {index_info}
            prompt = f"""请基于以下股票数据做出交易决策（买入/卖出/持有）：
            股票代码: {quote['symbol']}
            5分钟涨跌幅: {stock_indexes.five_minutes_change_rate:.2f}%
            当前价格: {quote['last_price']}
            前收盘价: {quote['previous_close']}
            涨跌幅: {quote['change_percent']:.2f}%
            模拟持仓价值: {stock_data['position']}
            实际持仓数量: {stock_position.get('quantity', 0)}
            持仓成本价: {stock_position.get('cost_price', '未知')}{stock_position.get('currency', '') if stock_position else ''}
            {f'市场温度: {market_temperature}' if market_temperature else ''}
            {index_info}
            {fund_info}
            {last_buy_info}
            {history_info}
            
            
            请按照以下格式输出：
            指令: [买入/卖出/持有]
            数量: [建议交易的股数，基于当前市场情况、风险考量、股票估值水平和可用资金限制。买入时请确保不超过资金限额。]"""
            #理由: [简洁的决策理由，充分考虑基本面指标(如市盈率、市净率)、技术面指标(如涨跌幅、换手率)、资金流向、最近买入价和现价、5分钟涨跌幅、市场温度以及历史决策的连续性]
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一个顶尖的量化交易专家，精通算法交易、统计套利和机器学习交易策略。基于提供的全面数据进行严格的量化分析，包括：\n1. 技术指标分析：RSI、MACD、布林带、成交量变化率、波动率等\n2. 统计模型应用：价格动量、均值回归、波动率突破策略\n3. 风险管理：严格执行单笔交易资金限制(不超过资金限额的10%)、止损策略(单笔最大亏损不超过最近买入价格的2%)\n4. 多因子评估：市场温度、行业相对强度、资金流向、量价关系\n5. 时间序列分析：日内波动模式识别、短期趋势预测\n\n请在当前价格大于最近买入价5%时考虑卖出，买入决策必须严格遵守资金限制，在5分钟跌幅大于1%的时候买入。使用量化语言思考，基于数据而非情绪做出决策。输出必须是'买入'、'卖出'或'持有'中的一个，不需要阐述理由。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 1
            }
            
            response = requests.post(api_url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            decision_text = result['choices'][0]['message']['content']
            
            logger.info(f"Deepseek分析结果 ({quote['symbol']}): {decision_text}")
            
            # 解析决策结果
            instruction = "hold"  # 默认持有
            reason = "未提供理由"
            quantity = 10  # 默认数量
            
            # 提取指令
            if "指令: 买入" in decision_text:
                instruction = "buy"
            elif "指令: 卖出" in decision_text:
                instruction = "sell"
            elif "指令: 持有" in decision_text:
                instruction = "hold"
            
            # 尝试提取理由
            reason_match = re.search(r'理由: (.+)', decision_text)
            if reason_match:
                reason = reason_match.group(1)
            
            # 尝试提取数量
            quantity_match = re.search(r'数量: (\d+)', decision_text)
            if quantity_match:
                try:
                    quantity = int(quantity_match.group(1))
                except ValueError:
                    pass
            
            # 保存决策到历史记忆
            self.save_decision_memory(quote['symbol'], instruction, reason, quote['last_price'])
            
            return {
                'instruction': instruction,
                'reason': reason,
                'quantity': quantity
            }
        except Exception as e:
            logger.error(f"调用Deepseek API失败: {e}")
            return {
                'instruction': "hold",
                'reason': "API调用失败，默认持有",
                'quantity': 0
            }
    
    
    
    def place_order(self, symbol, action, quantity, price):
        """使用LongPort API进行真实下单交易
        
        执行实际的股票交易订单，包括买入和卖出操作
        
        Args:
            symbol (str): 股票代码
            action (str): 交易动作 ('buy' 或 'sell')
            quantity (int): 交易数量
            price (float): 交易价格
            
        Returns:
            dict: 订单信息字典，如果下单失败则返回None
        """
        try:
            # 检查资金限额（买入操作时）
            if action == 'buy':
                fund_limit = self.config.get('fund_limit', 0)  # 从配置获取资金限额
                transaction_amount = quantity * price
                
                # 如果设置了资金限额，检查是否会超支
                if fund_limit > 0:
                    # 获取当前已使用资金（简化版，实际可能需要计算所有持仓）
                    used_funds = 0
                    positions = self.get_current_positions()
                    for sym, pos in positions.items():
                        # 获取当前价格
                        try:
                            quote = self.get_real_time_quote(sym)
                            used_funds += pos['quantity'] * quote['last_price']
                        except:
                            pass
                    
                    # 计算预计使用资金
                    estimated_used_funds = used_funds + transaction_amount
                    
                    # 检查是否超过限额
                    if estimated_used_funds > fund_limit:
                        logger.warning(f"交易金额将超过资金限额: {estimated_used_funds} > {fund_limit}")
                        # 调整数量以符合限额
                        adjusted_quantity = int((fund_limit - used_funds) / price)
                        if adjusted_quantity > 0:
                            logger.info(f"调整交易数量从 {quantity} 到 {adjusted_quantity} 以符合资金限额")
                            quantity = adjusted_quantity
                        else:
                            logger.warning(f"资金不足，无法执行买入操作")
                            return None
            
            # 获取最大持仓限制
            max_position = self.config.get('app', {}).get('max_position', 100000)
            
            # 检查持仓限制（对于买入操作）
            if action == 'buy' and self.stock_data[symbol]['position'] + (quantity * price) > max_position:
                logger.warning(f"买入将超出最大持仓限制，调整数量")
                # 计算可买入的最大数量
                available_funds = max_position - self.stock_data[symbol]['position']
                quantity = max(1, int(available_funds / price))
                logger.info(f"调整后买入数量: {quantity}")
            
            # 转换操作类型
            if action == 'buy':
                side = "Buy"
            elif action == 'sell':
                side = "Sell"
            else:
                raise ValueError(f"不支持的操作类型: {action}")
            
            # 执行真实下单
            order = self.trade_ctx.submit_order(
                symbol,
                OrderType.MO,                                       # 市价单
                OrderSide.Buy if side=="Buy" else OrderSide.Sell,  # 买卖方向
                Decimal(quantity),                                  # 数量
                TimeInForceType.Day,                                # 有效时间
                submitted_price=Decimal(price),                     # 提交价格
                remark="Hello from Python SDK",
            )
            
            # 构建订单信息
            order_info = {
                'symbol': symbol,                                   # 股票代码
                'action': action,                                   # 交易动作
                'quantity': quantity,                               # 交易数量
                'price': price,                                     # 交易价格
                'order_id': order.order_id if hasattr(order, 'order_id') else 'unknown',  # 订单ID
                'timestamp': datetime.now().isoformat(),            # 时间戳
                'status': 'submitted'                              # 订单状态
            }
            
            # 记录交易并计算利润（如果是卖出操作）
            if action == 'sell':
                with self.transaction_lock, self.position_lock:
                    profit_details = self.calculate_profit(order_info)
                    order_info['profit'] = profit_details['total_profit']
                    order_info['profit_percent'] = profit_details['total_profit_percent']
                    order_info['matched_buys'] = profit_details['matched_buys']
                
                # 记录利润信息
                logger.info(f"卖出 {symbol} 获利: {order_info['profit']:.2f} ({order_info['profit_percent']:.2f}%)")
            else:  # 买入操作，添加到未平仓记录
                with self.position_lock:
                    self.open_positions[symbol].append(order_info)
                    order_info['closed'] = False  # 标记为未平仓
            
            # 添加到交易历史并保存
            with self.transaction_lock:
                self.transactions.append(order_info)
                # 保存交易历史
                self.save_transactions()
            
            logger.info(f"下单成功: {order_info}")
            
            # 更新持仓信息
            if action == 'buy':
                with self.position_lock:
                    self.stock_data[symbol]['position'] += quantity * price
            elif action == 'sell':
                with self.position_lock:
                    self.stock_data[symbol]['position'] -= quantity * price
                    if self.stock_data[symbol]['position'] < 0:
                        self.stock_data[symbol]['position'] = 0
            
            return order_info
        except Exception as e:
            logger.error(f"下单失败: {e}")
            
            # 如果真实下单失败，回退到模拟下单（仅用于测试和演示）
            if self.config.get('app', {}).get('fallback_to_simulated', True):
                logger.info("回退到模拟下单模式")
                order_id = f"mock_order_{int(time.time())}"
                logger.info(f"模拟下单: {symbol}, {action}, {quantity}, {price}")
                order_info = {
                    'symbol': symbol,
                    'action': action,
                    'quantity': quantity,
                    'price': price,
                    'order_id': order_id,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'simulated',
                    'time_in_force': 'Day',
                    'transaction_type': 'simulated'  # 交易类型：模拟
                }
                
                # 记录交易并计算利润（如果是卖出操作）
                if action == 'sell':
                    with self.transaction_lock, self.position_lock:
                        profit_details = self.calculate_profit(order_info)
                        order_info['profit'] = profit_details['total_profit']
                        order_info['profit_percent'] = profit_details['total_profit_percent']
                        order_info['matched_buys'] = profit_details['matched_buys']
                    
                    # 记录利润信息
                    logger.info(f"模拟卖出 {symbol} 获利: {order_info['profit']:.2f} ({order_info['profit_percent']:.2f}%)")
                else:  # 买入操作，添加到未平仓记录
                    with self.position_lock:
                        self.open_positions[symbol].append(order_info)
                        order_info['closed'] = False  # 标记为未平仓
            
                # 添加到交易历史
                with self.transaction_lock:
                    self.transactions.append(order_info)
                    # 保存交易历史
                    self.save_transactions()
                
                # 更新模拟持仓
                if action == 'buy':
                    self.stock_data[symbol]['position'] += quantity * price
                elif action == 'sell':
                    self.stock_data[symbol]['position'] -= quantity * price
                    if self.stock_data[symbol]['position'] < 0:
                        self.stock_data[symbol]['position'] = 0
                
                return order_info
            
            return None

    def positions_to_dict(self, response):
        """将StockPositionsResponse对象转换为字典格式
        
        将LongPort API返回的StockPositionsResponse对象转换为标准Python字典格式
        
        Args:
            response: StockPositionsResponse对象
            
        Returns:
            dict: 转换后的持仓信息字典
        """
        # 辅助函数：将Decimal等特殊类型转换为可JSON序列化的类型
        def convert_value(value):
            if isinstance(value, Decimal):
                return float(value)
            elif hasattr(value, 'value'):
                return convert_value(value.value)
            elif hasattr(value, '__str__'):
                return str(value)
            return value
    
        result = {
            'channels': []  # 持仓通道列表
        }
        
        # 处理每个channel
        for channel in response.channels:
            channel_dict = {
                'account_channel': convert_value(channel.account_channel),  # 账户通道
                'positions': []  # 持仓列表
            }
            
            # 处理每个position
            for pos in channel.positions:
                position_dict = {
                    'symbol': convert_value(pos.symbol),                    # 股票代码
                    'symbol_name': convert_value(pos.symbol_name),          # 股票名称
                    'quantity': convert_value(pos.quantity),                # 持仓数量
                    'available_quantity': convert_value(pos.available_quantity),  # 可用数量
                    'currency': convert_value(pos.currency),                # 货币
                    'cost_price': float(pos.cost_price),                   # 成本价
                    'market': str(pos.market)                               # 市场
                }
                
                # 处理可选字段
                if hasattr(pos, 'init_quantity') and pos.init_quantity is not None:
                    position_dict['init_quantity'] = convert_value(pos.init_quantity)
                
                channel_dict['positions'].append(position_dict)
            
            result['channels'].append(channel_dict)
        
        return result
        
    def process_stock(self, symbol, stock_config):
        """处理单只股票的监控和交易逻辑
        
        对单只股票执行完整的监控和交易流程：
        1. 获取实时行情
        2. 调用AI分析决策
        3. 执行交易操作
        4. 检查价格波动警报
        
        Args:
            symbol (str): 股票代码
            stock_config (dict): 股票配置信息
        """
        quote = self.get_real_time_quote(symbol)
        if not quote:
            return
        
        # 记录首次价格
        if stock_config['previous_price'] is None:
            stock_config['previous_price'] = quote['last_price']
            logger.info(f"初始化{symbol}价格: {quote['last_price']}")
        
        # 持续调用Deepseek进行分析
        decision = self.analyze_with_deepseek(stock_config, quote)
        
        # 根据决策执行操作
        if decision['instruction'] == 'buy':
            logger.info(f"执行买入操作: {symbol}, 数量: {decision['quantity']}, 价格: {quote['last_price']}, 理由: {decision['reason']}")
            self.place_order(symbol, 'buy', decision['quantity'], quote['last_price'])
        elif decision['instruction'] == 'sell':
            # 获取实际持仓信息
            positions = self.get_current_positions()
            stock_position = positions.get(symbol, {})
            actual_available_quantity = stock_position.get('available_quantity', 0)
            
            # 同时考虑实际持仓和模拟持仓
            if actual_available_quantity > 0 or self.stock_data[symbol]['position'] > 0:
                # 使用实际可用数量作为最大可卖出数量
                max_sell_quantity = int(actual_available_quantity)
                # 如果没有实际持仓，则使用模拟持仓价值计算
                if max_sell_quantity <= 0:
                    max_sell_quantity = int(self.stock_data[symbol]['position'] / quote['last_price'])
                    
                quantity = min(decision['quantity'], max_sell_quantity)
                if quantity > 0:
                    logger.info(f"执行卖出操作: {symbol}, 数量: {quantity}, 价格: {quote['last_price']}, 理由: {decision['reason']}")
                    logger.info(f"实际可用持仓: {actual_available_quantity}, 模拟持仓价值: {self.stock_data[symbol]['position']}")
                    self.place_order(symbol, 'sell', quantity, quote['last_price'])
                else:
                    logger.warning(f"计算的卖出数量为0，无法执行卖出操作: {symbol}")
            else:
                logger.warning(f"无持仓或持仓不足，无法执行卖出操作: {symbol}, 实际可用: {actual_available_quantity}, 模拟持仓: {self.stock_data[symbol]['position']}")
        else:
            logger.info(f"执行持有策略: {symbol}, 理由: {decision['reason']}")
        
        # 检查涨跌幅是否超过阈值（作为额外的提醒机制）
        if abs(quote['change_percent']) >= stock_config['threshold']:
            # 避免频繁提醒，限制在5分钟内只提醒一次
            now = datetime.now()
            if stock_config['last_alert_time'] is None or \
               (now - stock_config['last_alert_time']).total_seconds() > 300:
                
                logger.info(f"⚠️  {symbol} 涨跌幅 ({quote['change_percent']:.2f}%) 超过阈值 {stock_config['threshold']}%")
                stock_config['last_alert_time'] = now
        
        # 更新价格
        stock_config['previous_price'] = quote['last_price']
    
    def run(self):
        """运行监控程序
        
        主循环函数，持续监控所有配置的股票，执行监控和交易逻辑
        使用多线程并行处理多个股票标的，提高运行效率
        """
        logger.info("股票监控程序已启动")
        logger.info(f"使用多线程并行处理，最大线程数: {self.max_workers}")
        
        try:
            # 记录程序启动时的利润报告
            logger.info("生成初始利润报告...")
            self.display_profit_report()
            
            # 记录报告生成时间，用于定期报告
            last_report_time = datetime.now()
            report_interval = self.config.get('app', {}).get('profit_report_interval', 10)  # 默认60分钟
            
            while True:
                # 使用线程池并行处理多个股票
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # 提交所有股票的处理任务
                    future_to_stock = {
                        executor.submit(self.process_stock, symbol, stock_config): (symbol, stock_config)
                        for symbol, stock_config in self.stock_data.items()
                    }
                    
                    # 等待所有任务完成并处理结果
                    for future in concurrent.futures.as_completed(future_to_stock):
                        symbol, _ = future_to_stock[future]
                        try:
                            future.result()  # 获取结果，以便捕获可能的异常
                            logger.debug(f"股票 {symbol} 处理完成")
                        except Exception as e:
                            logger.error(f"处理股票 {symbol} 时出错: {e}")
                
                # 检查是否需要生成利润报告
                now = datetime.now()
                if (now - last_report_time).total_seconds() > (report_interval * 60):
                    logger.info(f"生成定期利润报告 (每{report_interval}分钟)")
                    self.display_profit_report()
                    last_report_time = now
                
                # 等待下一次检查
                check_interval = self.config['app'].get('check_interval', 30)
                logger.debug(f"等待{check_interval}秒后进行下一次检查")
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            logger.info("程序被用户中断")
            # 用户中断时，生成最终利润报告
            logger.info("生成最终利润报告...")
            self.display_profit_report()
        except Exception as e:
            logger.error(f"程序运行出错: {e}")
            # 程序出错时，尝试生成最终利润报告
            try:
                self.display_profit_report()
            except:
                pass
        finally:
            logger.info("股票监控程序已停止")

if __name__ == "__main__":
    monitor = StockMonitor()
    monitor.run()