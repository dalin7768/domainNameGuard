#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试手动 check 指令是否正确发送通知
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config_manager import ConfigManager
from telegram_notifier import TelegramNotifier
from domain_checker import DomainChecker, CheckResult, CheckStatus
from datetime import datetime

async def test_manual_check():
    """测试手动检查通知"""
    # 初始化配置
    config_manager = ConfigManager()
    bot_token = config_manager.get('telegram.bot_token')
    chat_id = config_manager.get('telegram.chat_id')
    notifier = TelegramNotifier(bot_token, chat_id)
    
    # 创建模拟的检查结果
    print("创建模拟检查结果...")
    
    # 测试场景1：所有域名都正常
    results_all_success = [
        CheckResult(
            domain_name="example.com",
            url="https://example.com",
            status=CheckStatus.SUCCESS,
            status_code=200,
            response_time=0.5,
            timestamp=datetime.now()
        ),
        CheckResult(
            domain_name="google.com",
            url="https://google.com",
            status=CheckStatus.SUCCESS,
            status_code=200,
            response_time=0.3,
            timestamp=datetime.now()
        )
    ]
    
    # 测试场景2：有域名异常
    results_with_failure = [
        CheckResult(
            domain_name="example.com",
            url="https://example.com",
            status=CheckStatus.SUCCESS,
            status_code=200,
            response_time=0.5,
            timestamp=datetime.now()
        ),
        CheckResult(
            domain_name="failed-domain.com",
            url="https://failed-domain.com",
            status=CheckStatus.CONNECTION_ERROR,
            error_message="连接失败",
            timestamp=datetime.now()
        )
    ]
    
    print("\n测试场景1：手动检查 - 所有域名正常")
    print("=" * 50)
    print("is_manual=True, 应该发送通知")
    await notifier.notify_failures(
        results_all_success,
        failure_threshold=1,
        notify_recovery=True,
        notify_all_success=False,  # 配置中的值
        quiet_on_success=False,     # 配置中的值
        is_manual=True              # 手动检查
    )
    
    await asyncio.sleep(2)
    
    print("\n测试场景2：定时检查 - 所有域名正常")
    print("=" * 50)
    print("is_manual=False, notify_all_success=False")
    print("按配置不应该发送通知")
    await notifier.notify_failures(
        results_all_success,
        failure_threshold=1,
        notify_recovery=True,
        notify_all_success=False,  # 配置中的值
        quiet_on_success=False,     # 配置中的值
        is_manual=False             # 定时检查
    )
    
    await asyncio.sleep(2)
    
    print("\n测试场景3：手动检查 - 有域名异常")
    print("=" * 50)
    print("is_manual=True, 应该发送通知")
    await notifier.notify_failures(
        results_with_failure,
        failure_threshold=1,
        notify_recovery=True,
        notify_all_success=False,
        quiet_on_success=False,
        is_manual=True              # 手动检查
    )
    
    print("\n测试完成！请检查 Telegram 是否收到了预期的通知。")
    print("预期结果：")
    print("- 场景1（手动检查，全部正常）：应该收到通知")
    print("- 场景2（定时检查，全部正常）：不应该收到通知")
    print("- 场景3（手动检查，有异常）：应该收到通知")

if __name__ == "__main__":
    asyncio.run(test_manual_check())