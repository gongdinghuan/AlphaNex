#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易模块

负责处理交易相关的功能，包括下单、交易记录管理和利润计算。
"""

import threading
from datetime import datetime
from decimal import Decimal
from utils import get_logger, save_json, load_json

class TradeManager:
    """交易管理器"""
    
    def __init__(self, config, positions_manager):
        """初始化交易管理器
        
        Args:
            config (dict): 配置信息
            positions_manager: 持仓管理器实例
        """
        self.config = config
        self.positions_manager = positions_manager
        self.transaction_history = []
        self.transaction_lock = threading.Lock()
        self.logger = get_logger("TradeManager")
        self.transactions_file = config.get("transactions_file", "transactions.json")
        self.load_transactions()
    
    def save_transactions(self):
        """保存交易记录到文件"""
        with self.transaction_lock:
            success = save_json(self.transaction_history, self.transactions_file)
            if success:
                self.logger.info(f"交易记录已保存，共 {len(self.transaction_history)} 条记录")
            return success
    
    def load_transactions(self):
        """从文件加载交易记录"""
        data = load_json(self.transactions_file)
        if data:
            with self.transaction_lock:
                self.transaction_history = data
                self.logger.info(f"已加载 {len(self.transaction_history)} 条交易记录")
    
    def calculate_profit(self):
        """计算交易利润，使用FIFO原则
        
        Returns:
            dict: 利润计算结果
        """
        with self.transaction_lock:
            if not self.transaction_history:
                return {"total_profit": 0, "total_trades": 0, "profit_details": []}
            
            # 按股票分组交易记录
            stock_trades = {}
            for trade in self.transaction_history:
                symbol = trade.get("symbol")
                if symbol not in stock_trades:
                    stock_trades[symbol] = []
                stock_trades[symbol].append(trade)
            
            total_profit = 0
            profit_details = []
            
            # 对每只股票单独计算利润
            for symbol, trades in stock_trades.items():
                # 按时间排序
                sorted_trades = sorted(trades, key=lambda x: x.get("timestamp"))
                buy_positions = []  # 记录买入的仓位
                symbol_profit = 0
                
                for trade in sorted_trades:
                    direction = trade.get("direction")
                    quantity = Decimal(str(trade.get("quantity")))
                    price = Decimal(str(trade.get("price")))
                    amount = quantity * price
                    
                    if direction == "BUY":
                        # 添加到买入仓位列表
                        buy_positions.append({
                            "quantity": quantity,
                            "price": price,
                            "amount": amount,
                            "timestamp": trade.get("timestamp")
                        })
                    elif direction == "SELL":
                        remaining_quantity = quantity
                        sell_amount = amount
                        cost = 0
                        
                        # 使用FIFO原则匹配卖出和买入
                        while remaining_quantity > 0 and buy_positions:
                            buy = buy_positions[0]
                            if buy["quantity"] <= remaining_quantity:
                                # 完全匹配这个买入仓位
                                cost += buy["amount"]
                                remaining_quantity -= buy["quantity"]
                                buy_positions.pop(0)
                            else:
                                # 部分匹配
                                partial_cost = buy["price"] * remaining_quantity
                                cost += partial_cost
                                buy["quantity"] -= remaining_quantity
                                buy["amount"] = buy["quantity"] * buy["price"]
                                remaining_quantity = 0
                        
                        # 计算这次卖出的利润
                        if cost > 0:
                            trade_profit = sell_amount - cost
                            symbol_profit += trade_profit
                            total_profit += trade_profit
                            
                            profit_details.append({
                                "symbol": symbol,
                                "sell_timestamp": trade.get("timestamp"),
                                "sell_price": float(price),
                                "quantity": float(quantity),
                                "cost": float(cost),
                                "profit": float(trade_profit),
                                "profit_percent": float(trade_profit / cost * 100) if cost > 0 else 0
                            })
                
                if symbol_profit != 0:
                    self.logger.info(f"股票 {symbol} 总利润: {symbol_profit:.2f}")
            
            return {
                "total_profit": float(total_profit),
                "total_trades": len(profit_details),
                "profit_details": profit_details
            }
    
    def get_last_buy_price_info(self, symbol):
        """获取最近的买入价格信息
        
        Args:
            symbol (str): 股票代码
            
        Returns:
            dict: 买入价格信息
        """
        with self.transaction_lock:
            # 筛选出该股票的买入记录，并按时间倒序排列
            buy_trades = [
                trade for trade in self.transaction_history 
                if trade.get("symbol") == symbol and trade.get("direction") == "BUY"
            ]
            buy_trades.sort(key=lambda x: x.get("timestamp"), reverse=True)
            
            if not buy_trades:
                return {"has_position": False, "current_price": 0, "last_buy_price": 0, "price_diff": 0, "price_diff_percent": 0}
            
            last_buy = buy_trades[0]
            last_buy_price = Decimal(str(last_buy.get("price")))
            
            # 获取当前持仓
            position = self.positions_manager.get_position(symbol)
            if not position or position.get("quantity", 0) <= 0:
                return {"has_position": False, "current_price": 0, "last_buy_price": float(last_buy_price), "price_diff": 0, "price_diff_percent": 0}
            
            current_price = Decimal(str(position.get("current_price", 0)))
            price_diff = current_price - last_buy_price
            price_diff_percent = (price_diff / last_buy_price * 100) if last_buy_price > 0 else 0
            
            return {
                "has_position": True,
                "current_price": float(current_price),
                "last_buy_price": float(last_buy_price),
                "price_diff": float(price_diff),
                "price_diff_percent": float(price_diff_percent)
            }
    
    def place_order(self, symbol, direction, quantity, price, is_simulated=True):
        """执行下单操作
        
        Args:
            symbol (str): 股票代码
            direction (str): 买卖方向，"BUY"或"SELL"
            quantity (float): 交易数量
            price (float): 交易价格
            is_simulated (bool): 是否为模拟交易
            
        Returns:
            dict: 订单结果
        """
        try:
            # 检查持仓限制
            if direction == "BUY":
                # 检查资金限制
                available_funds = self.positions_manager.get_available_funds()
                total_amount = quantity * price
                if total_amount > available_funds and not is_simulated:
                    self.logger.warning(f"资金不足: 需要 {total_amount}, 可用 {available_funds}")
                    return {"success": False, "message": "资金不足"}
            else:
                # 检查持仓限制
                position = self.positions_manager.get_position(symbol)
                if not position or position.get("quantity", 0) < quantity:
                    self.logger.warning(f"持仓不足: 需要 {quantity}, 可用 {position.get('quantity', 0) if position else 0}")
                    return {"success": False, "message": "持仓不足"}
            
            # 构建订单信息
            order_info = {
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "price": price,
                "total_amount": quantity * price,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "simulated": is_simulated
            }
            
            # 更新交易历史
            with self.transaction_lock:
                self.transaction_history.append(order_info)
                self.save_transactions()
            
            # 更新持仓
            success = self.positions_manager.update_position(symbol, direction, quantity, price, is_simulated)
            
            if success:
                self.logger.info(f"{'模拟' if is_simulated else '真实'}下单成功: {direction} {symbol} {quantity}股 @ {price}")
                return {"success": True, "order": order_info}
            else:
                self.logger.error(f"更新持仓失败")
                # 回滚交易历史
                with self.transaction_lock:
                    if order_info in self.transaction_history:
                        self.transaction_history.remove(order_info)
                        self.save_transactions()
                return {"success": False, "message": "更新持仓失败"}
                
        except Exception as e:
            self.logger.error(f"下单失败: {e}")
            return {"success": False, "message": str(e)}