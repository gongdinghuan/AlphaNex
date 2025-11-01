#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
定时任务调度器脚本
功能：使用APScheduler实现灵活的定时任务调度
可配置不同类型的任务（间隔执行、定时执行、Cron表达式）
"""

import os
import sys
import time
import logging
import subprocess
import signal
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

# 全局变量，用于存储 stock_monitor.py 的进程ID
stock_monitor_process = None

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scheduler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('scheduler')

# 任务配置示例
JOBS_CONFIG = [
    {
        'id': 'account_update',
        'func': 'account:run_main',  # 调用account.py中的run_main函数
        'trigger': 'interval',
        'seconds': 600,  # 每10分钟执行一次
        'args': (),
        'kwargs': {},
        'name': '账户数据更新',
        'replace_existing': True
    }
]

def setup_scheduler():
    """
    设置并配置调度器
    """
    # 配置调度器
    jobstores = {
        'default': MemoryJobStore()
    }
    executors = {
        'default': ThreadPoolExecutor(10)  # 10个线程的线程池
    }
    job_defaults = {
        'coalesce': False,  # 不合并任务
        'max_instances': 1,  # 每个任务最多运行一个实例
        'misfire_grace_time': 60  # 任务错过执行的宽限时间（秒）
    }
    
    # 创建调度器
    scheduler = BlockingScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone='Asia/Shanghai'
    )
    
    return scheduler

def load_external_function(func_path):
    """
    动态加载外部函数
    格式：module:function_name
    """
    try:
        module_name, function_name = func_path.split(':')
        module = __import__(module_name)
        return getattr(module, function_name)
    except Exception as e:
        logger.error(f"加载函数 {func_path} 失败: {str(e)}")
        raise

def register_jobs(scheduler):
    """
    注册所有任务
    """
    for job_config in JOBS_CONFIG:
        try:
            # 复制配置以避免修改原始数据
            job_args = job_config.copy()
            
            # 处理触发器配置
            trigger_type = job_args.pop('trigger')
            if trigger_type == 'interval':
                # 移除trigger键，剩下的都是interval trigger的参数
                trigger_args = {k: v for k, v in job_args.items() 
                              if k in ['weeks', 'days', 'hours', 'minutes', 'seconds', 'start_date', 'end_date', 'timezone']}
                # 从job_args中移除trigger参数
                for k in trigger_args:
                    job_args.pop(k, None)
                trigger = IntervalTrigger(**trigger_args)
            
            elif trigger_type == 'cron':
                # 移除trigger键，剩下的都是cron trigger的参数
                trigger_args = {k: v for k, v in job_args.items() 
                              if k in ['year', 'month', 'day', 'week', 'day_of_week', 'hour', 'minute', 'second', 
                                      'start_date', 'end_date', 'timezone']}
                # 从job_args中移除trigger参数
                for k in trigger_args:
                    job_args.pop(k, None)
                trigger = CronTrigger(**trigger_args)
            
            elif trigger_type == 'date':
                # 一次性任务
                run_date = job_args.pop('run_date', datetime.now())
                trigger = DateTrigger(run_date=run_date)
            
            else:
                logger.error(f"未知的触发器类型: {trigger_type}")
                continue
            
            # 加载函数
            func_path = job_args.pop('func')
            func = load_external_function(func_path)
            
            # 添加任务到调度器
            scheduler.add_job(
                func=func,
                trigger=trigger,
                **job_args
            )
            
            logger.info(f"成功注册任务: {job_args.get('name', job_args.get('id'))}")
            
        except Exception as e:
            logger.error(f"注册任务 {job_config.get('id')} 失败: {str(e)}")

def start_stock_monitor():
    """
    启动 stock_monitor.py 脚本
    """
    global stock_monitor_process
    try:
        # 检查是否已经在运行
        if stock_monitor_process is not None and stock_monitor_process.poll() is None:
            logger.info("stock_monitor.py 已经在运行中")
            return
        
        # 构建运行命令，切换到正确的目录
        stock_monitor_path = "/Users/gongdinghuan/PycharmProjects/AlphaNex/stock_monitor.py"
        working_dir = os.path.dirname(stock_monitor_path)
        
        logger.info(f"准备启动 stock_monitor.py，路径: {stock_monitor_path}")
        
        # 启动子进程
        stock_monitor_process = subprocess.Popen(
            [sys.executable, stock_monitor_path],
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        logger.info(f"stock_monitor.py 已启动，进程ID: {stock_monitor_process.pid}")
        
    except Exception as e:
        logger.error(f"启动 stock_monitor.py 失败: {str(e)}")


def stop_stock_monitor():
    """
    停止 stock_monitor.py 脚本
    """
    global stock_monitor_process
    try:
        # 检查进程是否存在且正在运行
        if stock_monitor_process is None or stock_monitor_process.poll() is not None:
            logger.info("stock_monitor.py 未在运行")
            return
        
        logger.info(f"准备停止 stock_monitor.py，进程ID: {stock_monitor_process.pid}")
        
        # 发送终止信号
        stock_monitor_process.terminate()
        
        # 等待进程终止，最多等待5秒
        try:
            stock_monitor_process.wait(timeout=5)
            logger.info("stock_monitor.py 已成功停止")
        except subprocess.TimeoutExpired:
            # 如果超时，强制终止
            logger.warning("stock_monitor.py 未在指定时间内终止，强制终止")
            stock_monitor_process.kill()
            logger.info("stock_monitor.py 已强制终止")
        
        # 清理进程对象
        stock_monitor_process = None
        
    except Exception as e:
        logger.error(f"停止 stock_monitor.py 失败: {str(e)}")


def sample_task():
    """
    示例任务，用于测试
    """
    logger.info(f"示例任务执行于: {datetime.now()}")
    print(f"示例任务执行于: {datetime.now()}")

def main():
    """
    主函数
    """
    try:
        logger.info("启动定时任务调度器...")
        
        # 创建调度器
        scheduler = setup_scheduler()
        
        # 注册任务
        register_jobs(scheduler)
        
        # 添加直接在脚本中的示例任务，每5秒执行一次
        scheduler.add_job(
            sample_task,
            'interval',
            seconds=5,
            id='sample_task',
            name='示例任务'
        )
        
        # 添加启动股票监控的定时任务，每天22:30执行
        scheduler.add_job(
            start_stock_monitor,
            'cron',
            hour=22,
            minute=30,
            id='start_stock_monitor',
            name='启动股票监控',
            replace_existing=True
        )
        
        # 添加停止股票监控的定时任务，每天5:00执行
        scheduler.add_job(
            stop_stock_monitor,
            'cron',
            hour=5,
            minute=0,
            id='stop_stock_monitor',
            name='停止股票监控',
            replace_existing=True
        )
        
        logger.info(f"已注册 {len(scheduler.get_jobs())} 个任务")
        logger.info("调度器开始运行...")
        
        # 启动调度器
        scheduler.start()
        
    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭调度器...")
        scheduler.shutdown(wait=True)
        logger.info("调度器已关闭")
    except Exception as e:
        logger.error(f"调度器运行出错: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()