"""域名监控主程序

该模块是整个监控系统的入口点，负责：
1. 初始化所有组件（检测器、通知器、Bot）
2. 管理定时检查任务
3. 处理 Telegram 命令
4. 协调各模块的工作
"""

import asyncio
import logging
import logging.handlers
import sys
import signal
from pathlib import Path
from datetime import datetime
import time
from typing import Optional

from config_manager import ConfigManager
from domain_checker import DomainChecker, CheckResult, CheckStatus
from telegram_notifier import TelegramNotifier
from telegram_bot import TelegramBot


class DomainMonitor:
    """域名监控主程序
    
    这是整个监控系统的核心类，负责：
    1. 管理所有组件的生命周期
    2. 处理系统信号（如 Ctrl+C）
    3. 协调定时检查和命令处理
    4. 提供启动、停止、重启等控制功能
    """
    
    def __init__(self, config_file: str = "config.json"):
        """
        初始化域名监控器
        
        Args:
            config_file: 配置文件路径，默认为 config.json
        """
        self.config_file = config_file
        self.config_manager = ConfigManager(config_file)  # 配置管理器
        self.checker: Optional[DomainChecker] = None      # 域名检测器
        self.notifier: Optional[TelegramNotifier] = None  # Telegram 通知器
        self.bot: Optional[TelegramBot] = None            # Telegram 命令处理器
        self.logger: Optional[logging.Logger] = None      # 日志记录器
        self.is_running = True                             # 运行状态标志
        
        # 异步任务管理
        self.check_task: Optional[asyncio.Task] = None    # 当前的检查任务
        self.bot_task: Optional[asyncio.Task] = None      # Bot 监听任务
        self.schedule_task: Optional[asyncio.Task] = None # 定时调度任务
        
        # 存储当前运行中的间隔时间（用于比较）
        self.current_interval: Optional[int] = None
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理系统信号（如 Ctrl+C）
        
        当收到 SIGINT 或 SIGTERM 信号时，优雅地停止程序
        
        Args:
            signum: 信号编号
            frame: 当前堆栈帧
        """
        if self.logger:
            self.logger.info(f"收到退出信号 {signum}，正在停止监控...")
        self.is_running = False
        # 创建停止任务，确保异步清理，发送通知因为是从系统信号停止
        asyncio.create_task(self.stop(send_notification=True))
    
    def setup_logging(self) -> None:
        """设置日志系统
        
        配置日志输出到控制台和文件，支持日志轮转
        避免日志文件过大
        """
        # 从配置中读取日志设置
        log_config = self.config_manager.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        log_file = log_config.get('file', 'domain_monitor.log')
        max_size = log_config.get('max_size_mb', 10) * 1024 * 1024  # 转换为字节
        backup_count = log_config.get('backup_count', 5)
        
        # 创建日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 设置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # 重要：清除现有处理器，避免重复输出
        root_logger.handlers.clear()
        
        # 添加控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # 添加文件处理器，支持自动轮转
        # 当文件达到 max_size 时，会自动创建新文件
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count,  # 保留的历史文件数
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("日志系统初始化完成")
    
    def initialize_components(self) -> bool:
        """初始化所有组件
        
        按顺序初始化：
        1. 域名检测器 - 负责检查域名可用性
        2. Telegram 通知器 - 负责发送告警
        3. Telegram Bot - 负责处理命令
        
        Returns:
            bool: 所有组件初始化成功返回 True
        """
        try:
            # 步骤1：初始化域名检测器
            check_config = self.config_manager.get('check', {})
            self.checker = DomainChecker(
                timeout=check_config.get('timeout_seconds', 10),
                retry_count=check_config.get('retry_count', 2),
                retry_delay=check_config.get('retry_delay_seconds', 5),
                max_concurrent=check_config.get('max_concurrent', 10),  # 使用配置的并发数
                auto_adjust=check_config.get('auto_adjust_concurrent', True)  # 自适应并发
            )
            self.logger.info("域名检测器初始化完成")
            
            # 步骤2：初始化 Telegram 通知器
            telegram_config = self.config_manager.get('telegram', {})
            notification_config = self.config_manager.get('notification', {})
            
            self.notifier = TelegramNotifier(
                bot_token=telegram_config.get('bot_token'),
                chat_id=telegram_config.get('chat_id'),
                cooldown_minutes=notification_config.get('cooldown_minutes', 60)
            )
            self.logger.info("Telegram 通知器初始化完成")
            
            # 步骤3：初始化 Telegram Bot 并设置回调
            self.bot = TelegramBot(self.config_manager)
            # 设置命令回调函数，当用户发送命令时会调用这些函数
            self.bot.set_callbacks(
                check=self.run_check,      # /check 命令
                stop=lambda: self.stop(send_notification=False),  # /stop 命令，不重复发送通知
                reload=self.reload_config  # /reload 命令，重新加载配置
            )
            self.logger.info("Telegram Bot 初始化完成")
            
            return True
            
        except Exception as e:
            self.logger.error(f"初始化组件时发生错误：{e}")
            return False
    
    async def run_check(self) -> None:
        """执行一次域名检查
        
        该方法会：
        1. 检查所有配置的域名
        2. 处理检查结果
        3. 发送必要的通知
        
        如果上次检查还未完成，会取消它并开始新的检查
        """
        # 如果上次检查还未完成，取消它
        if self.check_task and not self.check_task.done():
            self.logger.warning("上一次检查还未完成，正在取消...")
            self.check_task.cancel()
            try:
                await self.check_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("=" * 50)
        self.logger.info(f"开始新一轮域名检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 记录检查开始时间
        check_start_time = datetime.now()
        
        try:
            # 重要：每次检查前重新加载配置
            # 这样通过 Telegram 命令修改的配置会立即生效
            domains = self.config_manager.get_domains()
            
            if not domains:
                self.logger.warning("没有配置监控域名")
                return
            
            # 动态更新检查器参数
            check_config = self.config_manager.get('check', {})
            self.checker.timeout = check_config.get('timeout_seconds', 10)
            self.checker.retry_count = check_config.get('retry_count', 2)
            self.checker.retry_delay = check_config.get('retry_delay_seconds', 5)
            self.checker.max_concurrent = check_config.get('max_concurrent', 10)
            batch_notify = check_config.get('batch_notify', False)
            show_eta = check_config.get('show_eta', True)
            
            domain_count = len(domains)
            max_concurrent = self.checker.max_concurrent
            
            # 计算预估时间
            batches = (domain_count + max_concurrent - 1) // max_concurrent
            # 假设每批平均需要10秒（根据超时时间调整）
            estimated_seconds = batches * (self.checker.timeout + 2)
            
            # 发送开始通知，包含预估时间
            if show_eta:
                eta_minutes = estimated_seconds // 60
                eta_seconds = estimated_seconds % 60
                await self.bot.send_message(
                    f"🔍 **开始检查域名**\n\n"
                    f"📊 域名总数: {domain_count} 个\n"
                    f"⚡ 并发数: {max_concurrent}\n"
                    f"📦 批次数: {batches}\n"
                    f"⏱️ 预计耗时: {eta_minutes}分{eta_seconds}秒\n\n"
                    f"正在检查..."
                )
            
            self.logger.info(f"检查 {domain_count} 个域名，并发数 {max_concurrent}，分 {batches} 批")
            
            # 获取通知配置
            notification_config = self.config_manager.get('notification', {})
            
            # 定义批次回调（用于分批通知）
            all_batch_results = []  # 收集所有批次结果
            
            async def batch_callback(batch_results, current_batch, total_batches, eta_seconds):
                """批次完成回调"""
                all_batch_results.extend(batch_results)
                
                # 如果启用分批通知，每批完成后发送结果
                if batch_notify:
                    # 统计批次结果
                    batch_success = sum(1 for r in batch_results if r.is_success)
                    batch_failed = len(batch_results) - batch_success
                    
                    eta_text = ""
                    if eta_seconds > 0:
                        eta_min = int(eta_seconds // 60)
                        eta_sec = int(eta_seconds % 60)
                        eta_text = f"\n⏱️ 剩余时间: {eta_min}分{eta_sec}秒"
                    
                    msg = f"📦 **批次 {current_batch}/{total_batches} 完成**\n\n"
                    msg += f"✅ 成功: {batch_success} 个\n"
                    msg += f"❌ 失败: {batch_failed} 个"
                    msg += eta_text
                    
                    await self.bot.send_message(msg)
                    
                    # 立即发送该批次的告警
                    await self.notifier.notify_failures(
                        batch_results,
                        failure_threshold=notification_config.get('failure_threshold', 2),
                        notify_recovery=notification_config.get('notify_on_recovery', True),
                        notify_all_success=False  # 批次模式不发送全部成功通知
                    )
            
            # 定义进度回调
            async def progress_callback(completed, total, eta_seconds):
                """进度更新回调"""
                # 每完成25%或最少50个发送一次进度
                if completed % max(50, total // 4) == 0 and completed < total:
                    progress_percent = (completed / total) * 100
                    eta_text = ""
                    if eta_seconds > 0:
                        eta_min = int(eta_seconds // 60)
                        eta_sec = int(eta_seconds % 60)
                        eta_text = f" - 剩余: {eta_min}分{eta_sec}秒"
                    
                    msg = f"⏳ 进度: {completed}/{total} ({progress_percent:.1f}%){eta_text}"
                    try:
                        await self.bot.send_message(msg)
                    except Exception as e:
                        self.logger.error(f"发送进度通知失败：{e}")
            
            # 执行批处理检查
            results = await self.checker.check_domains_batch(
                domains,
                batch_callback=batch_callback if batch_notify else None,
                progress_callback=progress_callback if show_eta and domain_count > 50 else None
            )
            
            # 计算实际耗时
            actual_duration = (datetime.now() - check_start_time).total_seconds()
            self.logger.info(f"域名检查完成，实际耗时: {actual_duration:.1f} 秒")
            
            # 动态更新通知器参数
            self.notifier.cooldown_minutes = notification_config.get('cooldown_minutes', 60)
            
            # 如果不是批次通知模式，或需要最终汇总，发送总体通知
            if not batch_notify:
                await self.notifier.notify_failures(
                    results,
                    failure_threshold=notification_config.get('failure_threshold', 2),
                    notify_recovery=notification_config.get('notify_on_recovery', True),
                    notify_all_success=notification_config.get('notify_on_all_success', True)
                )
            else:
                # 批次模式下只发送最终汇总
                await self.notifier._send_check_summary(results, True)
            
            # 输出统计信息
            success_count = sum(1 for r in results if r.is_success)
            failed_count = len(results) - success_count
            
            self.logger.info(f"本轮检查完成 - 成功: {success_count}, 失败: {failed_count}")
            
            # 如果有失败的域名，详细记录
            for result in results:
                if not result.is_success:
                    self.logger.warning(
                        f"域名异常 - {result.domain_name}: "
                        f"{result.status.value} - {result.error_message}"
                    )
            
        except Exception as e:
            self.logger.error(f"执行域名检查时发生错误：{e}", exc_info=True)
    
    async def schedule_checks(self) -> None:
        """定时执行域名检查
        
        使用 interval_minutes 作为最大循环时间：
        - 如果检查在 interval_minutes 内完成，等待剩余时间
        - 如果检查超过 interval_minutes，立即开始下一轮
        """
        while self.is_running:
            try:
                # 记录循环开始时间
                cycle_start = datetime.now()
                
                # 动态获取最大循环时间
                max_cycle_minutes = self.config_manager.get('check.interval_minutes', 30)
                max_cycle_seconds = max_cycle_minutes * 60
                
                self.logger.info(f"开始新的检查循环，最大循环时间: {max_cycle_minutes} 分钟")
                
                # 执行检查
                if self.is_running:
                    self.check_task = asyncio.create_task(self.run_check())
                    # 等待检查完成
                    try:
                        await self.check_task
                    except Exception as e:
                        self.logger.error(f"域名检查出错: {e}")
                
                # 计算已用时间
                elapsed_seconds = (datetime.now() - cycle_start).total_seconds()
                
                # 如果还有剩余时间，等待
                if elapsed_seconds < max_cycle_seconds:
                    wait_seconds = max_cycle_seconds - elapsed_seconds
                    wait_minutes = int(wait_seconds // 60)
                    wait_secs = int(wait_seconds % 60)
                    
                    self.logger.info(f"本轮检查用时 {elapsed_seconds:.1f} 秒，等待 {wait_minutes} 分 {wait_secs} 秒后开始下一轮")
                    
                    # 发送等待通知
                    if self.bot:
                        await self.bot.send_message(
                            f"⏰ 下次检查将在 {wait_minutes} 分 {wait_secs} 秒后开始"
                        )
                    
                    await asyncio.sleep(wait_seconds)
                else:
                    # 检查时间超过了最大循环时间，立即开始下一轮
                    self.logger.warning(f"检查用时 {elapsed_seconds:.1f} 秒，超过最大循环时间 {max_cycle_seconds} 秒，立即开始下一轮")
                    
                    if self.bot:
                        await self.bot.send_message(
                            f"⚠️ 检查耗时超过设定的 {max_cycle_minutes} 分钟，立即开始下一轮检查"
                        )
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"定时检查时发生错误：{e}")
                await asyncio.sleep(60)  # 出错后等待1分钟再继续
    
    async def test_setup(self) -> bool:
        """
        测试配置是否正确
        
        Returns:
            bool: 测试是否通过
        """
        self.logger.info("开始测试配置...")
        
        # 测试 Telegram 连接
        self.logger.info("测试 Telegram Bot 连接...")
        telegram_ok = await self.notifier.test_connection()
        if not telegram_ok:
            self.logger.error("Telegram Bot 连接测试失败，请检查 Bot Token 和 Chat ID")
            return False
        
        # 测试域名检查（只检查前3个）
        domains = self.config_manager.get_domains()
        if domains:
            self.logger.info("测试域名检查功能...")
            test_domains = domains[:min(3, len(domains))]
            test_results = await self.checker.check_domains(test_domains)
            
            for result in test_results:
                if result.is_success:
                    self.logger.info(f"✓ {result.domain_name} - 正常")
                else:
                    self.logger.warning(f"✗ {result.domain_name} - {result.status.value}")
        
        self.logger.info("配置测试完成")
        return True
    
    async def stop(self, send_notification: bool = True) -> None:
        """停止监控服务
        
        优雅地停止所有运行中的任务：
        1. 设置停止标志
        2. 发送停止通知（在取消任务之前）
        3. 取消所有异步任务
        4. 等待任务结束
        
        Args:
            send_notification: 是否发送停止通知，默认为True
                              当从telegram命令停止时应设为False避免重复
        """
        self.logger.info("正在停止监控服务...")
        self.is_running = False  # 设置停止标志
        
        # 先发送停止通知（在取消任务之前，确保消息能发送出去）
        if send_notification and self.bot:
            try:
                await self.bot.send_message("⏹️ 监控服务已停止")
            except Exception as e:
                self.logger.error(f"发送停止通知失败: {e}")
        
        # 收集所有需要取消的任务
        tasks = []
        if self.check_task and not self.check_task.done():
            self.check_task.cancel()
            tasks.append(self.check_task)
        
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            tasks.append(self.bot_task)
        
        if self.schedule_task and not self.schedule_task.done():
            self.schedule_task.cancel()
            tasks.append(self.schedule_task)
        
        # 等待所有任务完成
        # return_exceptions=True 确保即使任务抛出异常也不会中断
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.logger.info("监控服务已停止")
    
    async def reload_config(self) -> None:
        """重新加载配置
        
        重新加载配置文件并重启定时任务
        让间隔时间等配置立即生效
        """
        self.logger.info("正在重新加载配置...")
        
        # 使用内存中存储的当前间隔时间（而不是从配置文件读取）
        old_interval = self.current_interval if self.current_interval is not None else self.config_manager.get('check.interval_minutes', 30)
        
        # 重新加载配置文件
        self.config_manager.load_config()
        
        # 获取新的间隔时间
        new_interval = self.config_manager.get('check.interval_minutes', 30)
        
        # 更新内存中的当前间隔时间
        self.current_interval = new_interval
        
        # 更新关键配置
        telegram_config = self.config_manager.get('telegram', {})
        self.bot.bot_token = telegram_config.get('bot_token')
        self.bot.chat_id = telegram_config.get('chat_id')
        self.bot.api_base_url = f"https://api.telegram.org/bot{self.bot.bot_token}"
        
        # 如果间隔时间改变了，重启定时检查任务
        if old_interval != new_interval:
            self.logger.info(f"检查间隔从 {old_interval} 分钟更改为 {new_interval} 分钟，重启定时任务...")
            
            # 取消当前的定时任务
            if self.schedule_task and not self.schedule_task.done():
                self.schedule_task.cancel()
                try:
                    await self.schedule_task
                except asyncio.CancelledError:
                    pass
            
            # 重新启动定时任务，不立即执行检查
            self.schedule_task = asyncio.create_task(self.schedule_checks())
            
            await self.bot.send_message(
                f"🔄 **配置已重新加载**\n\n"
                f"⏰ 检查间隔已更新：{old_interval} → {new_interval} 分钟\n"
                f"✅ 新的间隔时间已生效\n"
                f"⏱️ 下次检查将在 {new_interval} 分钟后执行"
            )
        else:
            await self.bot.send_message(
                "🔄 **配置已重新加载**\n\n"
                "✅ 配置更新成功\n"
                "💡 检查间隔未改变"
            )
        
        self.logger.info("配置重新加载完成")
    
    async def run(self) -> None:
        """运行主程序
        
        完整的启动流程：
        1. 设置日志系统
        2. 检查必要配置
        3. 初始化组件
        4. 测试配置
        5. 启动所有任务
        6. 等待任务完成或退出信号
        """
        print("\n" + "=" * 60)
        print("域名监控服务 v2.0 - 支持 Telegram 命令控制")
        print("=" * 60 + "\n")
        
        # 设置日志
        self.setup_logging()
        
        # 检查必要配置（Bot Token 和 Chat ID）
        bot_token = self.config_manager.get('telegram.bot_token')
        chat_id = self.config_manager.get('telegram.chat_id')
        
        if not bot_token or not chat_id:
            self.logger.error("请先配置 Telegram Bot Token 和 Chat ID")
            print("\n请编辑 config.json 文件，配置以下信息：")
            print("1. telegram.bot_token - Telegram Bot Token")
            print("2. telegram.chat_id - 群组 ID")
            print("\n参考 CONFIG_README.md 文件获取详细说明")
            return
        
        # 初始化组件
        if not self.initialize_components():
            self.logger.error("组件初始化失败，程序退出")
            return
        
        # 测试配置
        if not await self.test_setup():
            self.logger.error("配置测试失败，请检查配置后重试")
            return
        
        # 启动 Bot 监听
        self.bot_task = asyncio.create_task(self.bot.listen_for_commands())
        self.logger.info("Telegram Bot 命令监听已启动")
        
        # 发送启动通知
        domains = self.config_manager.get_domains()
        interval = self.config_manager.get('check.interval_minutes', 30)
        self.current_interval = interval  # 初始化当前间隔时间
        
        await self.bot.send_message(
            f"🚀 **域名监控服务已启动**\n\n"
            f"🌐 监控域名数: {len(domains)} 个\n"
            f"⏰ 最大循环时间: {interval} 分钟\n\n"
            f"使用 /help 查看所有命令"
        )
        
        # 启动定时检查任务（包含首次检查）
        self.logger.info(f"定时检查已启动，最大循环时间 {interval} 分钟")
        self.schedule_task = asyncio.create_task(self.schedule_checks())
        
        print("\n监控服务正在运行中...")
        print("可以在 Telegram 群组中使用 /help 查看所有命令")
        print("按 Ctrl+C 停止服务\n")
        
        try:
            # 等待所有后台任务
            # Bot 任务和调度任务会一直运行直到收到停止信号
            await asyncio.gather(
                self.bot_task,
                self.schedule_task,
                return_exceptions=True
            )
        except KeyboardInterrupt:
            self.logger.info("收到停止信号")
        finally:
            # 只有在程序还在运行时才调用停止（避免重复调用）
            if self.is_running:
                await self.stop()
            print("\n监控服务已停止")


def main():
    """主函数入口
    
    程序的入口点，创建监控器实例并运行
    处理退出信号和异常
    """
    # 创建监控器实例
    monitor = DomainMonitor()
    
    try:
        # 使用 asyncio.run 运行异步主程序
        # 这个函数会创建事件循环并运行直到完成
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        # 处理 Ctrl+C
        print("\n程序已退出")
    except Exception as e:
        # 处理其他未捕获的异常
        print(f"程序运行出错：{e}")
        sys.exit(1)  # 退出码 1 表示异常退出


if __name__ == "__main__":
    main()