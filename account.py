#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票账户信息查询脚本

该脚本使用LongPort API获取账户资金信息，并按照API文档格式输出
包括账户余额、现金详情、可用资金、购买力等，以及计算当日收益率和盈亏金额
同时将每日账户收益和金额保存到日志文件中
参考文档: https://open.longportapp.com/zh-CN/docs/trade/asset/account
"""

from longport.openapi import Config, TradeContext
import yaml
import json
from datetime import datetime
import os
import csv

class AccountInfoFormatter:
    """账户信息格式化类"""
    
    def __init__(self, config_file='config.yaml'):
        """初始化并加载配置
        
        Args:
            config_file (str): 配置文件路径
        """
        self.load_config(config_file)
        self.ctx = self.create_trade_context()
        # 从日志文件读取昨日净资产，如果文件不存在或没有记录，则使用默认值
        self.yesterday_net_assets = self._get_yesterday_net_assets()
    
    def _get_yesterday_net_assets(self):
        """从历史日志文件获取昨日净资产
        
        Returns:
            float: 昨日净资产值
        """
        log_file = "account_daily_log.csv"
        default_value = 805000.0  # 默认值
        
        if not os.path.isfile(log_file):
            print(f"历史日志文件 {log_file} 不存在，使用默认昨日净资产值")
            return default_value
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                # 获取所有记录
                records = list(reader)
                
                if not records:
                    print("历史日志文件为空，使用默认昨日净资产值")
                    return default_value
                
                # 按时间戳排序，获取最新的记录
                def parse_timestamp(timestamp_str):
                    # 支持多种日期格式
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M']:
                        try:
                            return datetime.strptime(timestamp_str, fmt)
                        except ValueError:
                            continue
                    # 如果都解析失败，返回一个很早的时间
                    return datetime.min
                
                records.sort(key=lambda x: parse_timestamp(x['时间戳']), reverse=True)
                
                # 获取最新记录的净资产作为昨日净资产
                latest_record = records[0]
                yesterday_assets = float(latest_record['净资产'])
                print(f"从历史日志获取昨日净资产: {yesterday_assets}")
                return yesterday_assets
                
        except Exception as e:
            print(f"读取历史日志文件失败: {e}，使用默认昨日净资产值")
            return default_value
    
    def load_config(self, config_file):
        """加载配置文件
        
        Args:
            config_file (str): 配置文件路径
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f)
            print(f"配置文件加载成功: {config_file}")
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            raise
    
    def create_trade_context(self):
        """创建交易上下文对象
        
        Returns:
            TradeContext: 交易上下文对象
        """
        config = Config(
            app_key=self.config_data['longport']['app_key'],
            app_secret=self.config_data['longport']['app_secret'],
            access_token=self.config_data['longport']['access_token']
        )
        return TradeContext(config)
    
    def get_account_balance(self):
        """获取账户余额信息
        
        Returns:
            list: 账户余额信息列表
        """
        try:
            resp = self.ctx.account_balance()
            print("\n账户信息获取成功")
            return resp
        except Exception as e:
            print(f"获取账户信息失败: {e}")
            return []
    
    def calculate_daily_performance(self, current_net_assets):
        """计算当日收益率和盈亏金额
        
        Args:
            current_net_assets (float): 当前净资产
            
        Returns:
            dict: 包含详细性能指标的字典
        """
        daily_profit = current_net_assets - self.yesterday_net_assets
        daily_return_rate = (daily_profit / self.yesterday_net_assets) * 100
        
        # 确定盈亏状态
        profit_status = "盈利" if daily_profit > 0 else "亏损" if daily_profit < 0 else "持平"
        
        # 计算相对表现级别（简单分类）
        if abs(daily_return_rate) < 0.5:
            performance_level = "轻微波动"
        elif abs(daily_return_rate) < 1.0:
            performance_level = "小幅波动"
        elif abs(daily_return_rate) < 3.0:
            performance_level = "中幅波动"
        else:
            performance_level = "大幅波动"
        
        return {
            'daily_profit': daily_profit,
            'daily_return_rate': daily_return_rate,
            'yesterday_net_assets': self.yesterday_net_assets,
            'current_net_assets': current_net_assets,
            'profit_status': profit_status,
            'performance_level': performance_level
        }
    
    def format_risk_level(self, risk_level):
        """格式化风险等级
        
        Args:
            risk_level: 风险等级代码（可能是字符串或数字）
            
        Returns:
            str: 风险等级描述
        """
        # 转换为字符串以便进行映射
        risk_str = str(risk_level)
        risk_map = {
            '0': '安全',
            '1': '正常',
            '2': '预警',
            '3': '危险'
        }
        return risk_map.get(risk_str, f'未知({risk_str})')
    
    def format_cash_info(self, cash_info):
        """格式化现金信息
        
        Args:
            cash_info: CashInfo对象
            
        Returns:
            dict: 格式化后的现金信息
        """
        return {
            '币种': cash_info.currency,
            '可提现金': f"{float(cash_info.withdraw_cash):,.2f}",
            '可用现金': f"{float(cash_info.available_cash):,.2f}",
            '冻结现金': f"{float(cash_info.frozen_cash):,.2f}",
            '待结算现金': f"{float(cash_info.settling_cash):,.2f}"
        }
    
    def format_frozen_fees(self, frozen_fees):
        """格式化冻结费用信息
        
        Args:
            frozen_fees: FrozenTransactionFee对象列表
            
        Returns:
            list: 格式化后的冻结费用列表
        """
        result = []
        for fee in frozen_fees:
            result.append({
                '币种': fee.currency,
                '冻结费用': f"{float(fee.frozen_transaction_fee):,.2f}"
            })
        return result
    
    def pretty_print(self, account_data, performance):
        """美化打印账户信息
        
        Args:
            account_data: AccountBalance对象
            performance: 当日表现数据字典
        """
        print("\n" + "="*60)
        print(f"账户资金信息 - 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        # 基本账户信息
        print(f"\n【基本信息】")
        print(f"主币种: {account_data.currency}")
        print(f"现金总额: {float(account_data.total_cash):,.2f} {account_data.currency}")
        print(f"净资产: {float(account_data.net_assets):,.2f} {account_data.currency}")
        
        # 当日表现（增强版）
        print(f"\n【当日表现】")
        print(f"昨日净资产: {performance['yesterday_net_assets']:,.2f} {account_data.currency}")
        print(f"当前净资产: {performance['current_net_assets']:,.2f} {account_data.currency}")
        
        # 带颜色的盈亏显示
        daily_profit = performance['daily_profit']
        profit_str = f"{daily_profit:,.2f} {account_data.currency}"
        if daily_profit > 0:
            profit_display = f"当日盈亏: +{profit_str} (↑)"
        elif daily_profit < 0:
            profit_display = f"当日盈亏: {profit_str} (↓)"
        else:
            profit_display = f"当日盈亏: {profit_str} (→)"
        print(profit_display)
        
        # 收益率显示
        daily_return_rate = performance['daily_return_rate']
        return_str = f"{daily_return_rate:.2f}%"
        if daily_return_rate > 0:
            return_display = f"当日收益率: +{return_str} (↑)"
        elif daily_return_rate < 0:
            return_display = f"当日收益率: {return_str} (↓)"
        else:
            return_display = f"当日收益率: {return_str} (→)"
        print(return_display)
        
        # 盈亏状态和波动级别
        print(f"盈亏状态: {performance['profit_status']}")
        print(f"波动级别: {performance['performance_level']}")
        
        # 融资信息
        print(f"\n【融资信息】")
        print(f"最大融资金额: {float(account_data.max_finance_amount):,.2f} {account_data.currency}")
        print(f"剩余融资金额: {float(account_data.remaining_finance_amount):,.2f} {account_data.currency}")
        
        # 保证金信息
        print(f"\n【保证金信息】")
        print(f"初始保证金: {float(account_data.init_margin):,.2f} {account_data.currency}")
        print(f"维持保证金: {float(account_data.maintenance_margin):,.2f} {account_data.currency}")
        print(f"购买力: {float(account_data.buy_power):,.2f} {account_data.currency}")
        
        # 风险等级显示（增强）
        risk_level = self.format_risk_level(account_data.risk_level)
        risk_color = "🟢" if risk_level == "安全" else "🟡" if risk_level == "正常" else "🟠" if risk_level == "预警" else "🔴"
        print(f"风险等级: {risk_color} {risk_level}")
        
        # 现金详情
        print(f"\n【现金详情】")
        for cash_info in account_data.cash_infos:
            formatted = self.format_cash_info(cash_info)
            print(f"  - {formatted['币种']}:")
            print(f"    可提现金: {formatted['可提现金']}")
            print(f"    可用现金: {formatted['可用现金']}")
            print(f"    冻结现金: {formatted['冻结现金']}")
            print(f"    待结算现金: {formatted['待结算现金']}")
        
        # 冻结费用
        if account_data.frozen_transaction_fees:
            print(f"\n【冻结费用】")
            for fee in self.format_frozen_fees(account_data.frozen_transaction_fees):
                print(f"  - {fee['币种']}: {fee['冻结费用']}")
        
        print("="*60)
    
    def to_json(self, account_data, performance):
        """转换为JSON格式
        
        Args:
            account_data: AccountBalance对象
            performance: 当日表现数据字典
            
        Returns:
            dict: JSON格式的账户信息
        """
        result = {
            "查询时间": datetime.now().isoformat(),
            "基本信息": {
                "主币种": account_data.currency,
                "现金总额": float(account_data.total_cash),
                "净资产": float(account_data.net_assets)
            },
            "当日表现": performance,
            "融资信息": {
                "最大融资金额": float(account_data.max_finance_amount),
                "剩余融资金额": float(account_data.remaining_finance_amount)
            },
            "保证金信息": {
                "初始保证金": float(account_data.init_margin),
                "维持保证金": float(account_data.maintenance_margin),
                "购买力": float(account_data.buy_power),
                "风险等级": account_data.risk_level,
                "风险等级描述": self.format_risk_level(account_data.risk_level)
            },
            "现金详情": [self.format_cash_info(cash) for cash in account_data.cash_infos]
        }
        
        if account_data.frozen_transaction_fees:
            result["冻结费用"] = self.format_frozen_fees(account_data.frozen_transaction_fees)
        
        return result
    
    def save_to_log(self, account_data, performance):
        """将账户收益和金额保存到日志文件
        
        Args:
            account_data: AccountBalance对象
            performance: 当日表现数据字典
        """
        log_file = "account_daily_log.csv"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date = datetime.now().strftime("%Y-%m-%d")
        
        # 准备日志数据
        log_data = [
            date,
            timestamp,
            float(account_data.net_assets),
            performance['yesterday_net_assets'],
            performance['daily_profit'],
            f"{performance['daily_return_rate']:.2f}%",
            float(account_data.total_cash),
            float(account_data.buy_power),
            account_data.risk_level
        ]
        
        # 检查文件是否存在，不存在则创建并写入表头
        file_exists = os.path.isfile(log_file)
        
        try:
            with open(log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    # 写入表头
                    headers = [
                        '日期', '时间戳', '净资产', '昨日净资产', 
                        '当日盈亏', '当日收益率', '现金总额', '购买力', '风险等级'
                    ]
                    writer.writerow(headers)
                # 写入数据
                writer.writerow(log_data)
            print(f"\n账户日志已成功保存到 {log_file}")
        except Exception as e:
            print(f"保存日志文件失败: {e}")
    
    def run(self):
        """运行主程序"""
        # 获取账户信息
        accounts = self.get_account_balance()
        
        if not accounts:
            print("未获取到账户信息")
            return
        
        for account in accounts:
            # 计算当日表现
            performance = self.calculate_daily_performance(float(account.net_assets))
            
            # 美化打印
            self.pretty_print(account, performance)
            
            # 保存到日志文件
            self.save_to_log(account, performance)
            
            # 输出JSON格式（可选）
            # json_data = self.to_json(account, performance)
            # print("\nJSON格式输出:")
            # print(json.dumps(json_data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    formatter = AccountInfoFormatter()
    formatter.run()