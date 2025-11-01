#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV数据导入到SQLite数据库脚本

该脚本用于将account_daily_log.csv文件中的历史数据导入到account_data.db数据库中
"""

import os
import csv
import sqlite3
from datetime import datetime

def import_csv_to_database(csv_path, db_path):
    """
    将CSV文件数据导入到SQLite数据库
    
    Args:
        csv_path (str): CSV文件路径
        db_path (str): 数据库文件路径
    """
    print(f"开始导入CSV数据到数据库...")
    print(f"CSV文件: {csv_path}")
    print(f"数据库文件: {db_path}")
    
    # 检查CSV文件是否存在
    if not os.path.exists(csv_path):
        print(f"错误: CSV文件不存在 - {csv_path}")
        return
    
    try:
        # 连接到数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 确保表结构存在
        init_database_tables(cursor)
        
        # 读取CSV文件并导入数据
        imported_count = 0
        skipped_count = 0
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    # 处理日期格式，将'2025/10/29'格式转换为'2025-10-29'
                    date_str = row['日期']
                    if '/' in date_str:
                        # 转换格式：2025/10/29 -> 2025-10-29
                        try:
                            date_obj = datetime.strptime(date_str, '%Y/%m/%d')
                            date_str = date_obj.strftime('%Y-%m-%d')
                        except ValueError:
                            # 如果转换失败，保留原格式
                            pass
                    
                    # 处理时间戳格式
                    timestamp_str = row['时间戳']
                    if '/' in timestamp_str:
                        # 转换格式：2025/10/29 20:24 -> 2025-10-29 20:24:00
                        try:
                            timestamp_obj = datetime.strptime(timestamp_str, '%Y/%m/%d %H:%M')
                            timestamp_str = timestamp_obj.strftime('%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            try:
                                # 尝试其他可能的格式
                                timestamp_obj = datetime.strptime(timestamp_str, '%Y/%m/%d %H:%M:%S')
                                timestamp_str = timestamp_obj.strftime('%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                # 如果转换失败，保留原格式
                                pass
                    
                    # 检查是否已存在相同的记录（通过时间戳判断）
                    cursor.execute(
                        "SELECT id FROM account_logs WHERE timestamp = ?",
                        (timestamp_str,)
                    )
                    
                    if cursor.fetchone():
                        # 记录已存在，跳过
                        skipped_count += 1
                        continue
                    
                    # 准备数据
                    net_assets = float(row['净资产'])
                    yesterday_net_assets = float(row['昨日净资产'])
                    daily_profit = float(row['当日盈亏'])
                    daily_return_rate = row['当日收益率']
                    # 确保收益率格式正确（带有%符号）
                    if not daily_return_rate.endswith('%'):
                        daily_return_rate = f"{daily_return_rate}%"
                    
                    total_cash = float(row['现金总额'])
                    buy_power = float(row['购买力'])
                    risk_level = int(row['风险等级'])
                    
                    # 插入数据
                    cursor.execute('''
                        INSERT INTO account_logs 
                        (date, timestamp, net_assets, yesterday_net_assets, daily_profit, 
                         daily_return_rate, total_cash, buy_power, risk_level)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        date_str,
                        timestamp_str,
                        net_assets,
                        yesterday_net_assets,
                        daily_profit,
                        daily_return_rate,
                        total_cash,
                        buy_power,
                        risk_level
                    ))
                    
                    imported_count += 1
                    
                    # 每导入10条记录打印一次进度
                    if imported_count % 10 == 0:
                        print(f"已导入 {imported_count} 条记录...")
                    
                except Exception as e:
                    print(f"处理行数据时出错: {e}")
                    print(f"问题行: {row}")
                    continue
        
        # 提交事务
        conn.commit()
        conn.close()
        
        print(f"\n导入完成！")
        print(f"成功导入: {imported_count} 条记录")
        print(f"跳过（已存在）: {skipped_count} 条记录")
        print(f"数据库文件已更新: {db_path}")
        
    except Exception as e:
        print(f"导入过程中发生错误: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

def init_database_tables(cursor):
    """
    初始化数据库表结构
    
    Args:
        cursor: SQLite游标对象
    """
    try:
        # 创建账户日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                net_assets REAL NOT NULL,
                yesterday_net_assets REAL NOT NULL,
                daily_profit REAL NOT NULL,
                daily_return_rate TEXT NOT NULL,
                total_cash REAL NOT NULL,
                buy_power REAL NOT NULL,
                risk_level INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建账户详情表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL,
                currency TEXT NOT NULL,
                withdraw_cash REAL NOT NULL,
                available_cash REAL NOT NULL,
                frozen_cash REAL NOT NULL,
                settling_cash REAL NOT NULL,
                FOREIGN KEY (log_id) REFERENCES account_logs (id)
            )
        ''')
        
        # 创建冻结费用表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS frozen_fees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL,
                currency TEXT NOT NULL,
                frozen_fee REAL NOT NULL,
                FOREIGN KEY (log_id) REFERENCES account_logs (id)
            )
        ''')
        
        print("数据库表结构检查完成")
        
    except Exception as e:
        print(f"初始化数据库表结构时出错: {e}")
        raise

def main():
    """
    主函数
    """
    # 获取当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # CSV文件路径
    csv_path = os.path.join(script_dir, 'account_daily_log.csv')
    
    # 数据库文件路径
    db_path = os.path.join(script_dir, 'account_data.db')
    
    # 执行导入
    import_csv_to_database(csv_path, db_path)
    
    # 显示数据库中的记录数
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM account_logs")
        total_records = cursor.fetchone()[0]
        conn.close()
        print(f"\n数据库中总记录数: {total_records}")
        
    except Exception as e:
        print(f"查询数据库记录数时出错: {e}")

if __name__ == "__main__":
    print("========== CSV数据导入工具 ==========\n")
    main()
    print("\n========== 导入完成 ==========")