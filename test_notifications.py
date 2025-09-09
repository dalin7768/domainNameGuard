#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试优化后的通知消息
"""

import asyncio
import sys
import os
import io

# 设置标准输出编码为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config_manager import ConfigManager
from telegram_bot import TelegramBot

async def test_notifications():
    """测试通知消息格式"""
    # 初始化配置
    config_manager = ConfigManager()
    bot = TelegramBot(config_manager)
    
    print("测试通知消息格式...")
    print("=" * 50)
    
    # 获取配置信息
    domains = config_manager.get_domains()
    interval = config_manager.get('check.interval_minutes', 30)
    
    notification_config = config_manager.get('notification', {})
    check_config = config_manager.get('check', {})
    daily_report_config = config_manager.get('daily_report', {})
    
    quiet_on_success = notification_config.get('quiet_on_success', False)
    notify_on_all_success = notification_config.get('notify_on_all_success', False)
    notify_on_recovery = notification_config.get('notify_on_recovery', True)
    failure_threshold = notification_config.get('failure_threshold', 2)
    max_concurrent = check_config.get('max_concurrent', 50)
    timeout_seconds = check_config.get('timeout_seconds', 10)
    retry_count = check_config.get('retry_count', 3)
    daily_report_enabled = daily_report_config.get('enabled', False)
    daily_report_time = daily_report_config.get('time', '00:00')
    
    # 测试启动通知
    print("\n1. 服务启动通知:")
    print("-" * 40)
    startup_message = f"""🚀 **域名监控服务已启动**

📊 **监控配置**
├ 监控域名数: {len(domains)} 个
├ 最大循环时间: {interval} 分钟
├ 并发数: {max_concurrent}
├ 超时时间: {timeout_seconds} 秒
└ 重试次数: {retry_count} 次

🔔 **通知设置**
├ 静默模式: {'✅ 开启' if quiet_on_success else '❌ 关闭'}
├ 全部成功通知: {'✅ 开启' if notify_on_all_success else '❌ 关闭'}
├ 恢复通知: {'✅ 开启' if notify_on_recovery else '❌ 关闭'}
├ 失败阈值: {failure_threshold} 次
└ 每日报告: {'✅ ' + daily_report_time if daily_report_enabled else '❌ 关闭'}

💡 使用 /help 查看所有命令
🔍 使用 /check 立即执行检查"""
    
    print(startup_message)
    
    # 测试手动检查通知
    print("\n2. 手动检查开始通知:")
    print("-" * 40)
    
    domain_count = len(domains)
    batches = (domain_count + max_concurrent - 1) // max_concurrent
    estimated_seconds = batches * (timeout_seconds + 2)
    eta_minutes = estimated_seconds // 60
    eta_seconds = estimated_seconds % 60
    
    check_message = f"""🔍 **开始执行域名检查**

📊 **检查信息**
├ 域名总数: {domain_count} 个
├ 并发数: {max_concurrent}
├ 批次数: {batches}
└ 预计耗时: {eta_minutes}分{eta_seconds}秒

⚙️ **通知设置**
├ 静默模式: {'✅ 开启' if quiet_on_success else '❌ 关闭'}
├ 全部成功通知: {'✅ 开启' if notify_on_all_success else '❌ 关闭'}
├ 恢复通知: {'✅ 开启' if notify_on_recovery else '❌ 关闭'}
└ 失败阈值: {failure_threshold} 次

正在检查中，请稍候..."""
    
    print(check_message)
    
    # 发送到 Telegram
    print("\n" + "=" * 50)
    print("正在发送测试消息到 Telegram...")
    
    await bot.send_message("📝 **通知格式测试**\n\n以下是优化后的通知消息格式预览：")
    await asyncio.sleep(1)
    await bot.send_message(startup_message)
    await asyncio.sleep(1)
    await bot.send_message(check_message)
    
    print("测试完成！请检查 Telegram 中的消息格式。")

if __name__ == "__main__":
    asyncio.run(test_notifications())