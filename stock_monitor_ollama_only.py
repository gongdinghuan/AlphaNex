#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票监控和自动交易系统 - Ollama精简版

该脚本是一个精简版的股票监控和自动交易系统，只使用Ollama进行AI分析。
主要功能包括：
1. 实时获取股票行情数据
2. 利用Ollama AI分析决策是否买卖或持有
3. 执行基本的交易操作
"""

# 导入所需模块
from datetime import datetime
from decimal import Decimal  # 用于精确的十进制运算
import yaml                  # 用于读取配置文件
import time                 # 用于控制程序执行间隔
import logging              # 用于记录日志
import requests             # 用于向AI服务发送HTTP请求
import json                 # 用于处理JSON数据
import os                   # 用于操作系统相关功能
import re                   # 用于正则表达式匹配
from collections import defaultdict
import threading
from typing import Dict, List, Optional, Any, Union

# 导入LongPort OpenAPI相关模块
from longport.openapi import QuoteContext, Config, TradeContext, Market, OrderType, OrderSide, TimeInForceType

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别为INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # 日志格式
    handlers=[
        logging.FileHandler("stock_monitor_ollama.log"),  # 输出到文件
        logging.StreamHandler()  # 输出到控制台
    ]
)
logger = logging.getLogger("StockMonitor")  # 创建日志记录器

class StockMonitor:
    """
    股票监控主类 - Ollama精简版
    
    负责监控股票价格变化、调用Ollama AI进行分析决策、执行交易订单等功能
    """
    
    def __init__(self, config_file: str = "config.yaml") -> None:
        """初始化股票监控器
        
        Args:
            config_file (str): 配置文件路径，默认为"config.yaml"
        """
        self.config_file: str = config_file           # 配置文件路径
        self.config: Dict[str, Any] = self.load_config()        # 加载配置
        self.stock_data: Dict[str, Dict[str, Any]] = {}                    # 存储各股票的监控数据
        self.decision_memory: Dict[str, List[Dict[str, Any]]] = {}               # 存储各股票的AI决策历史
        self.transactions: List[Dict[str, Any]] = []                  # 所有交易记录
        self.open_positions: defaultdict[str, List[Dict[str, Any]]] = defaultdict(list) # 当前未平仓的持仓，按股票代码分组
        self.position_lock: threading.Lock = threading.Lock()    # 保护持仓信息
        self.transaction_lock: threading.Lock = threading.Lock() # 保护交易记录
        
        # 加载历史交易记录
        self.load_transactions()
        
        self.initialize_stock_data()            # 初始化股票数据
        
        # 创建LongPort API上下文
        self.config_obj: Config = Config(
            app_key=self.config['longport']['app_key'],
            app_secret=self.config['longport']['app_secret'],
            access_token=self.config['longport']['access_token']
        )
        self.quote_ctx: QuoteContext = QuoteContext(self.config_obj)  # 行情上下文对象
        self.trade_ctx: TradeContext = TradeContext(self.config_obj)  # 交易上下文对象
        
        logger.info(f"股票监控器已初始化，监控股票数量: {len(self.config['stocks'])}")

    def load_config(self) -> Dict[str, Any]:
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
    
    def initialize_stock_data(self) -> None:
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
                    'position': 0,                                # 持仓价值
                    'position_quantity': 0,                        # 持仓数量
                    'average_cost': 0.0                            # 平均成本
                }
                # 初始化该股票的历史决策记忆
                self.decision_memory[stock['symbol']] = []

    def get_real_time_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情数据
        
        通过LongPort API获取指定股票的实时行情数据
        
        Args:
            symbol (str): 股票代码
            
        Returns:
            Optional[Dict[str, Any]]: 包含股票行情信息的字典，如果获取失败则返回None
        """
        try:
            resp = self.quote_ctx.quote([symbol])
            if resp and len(resp) > 0:
                quote = resp[0]
                return {
                    'symbol': quote.symbol,
                    'last_price': float(quote.last_done),
                    'previous_close': float(quote.prev_close),
                    'open': float(quote.open),
                    'high': float(quote.high),
                    'low': float(quote.low),
                    'volume': int(quote.volume),
                    # 手动计算涨跌幅百分比
                    'change_percent': ((float(quote.last_done) - float(quote.prev_close)) / float(quote.prev_close) * 100) if quote.prev_close > 0 else 0
                }
            logger.error(f"获取{symbol}行情数据失败: 无返回数据")
            return None
        except Exception as e:
            logger.error(f"获取{symbol}行情数据失败: {e}")
            return None

    def positions_to_dict(self, positions_response: Any) -> Dict[str, Any]:
        """将持仓响应对象转换为字典格式
        
        Args:
            positions_response: LongPort API返回的持仓响应对象
            
        Returns:
            Dict[str, Any]: 格式化后的持仓信息字典
        """
        result: Dict[str, Any] = {'channels': [{'positions': []}]}
        positions_to_process: List[Any] = []
        
        try:
            # 尝试不同的方式获取持仓数据，以适应实际的API响应结构
            if hasattr(positions_response, 'positions'):
                # 方式1: 直接从响应对象获取positions
                positions_to_process = positions_response.positions
            elif hasattr(positions_response, 'channels'):
                # 方式2: 从channels中获取所有positions
                for channel in positions_response.channels:
                    if hasattr(channel, 'positions'):
                        positions_to_process.extend(channel.positions)
            else:
                logger.info(f"持仓响应对象类型: {type(positions_response)}, 无法直接获取持仓数据")
                return result
            
            # 处理所有持仓数据
            for pos in positions_to_process:
                try:
                    pos_data = {
                        'symbol': getattr(pos, 'symbol', 'unknown'),
                        'quantity': getattr(pos, 'quantity', 0),
                        'available_quantity': getattr(pos, 'available_quantity', 0),
                        'cost_price': float(getattr(pos, 'cost_price', 0)),
                        'currency': getattr(pos, 'currency', 'unknown')
                    }
                    result['channels'][0]['positions'].append(pos_data)
                except Exception as inner_e:
                    logger.warning(f"处理单个持仓时出错: {inner_e}")
                    
        except Exception as e:
            logger.error(f"转换持仓数据失败: {e}")
        
        return result
    
    def get_current_positions(self) -> Dict[str, Dict[str, Any]]:
        """获取当前实际持仓信息
        
        通过交易上下文获取账户当前的实际持仓情况
        
        Returns:
            Dict[str, Dict[str, Any]]: 以股票代码为键的持仓信息字典
        """
        try:
            resp = self.trade_ctx.stock_positions()
            positions_dict = self.positions_to_dict(resp)
            
            # 提取所有持仓到一个字典中，以股票代码为键
            positions: Dict[str, Dict[str, Any]] = {}
            for channel in positions_dict['channels']:
                for pos in channel['positions']:
                    positions[pos['symbol']] = {
                        'quantity': pos['quantity'],                # 总持仓数量
                        'available_quantity': pos['available_quantity'],  # 可用数量
                        'cost_price': pos['cost_price'],            # 成本价
                        'currency': pos['currency']                 # 货币单位
                    }
            
            #logger.info(f"获取当前持仓: {positions}")
            return positions
        except Exception as e:
            logger.warning(f"获取当前持仓失败: {e}，使用默认空字典")
            # 返回空字典作为后备
            return {}

    def get_last_buy_price_info(self, symbol: str, current_price: float) -> str:
        """获取最近一次买入价格信息
        
        Args:
            symbol (str): 股票代码
            current_price (float): 当前价格
            
        Returns:
            str: 最近买入价格信息
        """
        # 查找该股票的最近买入交易
        buy_transactions = [t for t in self.transactions if t['symbol'] == symbol and t['action'] == 'buy']
        if buy_transactions:
            # 按时间倒序排序，取最新的
            buy_transactions.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            last_buy = buy_transactions[0]
            last_price = last_buy.get('price', 0)
            price_diff = current_price - last_price
            percent_diff = (price_diff / last_price) * 100 if last_price > 0 else 0
            
            return f"最近买入信息: 价格={last_price}, 与现价差距={price_diff:.2f} ({percent_diff:.2f}%)"
        return ""

    def save_decision_memory(self, symbol: str, instruction: str, reason: str, price: float) -> None:
        """保存决策到历史记忆
        
        Args:
            symbol (str): 股票代码
            instruction (str): 决策指令
            reason (str): 决策理由
            price (float): 当前价格
        """
        decision: Dict[str, Any] = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'instruction': instruction,
            'reason': reason,
            'price': price
        }
        
        if symbol not in self.decision_memory:
            self.decision_memory[symbol] = []
        
        # 限制历史记录数量，只保留最近20条
        self.decision_memory[symbol].append(decision)
        if len(self.decision_memory[symbol]) > 20:
            self.decision_memory[symbol] = self.decision_memory[symbol][-20:]

    def analyze_with_ollama(self, stock_data: Dict[str, Any], quote: Dict[str, Any]) -> Dict[str, Any]:
        """使用Ollama进行决策分析，返回明确的交易指令
        
        调用Ollama本地API接口，基于当前股票数据、持仓情况、股票指标和历史决策记录，
        分析并生成交易决策（买入/卖出/持有）
        
        Args:
            stock_data (Dict[str, Any]): 股票监控数据
            quote (Dict[str, Any]): 实时行情数据
            
        Returns:
            Dict[str, Any]: 包含指令、理由和数量的决策字典
        """
        try:
            # 检查配置是否存在
            if 'ollama' not in self.config:
                logger.error("配置中未找到Ollama API配置")
                return {'instruction': 'hold', 'reason': '配置错误', 'quantity': 10}
                
            # 确保使用正确的API端点，添加chat路径
            api_url = self.config['ollama'].get('api_url', 'http://localhost:11434/api')
            if not api_url.endswith('/chat'):
                api_url = f"{api_url}/chat"
            model_name = self.config['ollama'].get('model', 'qwen3:4b')
            
            # 获取实际持仓信息
            positions = self.get_current_positions()
            stock_position = positions.get(quote['symbol'], {})
            
            # 获取账户资金信息
            account_balance = None
            fund_limit = self.config.get('fund_limit', 0)
            available_funds = 0
            
            try:
                resp = self.trade_ctx.account_balance()
                if resp and len(resp) > 0:
                    for cash_info in resp[0].cash_infos:
                        if cash_info.currency == 'HKD' or cash_info.currency == 'USD':
                            available_funds += float(cash_info.available_cash)
                    account_balance = {
                        'available_funds': available_funds,
                        'fund_limit': fund_limit
                    }
            except Exception as acc_e:
                logger.warning(f"获取账户资金信息失败: {acc_e}")
            
            # 准备历史决策信息
            history_info = ""
            if self.decision_memory.get(quote['symbol']):
                history_info = "\n历史决策记录:\n"
                recent_decisions = self.decision_memory[quote['symbol']][-5:]
                for idx, decision in enumerate(recent_decisions, 1):
                    history_info += f"- 时间: {decision['timestamp']}, 指令: {decision['instruction']}, 理由: {decision['reason']}\n"
            
            # 准备资金信息
            fund_info = ""
            if account_balance:
                fund_info = "\n资金信息:\n"
                fund_info += f"- 账户可用资金: {account_balance['available_funds']:.2f}\n"
                if account_balance['fund_limit'] > 0:
                    fund_info += f"- 交易资金限额: {account_balance['fund_limit']:.2f}\n"
            
            # 获取股票指标数据
            stock_indexes = None
            try:
                from longport.openapi import CalcIndex
                resp = self.quote_ctx.calc_indexes(
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
                if hasattr(stock_indexes, 'five_minutes_change_rate') and stock_indexes.five_minutes_change_rate is not None:
                    index_info += f"- 5分钟涨跌幅: {stock_indexes.five_minutes_change_rate:.2f}%\n"
                if hasattr(stock_indexes, 'volume') and stock_indexes.volume is not None:
                    index_info += f"- 成交量: {stock_indexes.volume}\n"
            

            # 获取最近一次买入价格信息
            last_buy_info = self.get_last_buy_price_info(quote['symbol'], quote['last_price'])
            
            # 获取模拟持仓价值，设置默认值0
            position_value = stock_data.get('position', 0)
            
            # 构建提示信息
            prompt = f"""请基于以下股票数据做出交易决策（买入/卖出/持有）：
            股票代码: {quote['symbol']}
            当前价格: {quote['last_price']}
            前收盘价: {quote['previous_close']}
            涨跌幅: {quote['change_percent']:.2f}%
            模拟持仓价值: {position_value}
            实际持仓数量: {stock_position.get('quantity', 0)}
            持仓成本价: {stock_position.get('cost_price', '未知')}{stock_position.get('currency', '') if stock_position else ''}
            {fund_info}
            {last_buy_info}
            {history_info}
            {index_info}
            
            请按照以下格式输出：
            指令: [买入/卖出/持有]
            数量: [建议交易的股数，基于当前市场情况、风险考量、股票估值水平和可用资金限制。买入时请确保不超过资金限额。]
            理由: [简洁的决策理由，充分考虑基本面指标、技术面指标、资金流向、最近买入价和现价以及历史决策的连续性]
            """
            
            # Ollama API请求格式
            headers = {
                'Content-Type': 'application/json'
            }
            
            # Ollama的请求参数
            data = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        #"content": "你是一个顶尖且激进量化交易专家，精通算法交易、统计套利和马丁交易策略，准备把资金做到盈利1000万。基于提供的全面数据进行严格的量化分析，包括技术指标分析、统计模型应用、风险管理、多因子评估和时间序列分析。请在当前价格大于最近买入价2%时考虑卖出，极速下跌或5分钟跌幅1%时买入。买入决策必须严格遵守资金限制。使用量化语言思考，基于数据而非情绪做出决策。输出必须是'买入'、'卖出'或'持有'中的一个，阐述理由。"
                        "content":"""你是一个顶尖且激进量化交易专家，精通算法交易、统计套利和马丁交易策略，准备把资金做到盈利1000万。根据提供的数据进行以下操作：
                                    每只标的开仓触发规则
                                    → 价格下跌 ≥1% 时，以100股开仓（最小仓位）
                                    加仓规则（关键！）
                                    → 每次亏损后，加仓1.5倍（非2倍！）
                                    → 最多加仓3次（避免爆仓）
                                    （例：第1次亏损 → 加仓150股；第2次亏损 → 加仓225股；第3次后停止）
                                    止盈规则
                                    → 价格反弹至平均成本+4% 时，立即平仓
                                    → 若价格持续下跌 → 退出交易（触发止损）
                                    ⚠️ 必须遵守的风险控制！
                                    输出必须是'买入'、'卖出'或'持有'中的一个，阐述理由。
                                    """
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 1,
                "stream": False
            }
            
            response = requests.post(api_url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            decision_text = result.get('message', {}).get('content', '')
            
            logger.info(f"Ollama分析结果 ({quote['symbol']}): {decision_text}")
            
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
            if not reason_match and decision_text:
                # 如果没有找到标准格式的理由，使用整个响应作为理由
                reason = decision_text[:100]  # 限制理由长度
            elif reason_match:
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
            logger.error(f"调用Ollama API失败: {e}")
            return {'instruction': 'hold', 'reason': f'API调用失败: {str(e)}', 'quantity': 10}

    def place_order(self, symbol: str, action: str, quantity: int, price: float) -> Optional[Dict[str, Any]]:
        """使用LongPort API进行真实下单交易
        
        执行实际的股票交易订单，包括买入和卖出操作
        
        Args:
            symbol (str): 股票代码
            action (str): 交易动作 ('buy' 或 'sell')
            quantity (int): 交易数量
            price (float): 交易价格
            
        Returns:
            Optional[Dict[str, Any]]: 订单信息字典，如果下单失败则返回None
        """
        try:
            # 检查资金限额（买入操作时）
            if action == 'buy':
                fund_limit = self.config.get('fund_limit', 0)  # 从配置获取资金限额
                transaction_amount = quantity * price
                
                # 如果设置了资金限额，检查是否会超支
                if fund_limit > 0:
                    # 使用self.stock_data中已有的持仓价值，避免多次API调用
                    used_funds = sum(stock_info['position'] for stock_info in self.stock_data.values())
                    
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
            
            # 确保数量是正整数且不以0开头
            # API要求数量必须符合正则表达式: ^([1-9]\d*(\.\d+)?)$
            # 先转换为整数，确保是有效数字
            if not isinstance(quantity, int) or quantity <= 0:
                quantity = int(quantity)
                if quantity <= 0:
                    raise ValueError(f"无效的交易数量: {quantity}，数量必须为正整数")
            
            # 执行真实下单
            order = self.trade_ctx.submit_order(
                symbol,
                OrderType.MO,                                       # 市价单
                OrderSide.Buy if side=="Buy" else OrderSide.Sell,  # 买卖方向
                Decimal(str(quantity)),                             # 数量转换为Decimal，确保格式正确
                TimeInForceType.Day,                                # 有效时间
                submitted_price=Decimal(str(price)),                # 价格转换为Decimal，确保格式正确
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
                    # 更新持仓价值和数量
                    old_quantity = self.stock_data[symbol]['position_quantity']
                    old_cost = self.stock_data[symbol]['position']
                    
                    # 计算新的平均成本
                    new_quantity = old_quantity + quantity
                    new_cost = old_cost + quantity * price
                    new_average_cost = new_cost / new_quantity if new_quantity > 0 else 0.0
                    
                    # 更新所有持仓信息
                    self.stock_data[symbol]['position'] = new_cost
                    self.stock_data[symbol]['position_quantity'] = new_quantity
                    self.stock_data[symbol]['average_cost'] = new_average_cost
                    
            elif action == 'sell':
                with self.position_lock:
                    # 更新持仓价值和数量
                    old_quantity = self.stock_data[symbol]['position_quantity']
                    old_cost = self.stock_data[symbol]['position']
                    
                    # 计算卖出后的持仓信息
                    # 注意：卖出操作不改变平均成本，只是减少持仓数量和价值
                    new_quantity = old_quantity - quantity
                    if new_quantity < 0:
                        new_quantity = 0
                    
                    # 按比例减少持仓价值（保持平均成本不变）
                    if old_quantity > 0:
                        new_cost = (new_quantity / old_quantity) * old_cost
                    else:
                        new_cost = 0
                    
                    # 更新所有持仓信息
                    self.stock_data[symbol]['position'] = new_cost
                    self.stock_data[symbol]['position_quantity'] = new_quantity
                    # 平均成本保持不变，除非持仓为0
                    if new_quantity == 0:
                        self.stock_data[symbol]['average_cost'] = 0.0
            
            return {
                'success': True,
                'order_id': order_info['order_id'],
                'transaction': order_info
            }
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
                    with self.position_lock:
                        # 更新持仓价值和数量
                        old_quantity = self.stock_data[symbol]['position_quantity']
                        old_cost = self.stock_data[symbol]['position']
                        
                        # 计算新的平均成本
                        new_quantity = old_quantity + quantity
                        new_cost = old_cost + quantity * price
                        new_average_cost = new_cost / new_quantity if new_quantity > 0 else 0.0
                        
                        # 更新所有持仓信息
                        self.stock_data[symbol]['position'] = new_cost
                        self.stock_data[symbol]['position_quantity'] = new_quantity
                        self.stock_data[symbol]['average_cost'] = new_average_cost
                elif action == 'sell':
                    with self.position_lock:
                        # 更新持仓价值和数量
                        old_quantity = self.stock_data[symbol]['position_quantity']
                        old_cost = self.stock_data[symbol]['position']
                        
                        # 计算卖出后的持仓信息
                        # 注意：卖出操作不改变平均成本，只是减少持仓数量和价值
                        new_quantity = old_quantity - quantity
                        if new_quantity < 0:
                            new_quantity = 0
                        
                        # 按比例减少持仓价值（保持平均成本不变）
                        if old_quantity > 0:
                            new_cost = (new_quantity / old_quantity) * old_cost
                        else:
                            new_cost = 0
                        
                        # 更新所有持仓信息
                        self.stock_data[symbol]['position'] = new_cost
                        self.stock_data[symbol]['position_quantity'] = new_quantity
                        # 平均成本保持不变，除非持仓为0
                        if new_quantity == 0:
                            self.stock_data[symbol]['average_cost'] = 0.0
                
                return order_info
            
            return None

    
    def save_transactions(self) -> None:
        """保存交易记录到文件"""
        try:
            with open('transaction_history.json', 'w', encoding='utf-8') as f:
                json.dump(self.transactions, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"交易记录已保存，共 {len(self.transactions)} 条")
        except Exception as e:
            logger.error(f"保存交易记录失败: {e}")
    
    def load_transactions(self) -> None:
        """加载历史交易记录"""
        try:
            if os.path.exists('transaction_history.json'):
                with open('transaction_history.json', 'r', encoding='utf-8') as f:
                    self.transactions = json.load(f)
                    
                # 重建未平仓记录
                self.open_positions = defaultdict(list)
                for transaction in self.transactions:
                    if transaction['action'] == 'buy' and not transaction.get('closed', False):
                        self.open_positions[transaction['symbol']].append(transaction)
                
                logger.info(f"成功加载{len(self.transactions)}条交易记录")
            else:
                logger.info("交易记录文件不存在，使用空记录")
        except Exception as e:
            logger.error(f"加载交易历史失败: {e}")
            self.transactions = []
            self.open_positions = defaultdict(list)
    
    def calculate_profit(self, sell_transaction: Dict[str, Any]) -> Dict[str, Any]:
        """计算卖出交易的利润
        
        根据卖出交易信息，匹配合适的买入交易，计算利润
        
        Args:
            sell_transaction (Dict[str, Any]): 卖出交易记录
            
        Returns:
            Dict[str, Any]: 包含利润信息的字典
        """
        symbol = sell_transaction['symbol']
        sell_quantity = sell_transaction['quantity']
        sell_price = sell_transaction['price']
        remaining_quantity = sell_quantity
        
        profit_details = {
            'total_profit': 0.0,
            'total_profit_percent': 0.0,
            'matched_buys': [],
            'unmatched_quantity': 0
        }
        
        # 如果该股票没有未平仓记录，返回0利润
        if symbol not in self.open_positions or not self.open_positions[symbol]:
            profit_details['unmatched_quantity'] = sell_quantity
            logger.warning(f"卖出 {symbol} 时没有找到对应的买入记录，数量: {sell_quantity}")
            return profit_details
        
        # 尝试匹配买入记录（使用先进先出FIFO原则）
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
            
            # 记录匹配信息并更新总利润
            match_info = {
                'buy_order_id': buy_transaction['order_id'],
                'buy_price': buy_transaction['price'],
                'match_quantity': match_quantity,
                'profit': profit,
                'profit_percent': profit_percent
            }
            profit_details['matched_buys'].append(match_info)
            profit_details['total_profit'] += profit
            
            # 更新剩余数量
            remaining_quantity -= match_quantity
            
            # 更新买入记录和交易历史
            if match_quantity == buy_transaction['quantity']:
                # 全部匹配，标记为已平仓
                buy_transaction['closed'] = True
                self.open_positions[symbol].remove(buy_transaction)
            else:
                # 部分匹配，更新数量
                buy_transaction['quantity'] -= match_quantity
            
            # 更新交易历史中的对应记录
            for t in self.transactions:
                if t['order_id'] == buy_transaction['order_id']:
                    t.update(buy_transaction)
                    break
        
        # 如果卖出数量没有完全匹配
        if remaining_quantity > 0:
            profit_details['unmatched_quantity'] = remaining_quantity
            logger.warning(f"卖出 {symbol} 有 {remaining_quantity} 股未找到匹配的买入记录")
        
        # 计算总收益率
        total_buy_cost = sum(b['buy_price'] * b['match_quantity'] for b in profit_details['matched_buys'])
        if total_buy_cost > 0:
            profit_details['total_profit_percent'] = (profit_details['total_profit'] / total_buy_cost) * 100
        
        return profit_details
    
    def buy_stock(self, symbol, quantity, price=None):
        """买入股票
        
        Args:
            symbol (str): 股票代码
            quantity (int): 买入数量
            price (float, optional): 买入价格，None表示使用当前价格
            
        Returns:
            dict: 交易结果，包含success、order_id、transaction等字段
        """
        try:
            # 如果没有提供价格，使用当前价格
            if price is None:
                quote = self.get_real_time_quote(symbol)
                if not quote:
                    logger.error(f"无法获取{symbol}的价格信息")
                    return {'success': False, 'error': '无法获取价格信息'}
                price = quote['last_price']
            
            # 执行买入
            result = self.place_order(symbol, 'buy', quantity, price)
            
            # 处理place_order的返回结果
            if result and isinstance(result, dict):
                if 'success' in result and result['success']:
                    # 获取最新持仓信息
                    positions = self.get_current_positions()
                    if symbol in positions:
                        # 确保类型一致
                        pos_quantity = float(positions[symbol]['quantity'])
                        cost_price = float(positions[symbol]['cost_price'])
                        self.stock_data[symbol]['position'] = pos_quantity * cost_price
                        self.stock_data[symbol]['position_quantity'] = pos_quantity
                        self.stock_data[symbol]['average_cost'] = cost_price  # 直接使用API返回的平均成本
                elif 'order_id' in result:  # 模拟下单成功
                    return {'success': True, 'order_id': result['order_id'], 'transaction': result}
            
            return result if result else {'success': False, 'error': '未知错误'}
        except Exception as e:
            logger.error(f"买入股票{symbol}时出错: {e}")
            return {'success': False, 'error': str(e)}
    
    def sell_stock(self, symbol, quantity):
        """卖出股票
        
        Args:
            symbol (str): 股票代码
            quantity (int): 卖出数量
            
        Returns:
            dict: 交易结果，包含success、order_id、transaction等字段
        """
        try:
            # 检查持仓
            positions = self.get_current_positions()
            if symbol not in positions:
                logger.warning(f"没有{symbol}的持仓")
                return {'success': False, 'error': f'没有{symbol}的持仓'}
            
            available_quantity = positions[symbol].get('available_quantity', 0)
            if quantity > available_quantity:
                logger.warning(f"卖出数量超过可用持仓: 请求{quantity}，可用{available_quantity}")
                return {'success': False, 'error': f'卖出数量超过可用持仓: 请求{quantity}，可用{available_quantity}'}
            
            # 获取当前价格作为卖出价格
            quote = self.get_real_time_quote(symbol)
            if not quote:
                logger.error(f"无法获取{symbol}的价格信息")
                return {'success': False, 'error': '无法获取价格信息'}
            
            price = quote['last_price']
            
            # 执行卖出
            result = self.place_order(symbol, 'sell', quantity, price)
            
            # 处理place_order的返回结果
            if result and isinstance(result, dict):
                if 'success' in result and result['success']:
                    # 获取最新持仓信息
                    updated_positions = self.get_current_positions()
                    if symbol in updated_positions:
                        # 确保类型一致
                        pos_quantity = float(updated_positions[symbol]['quantity'])
                        cost_price = float(updated_positions[symbol]['cost_price'])
                        self.stock_data[symbol]['position'] = pos_quantity * cost_price
                    else:
                        self.stock_data[symbol]['position'] = 0
                elif 'order_id' in result:  # 模拟下单成功
                    return {'success': True, 'order_id': result['order_id'], 'transaction': result}
            
            return result if result else {'success': False, 'error': '未知错误'}
        except Exception as e:
            logger.error(f"卖出股票{symbol}时出错: {e}")
            return {'success': False, 'error': str(e)}
    
    def process_stock(self, symbol: str, stock_info: Dict[str, Any]) -> None:
        """处理单只股票的监控逻辑
        
        Args:
            symbol (str): 股票代码
            stock_info (Dict[str, Any]): 股票监控信息
        """
        try:
            # 获取实时行情
            quote = self.get_real_time_quote(symbol)
            if not quote:
                logger.error(f"无法获取{symbol}的行情数据")
                return
            
            # 如果是第一次运行，初始化价格
            if stock_info['previous_price'] is None:
                stock_info['previous_price'] = quote['last_price']
                logger.info(f"初始化{symbol}价格: {quote['last_price']}")
            
            # 调用Ollama进行AI分析并执行决策
            stock_data = self.stock_data.get(symbol, {})
            decision = self.analyze_with_ollama(stock_data, quote)
            
            # 执行决策
            if decision['instruction'] == 'buy':
                logger.info(f"执行买入操作: {symbol}, 数量: {decision['quantity']}, 价格: {quote['last_price']}, 理由: {decision['reason']}")
                result = self.buy_stock(symbol, decision['quantity'], quote['last_price'])
                if result['success']:
                    logger.info(f"买入成功: {symbol}")
                else:
                    logger.info(f"买入失败: {symbol}, 原因: {result.get('error', '未知错误')}")
            elif decision['instruction'] == 'sell':
                logger.info(f"执行卖出操作: {symbol}, 数量: {decision['quantity']}, 价格: {quote['last_price']}, 理由: {decision['reason']}")
                result = self.sell_stock(symbol, decision['quantity'])
                if result['success']:
                    logger.info(f"卖出成功: {symbol}")
                else:
                    logger.info(f"卖出失败: {symbol}, 原因: {result.get('error', '未知错误')}")
            else:
                logger.info(f"执行持有策略: {symbol}, 理由: {decision['reason']}")
            
            # 更新价格
            stock_info['previous_price'] = quote['last_price']
            
        except Exception as e:
            logger.error(f"处理{symbol}时出错: {e}")

    def time_control(self):
        """检查当前时间是否在交易时间区间内
        
        Returns:
            bool: True表示在交易时间内，False表示不在
        """
        from datetime import datetime
        
        time_format = "%H:%M"
        now = datetime.now()
        current_time = datetime.strptime(now.strftime(time_format), time_format)
        
        # 从配置读取时间区间，默认值为原硬编码值
        start_time = self.config.get('trading_time', {}).get('start', "22:00")
        end_time = self.config.get('trading_time', {}).get('end', "05:00")
        
        start = datetime.strptime(start_time, time_format)
        end = datetime.strptime(end_time, time_format)
        
        # 判断是否在时间区间内
        if start > end:
            # 跨天情况：当前时间 >= 开始时间 或者 当前时间 < 结束时间
            return current_time >= start or current_time < end
        else:
            # 同一天情况：当前时间在开始时间和结束时间之间
            return start <= current_time < end

    def start_monitoring(self) -> None:
        """启动股票监控
        
        定期监控所有配置的股票，分析并执行交易决策
        """
        logger.info("开始股票监控...")
        
        try:
            while True:
                is_trading_time = self.time_control()
                print(f"当前{'在' if is_trading_time else '不在'}交易时间区间内")
                if is_trading_time:
                    for symbol, stock_info in self.stock_data.items():
                        self.process_stock(symbol, stock_info)
                    check_interval = self.config.get('check_interval', 30)  # 默认60秒检查一次
                    logger.info(f"等待{check_interval}秒后进行下一次检查...")
                    time.sleep(check_interval)
                else:
                    logger.info("当前时间不在交易时间区间内，等待到交易时间开始...")
                    time.sleep(60)  # 每分钟检查一次
                
                
        except KeyboardInterrupt:
            logger.info("用户中断，停止监控")
        except Exception as e:
            logger.error(f"监控过程中出错: {e}")

if __name__ == "__main__":
    try:
        monitor = StockMonitor()
        monitor.start_monitoring()
    except Exception as e:
        logger.error(f"程序启动失败: {e}")
        print(f"错误: {e}")