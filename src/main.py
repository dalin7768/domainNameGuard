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
from datetime import datetime, timedelta
import time
from typing import Optional, List

from config_manager import ConfigManager
from domain_checker import DomainChecker, CheckResult, CheckStatus
from telegram_notifier import TelegramNotifier
from telegram_bot import TelegramBot
from error_tracker import ErrorTracker
from http_server import HttpApiServer


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
        self.error_tracker: Optional[ErrorTracker] = None # 错误状态跟踪器
        self.http_server: Optional[HttpApiServer] = None  # HTTP API服务器
        self.is_running = True                             # 运行状态标志
        
        # 异步任务管理
        self.check_task: Optional[asyncio.Task] = None    # 当前的检查任务
        self.bot_task: Optional[asyncio.Task] = None      # Bot 监听任务
        self.schedule_task: Optional[asyncio.Task] = None # 定时调度任务
        self.http_task: Optional[asyncio.Task] = None     # HTTP服务器任务
        
        # 存储当前运行中的间隔时间（用于比较）
        self.current_interval: Optional[int] = None
        
        # 统计信息跟踪
        self.last_check_time: Optional[datetime] = None    # 上次检查时间
        self.next_check_time: Optional[datetime] = None    # 下次检查时间
        self.last_check_results = {                        # 上次检查结果统计
            "total": 0,
            "success": 0,
            "failed": 0,
            "error_types": {}  # 错误类型统计
        }
        self.service_start_time: datetime = datetime.now() # 服务启动时间
        self.total_checks_count: int = 0                   # 总检查次数
        
        # 每日统计数据
        self.daily_stats = {
            "date": datetime.now().date(),
            "total_checks": 0,
            "total_domains_checked": 0,
            "total_success": 0,
            "total_failed": 0,
            "error_summary": {},  # 错误类型汇总
            "availability_by_domain": {}  # 每个域名的可用性统计
        }
        self.daily_report_task: Optional[asyncio.Task] = None  # 每日报告任务
        
        # 设置信号处理（在Windows上优化）
        if sys.platform != "win32":
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理系统信号（如 Ctrl+C）
        
        当收到 SIGINT 或 SIGTERM 信号时，优雅地停止程序
        信号处理器只设置标志，让主循环检测到并执行异步停止
        
        Args:
            signum: 信号编号
            frame: 当前堆栈帧
        """
        if self.logger:
            self.logger.info(f"收到退出信号 {signum}，正在停止监控...")
        self.is_running = False
    
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
                chat_id=telegram_config.get('chat_id')
            )
            self.logger.info("Telegram 通知器初始化完成")
            
            # 步骤3：初始化错误跟踪器
            history_config = self.config_manager.get('history', {})
            if history_config.get('enabled', True):
                self.error_tracker = ErrorTracker(
                    history_file="error_history.json",
                    retention_days=history_config.get('retention_days', 30)
                )
                self.logger.info("错误跟踪器初始化完成")
            
            # 步骤4：初始化 Telegram Bot 并设置回调
            self.bot = TelegramBot(self.config_manager)
            # 设置命令回调函数，当用户发送命令时会调用这些函数
            self.bot.set_callbacks(
                check=self.run_check,      # /check 命令
                stop=lambda **kwargs: self.stop(**kwargs),  # /stop 命令，支持 force 参数
                stop_check=self.stop_check,  # /stopcheck 命令，停止当前检查
                restart=self.restart_service,  # /restart 命令，重启服务
                reload=self.reload_config,  # /reload 命令，重新加载配置
                get_status=self.get_status_info,  # /status 命令，获取详细状态
                send_daily_report=self.send_daily_report,  # /dailyreport now 命令，发送每日报告
                error_tracker=self.get_error_tracker  # 获取错误跟踪器
            )
            self.logger.info("Telegram Bot 初始化完成")
            
            # 步骤5：初始化 HTTP API 服务器
            self.http_server = HttpApiServer(self.config_manager, self.bot)
            self.logger.info("HTTP API 服务器初始化完成")
            
            return True
            
        except Exception as e:
            self.logger.error(f"初始化组件时发生错误：{e}")
            return False
    
    async def run_check(self, is_manual: bool = False) -> None:
        """执行一次域名检查
        
        该方法会：
        1. 检查所有配置的域名
        2. 处理检查结果
        3. 发送必要的通知
        
        Args:
            is_manual: 是否为手动触发的检查（默认False为定时检查）
        
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
        self.last_check_time = check_start_time
        self.total_checks_count += 1
        
        try:
            # 重要：每次检查前重新加载配置
            # 获取所有群组的域名进行合并监控
            all_domains = []
            groups_domains_map = {}  # 存储每个群组对应的域名

            if hasattr(self.bot, 'groups_config') and self.bot.groups_config:
                # 多群组模式：合并所有群组的域名
                for chat_id, group_config in self.bot.groups_config.items():
                    group_domains = group_config.get('domains', [])
                    groups_domains_map[chat_id] = group_domains
                    all_domains.extend(group_domains)
            else:
                # 兼容旧版单群组模式
                all_domains = self.config_manager.get_domains()
                # 为兼容性创建映射
                if all_domains:
                    chat_id = next(iter(self.bot.groups_config.keys())) if self.bot.groups_config else None
                    if chat_id:
                        groups_domains_map[chat_id] = all_domains

            domains = all_domains
            
            # 添加详细日志
            self.logger.info(f"从配置获取到 {len(domains)} 个域名")
            
            if not domains:
                self.logger.warning("没有配置监控域名")
                return
            
            # 去除重复域名并记录
            unique_domains = list(dict.fromkeys(domains))  # 保持顺序的去重
            if len(unique_domains) != len(domains):
                self.logger.warning(f"发现重复域名，原始数量: {len(domains)}，去重后: {len(unique_domains)}")
                domains = unique_domains
            
            # 再次记录最终域名数量
            self.logger.info(f"准备检查 {len(domains)} 个域名（去重后）")
            
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
            
            # 仅在手动检查时发送开始通知
            if is_manual and show_eta:
                eta_minutes = estimated_seconds // 60
                eta_seconds = estimated_seconds % 60
                
                # 获取通知配置信息
                notification_config = self.config_manager.get('notification', {})
                notify_level = notification_config.get('level', 'smart')
                failure_threshold = notification_config.get('failure_threshold', 2)
                
                level_desc = {
                    'all': '始终通知',
                    'error': '仅错误时',
                    'smart': '智能模式'
                }
                
                await self.bot.send_message(
                    f"🔍 **域名检查启动**\n\n"
                    f"📊 **检查配置**\n"
                    f"├ 域名总数: {domain_count} 个\n"
                    f"├ 并发线程: {max_concurrent}\n"
                    f"├ 分批执行: {batches} 批\n"
                    f"└ 预计用时: {eta_minutes}分{eta_seconds}秒\n\n"
                    f"🔔 **通知模式**\n"
                    f"└ 当前级别: {level_desc.get(notify_level, notify_level)}"
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
                    )
            
            # 定义进度回调 - 根据用户要求，进一步限制进度消息
            async def progress_callback(completed, total, eta_seconds):
                """进度更新回调"""
                # 用户要求禁用不必要的进度消息，只在域名数量非常多时才显示
                # 条件：域名数量>500，且每完成50%才发送一次
                if total > 500 and completed % (total // 2) == 0 and completed < total:
                    progress_percent = (completed / total) * 100
                    eta_text = ""
                    if eta_seconds > 0:
                        eta_min = int(eta_seconds // 60)
                        eta_sec = int(eta_seconds % 60)
                        eta_text = f" - 剩余: {eta_min}分{eta_sec}秒"
                    
                    msg = f"⏳ 进度: {completed}/{total} ({progress_percent:.1f}%){eta_text}"
                    # 使用异步非阻塞方式发送进度消息
                    try:
                        # 创建任务并保持引用，避免被垃圾回收
                        task = asyncio.create_task(self._send_progress_message(msg))
                        # 添加完成回调来处理异常，避免任务异常被忽略
                        def handle_task_done(task):
                            try:
                                task.result()  # 获取结果，如果有异常会抛出
                            except Exception as e:
                                self.logger.debug(f"发送进度消息失败: {e}")
                        task.add_done_callback(handle_task_done)
                    except Exception as e:
                        self.logger.debug(f"创建进度通知任务失败：{e}")
            
            # 执行批处理检查 - 根据用户要求完全禁用进度回调
            results = await self.checker.check_domains_batch(
                domains,
                batch_callback=batch_callback if batch_notify else None,
                progress_callback=None  # 禁用进度消息避免卡住问题
            )
            
            # 计算实际耗时
            actual_duration = (datetime.now() - check_start_time).total_seconds()
            self.logger.info(f"域名检查完成，实际耗时: {actual_duration:.1f} 秒")
            
            
            # 计算下次执行时间
            max_cycle_minutes = self.config_manager.get('check.interval_minutes', 30)
            max_cycle_seconds = max_cycle_minutes * 60
            elapsed = (datetime.now() - check_start_time).total_seconds()
            
            # 计算下次执行的具体时间
            if elapsed < max_cycle_seconds:
                wait_seconds = max_cycle_seconds - elapsed
                next_run_time = datetime.now() + timedelta(seconds=wait_seconds)
            else:
                next_run_time = datetime.now()  # 立即执行
            
            self.next_check_time = next_run_time
            
            # 更新错误跟踪器
            new_errors = []
            recovered = []
            persistent_errors = []
            
            if self.error_tracker:
                new_errors, recovered, persistent_errors = await self.error_tracker.update_status(results)
            
            # 根据通知级别决定是否发送通知
            notify_level = notification_config.get('level', 'smart')
            
            # 统计结果用于调试
            success_count = sum(1 for r in results if r.is_success)
            failed_count = len(results) - success_count
            self.logger.info(f"检查结果统计 - 总数: {len(results)}, 成功: {success_count}, 失败: {failed_count}")
            self.logger.info(f"通知级别: {notify_level}, 手动检查: {is_manual}")
            
            # 如果是手动检查，始终通知
            if is_manual:
                should_notify = True
                results_to_notify = results
                self.logger.info("手动检查 - 将发送通知")
            # 根据通知级别决定
            elif notify_level == 'all':
                # 始终通知
                should_notify = True
                results_to_notify = results
                self.logger.info("all模式 - 将发送通知")
            elif notify_level == 'error':
                # 仅在有错误时通知
                failed_results = [r for r in results if not r.is_success]
                should_notify = len(failed_results) > 0
                results_to_notify = results
            elif notify_level == 'smart':
                # 智能通知：只通知变化
                should_notify = len(new_errors) > 0 or len(recovered) > 0
                # 只通知新增错误和恢复的
                results_to_notify = new_errors + recovered
                # 如果有持续错误但未确认，也要提醒
                if self.error_tracker:
                    unack_count = len(self.error_tracker.get_unacknowledged_errors())
                    if unack_count > 0:
                        # 添加未处理错误提醒
                        results_to_notify = results
            else:
                # 默认为智能通知
                should_notify = len(new_errors) > 0 or len(recovered) > 0
                results_to_notify = new_errors + recovered
            
            # 多群组通知：为每个群组发送相关的检查结果
            if groups_domains_map:
                for chat_id, group_domains in groups_domains_map.items():
                    if not group_domains:  # 跳过没有域名的群组
                        continue

                    # 筛选出这个群组相关的检查结果
                    group_results = [r for r in results if r.domain_name in group_domains]
                    if not group_results:
                        continue

                    # 筛选出这个群组的新错误和恢复
                    group_new_errors = [e for e in new_errors if e.domain_name in group_domains] if new_errors else []
                    group_recovered = [r for r in recovered if r.domain_name in group_domains] if recovered else []
                    group_persistent_errors = [e for e in persistent_errors if e.domain_name in group_domains] if persistent_errors else []

                    # 判断是否需要向这个群组发送通知
                    if is_manual:
                        group_should_notify = True
                        group_results_to_notify = group_results
                    elif notify_level == 'all':
                        group_should_notify = True
                        group_results_to_notify = group_results
                    elif notify_level == 'error':
                        group_failed_results = [r for r in group_results if not r.is_success]
                        group_should_notify = len(group_failed_results) > 0
                        group_results_to_notify = group_results
                    elif notify_level == 'smart':
                        group_should_notify = len(group_new_errors) > 0 or len(group_recovered) > 0
                        group_results_to_notify = group_new_errors + group_recovered
                    else:
                        group_should_notify = len(group_new_errors) > 0 or len(group_recovered) > 0
                        group_results_to_notify = group_new_errors + group_recovered

                    # 发送群组通知
                    if group_should_notify:
                        quiet_on_success_setting = notify_level == 'error'

                        # 创建群组特定的通知器实例
                        group_notifier = TelegramNotifier(
                            bot_token=self.notifier.bot_token,
                            chat_id=chat_id
                        )

                        await group_notifier.notify_failures(
                            group_results_to_notify if notify_level == 'smart' and not is_manual else group_results,
                            quiet_on_success=quiet_on_success_setting,
                            is_manual=is_manual,
                            next_run_time=next_run_time,
                            new_errors=group_new_errors if notify_level == 'smart' else None,
                            recovered=group_recovered if notify_level == 'smart' else None,
                            persistent_errors=group_persistent_errors if notify_level == 'smart' else None
                        )

                        self.logger.info(f"已向群组 {chat_id} 发送通知")

            else:
                # 兼容旧版单群组逻辑
                self.logger.info(f"通知判断 - batch_notify: {batch_notify}, should_notify: {should_notify}")
                if not batch_notify and should_notify:
                    quiet_on_success_setting = notify_level == 'error'
                    self.logger.info(f"准备发送通知 - 级别: {notify_level}, 手动: {is_manual}, quiet_on_success: {quiet_on_success_setting}")

                    await self.notifier.notify_failures(
                        results_to_notify if notify_level == 'smart' and not is_manual else results,
                        quiet_on_success=quiet_on_success_setting,
                        is_manual=is_manual,
                        next_run_time=next_run_time,
                        new_errors=new_errors if notify_level == 'smart' else None,
                        recovered=recovered if notify_level == 'smart' else None,
                        persistent_errors=persistent_errors if notify_level == 'smart' else None
                    )
                    self.logger.info("通知已发送")
            
            # 输出统计信息
            success_count = sum(1 for r in results if r.is_success)
            failed_count = len(results) - success_count
            
            # 更新统计信息
            self.last_check_results["total"] = len(results)
            self.last_check_results["success"] = success_count
            self.last_check_results["failed"] = failed_count
            
            # 统计错误类型
            error_types = {}
            for result in results:
                if not result.is_success:
                    error_type = result.status.value
                    error_types[error_type] = error_types.get(error_type, 0) + 1
            self.last_check_results["error_types"] = error_types
            
            # 更新每日统计
            self._update_daily_stats(results)
            
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
                    # 所有检查都按定时检查逻辑处理
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
                    
                    # 不再单独发送等待通知（已合并到检查完成消息中）
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
    
    async def stop(self, send_notification: bool = True, force: bool = False) -> None:
        """停止监控服务
        
        优雅地停止所有运行中的任务：
        1. 设置停止标志
        2. 发送停止通知（在取消任务之前）
        3. 取消所有异步任务
        4. 等待任务结束（除非强制停止）
        
        Args:
            send_notification: 是否发送停止通知，默认为True
                              当从telegram命令停止时应设为False避免重复
            force: 是否强制停止（不等待任务完成）
        """
        self.logger.info(f"正在{'强制' if force else ''}停止监控服务...")
        self.is_running = False  # 设置停止标志
        
        # 先发送停止通知（在取消任务之前，确保消息能发送出去）
        if send_notification and self.bot:
            try:
                await self.bot.send_message("🛑 监控服务已停止")
            except Exception as e:
                self.logger.error(f"发送停止通知失败: {e}")
        
        # 如果是强制停止，立即取消所有任务并退出
        if force:
            # 立即取消所有任务
            if self.check_task and not self.check_task.done():
                self.check_task.cancel()
            if self.bot_task and not self.bot_task.done():
                self.bot_task.cancel()
            if self.schedule_task and not self.schedule_task.done():
                self.schedule_task.cancel()
            if self.daily_report_task and not self.daily_report_task.done():
                self.daily_report_task.cancel()
            # 停止HTTP服务器
            if self.http_server:
                try:
                    await self.http_server.stop_server()
                except Exception as e:
                    self.logger.error(f"停止HTTP服务器失败: {e}")
            self.logger.info("强制停止：已取消所有任务")
            return
        
        # 正常停止：收集所有需要取消的任务
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
        
        if self.daily_report_task and not self.daily_report_task.done():
            self.daily_report_task.cancel()
            tasks.append(self.daily_report_task)
        
        # 停止HTTP服务器
        if self.http_server:
            try:
                await self.http_server.stop_server()
                self.logger.info("HTTP API 服务器已停止")
            except Exception as e:
                self.logger.error(f"停止HTTP服务器失败: {e}")

        
        # 等待所有任务完成（带超时，更快响应）
        # return_exceptions=True 确保即使任务抛出异常也不会中断
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 
                    timeout=2.0  # 2秒超时，更快响应
                )
            except asyncio.TimeoutError:
                self.logger.warning("等待任务停止超时，强制退出")
        
        self.logger.info("监控服务已停止")
    
    async def get_status_info(self) -> dict:
        """获取服务状态信息
        
        Returns:
            dict: 包含各种状态信息的字典
        """
        return {
            'service_start_time': self.service_start_time,
            'last_check_time': self.last_check_time,
            'next_check_time': self.next_check_time,
            'last_check_results': self.last_check_results,
            'total_checks_count': self.total_checks_count,
            'is_running': self.is_running
        }
    
    async def stop_check(self):
        """停止当前正在进行的检查任务"""
        if self.check_task and not self.check_task.done():
            self.logger.info("正在停止当前的域名检查任务...")
            self.check_task.cancel()
            try:
                await self.check_task
            except asyncio.CancelledError:
                self.logger.info("域名检查任务已停止")
            except Exception as e:
                self.logger.error(f"停止检查任务时出错: {e}")
        else:
            self.logger.info("当前没有正在运行的检查任务")

    async def get_error_tracker(self):
        """获取错误跟踪器
        
        Returns:
            ErrorTracker: 错误跟踪器实例
        """
        return self.error_tracker
    
    def _update_daily_stats(self, results: List[CheckResult]) -> None:
        """更新每日统计数据
        
        Args:
            results: 检查结果列表
        """
        # 检查是否需要重置每日统计（新的一天）
        current_date = datetime.now().date()
        if self.daily_stats["date"] != current_date:
            # 新的一天，重置统计
            self.daily_stats = {
                "date": current_date,
                "total_checks": 0,
                "total_domains_checked": 0,
                "total_success": 0,
                "total_failed": 0,
                "error_summary": {},
                "availability_by_domain": {}
            }
        
        # 更新统计
        self.daily_stats["total_checks"] += 1
        self.daily_stats["total_domains_checked"] += len(results)
        
        for result in results:
            domain = result.domain_name
            
            # 更新可用性统计
            if domain not in self.daily_stats["availability_by_domain"]:
                self.daily_stats["availability_by_domain"][domain] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0
                }
            
            self.daily_stats["availability_by_domain"][domain]["total"] += 1
            
            if result.is_success:
                self.daily_stats["total_success"] += 1
                self.daily_stats["availability_by_domain"][domain]["success"] += 1
            else:
                self.daily_stats["total_failed"] += 1
                self.daily_stats["availability_by_domain"][domain]["failed"] += 1
                
                # 更新错误类型统计
                error_type = result.status.value
                self.daily_stats["error_summary"][error_type] = \
                    self.daily_stats["error_summary"].get(error_type, 0) + 1
    
    async def _send_progress_message(self, message: str) -> None:
        """发送进度消息（非阻塞方式）"""
        try:
            if self.bot:
                await self.bot.send_message(message)
        except Exception as e:
            self.logger.debug(f"发送进度消息失败: {e}")

    async def send_daily_report(self) -> None:
        """发送每日统计报告"""
        if not self.bot:
            return
        
        stats = self.daily_stats
        
        # 计算总体可用率
        total_checked = stats["total_success"] + stats["total_failed"]
        if total_checked == 0:
            overall_availability = 100.0
        else:
            overall_availability = (stats["total_success"] / total_checked) * 100
        
        # 构建报告消息
        message = f"📊 **每日统计报告**\n"
        message += f"📅 日期: {stats['date']}\n\n"
        
        message += f"**📈 总体统计**\n"
        message += f"├ 检查轮次: {stats['total_checks']} 次\n"
        message += f"├ 检查域名数: {stats['total_domains_checked']} 个次\n"
        message += f"├ 成功: {stats['total_success']} 次\n"
        message += f"├ 失败: {stats['total_failed']} 次\n"
        message += f"└ 总体可用率: {overall_availability:.2f}%\n\n"
        
        # 错误类型统计
        if stats["error_summary"]:
            message += f"**❌ 错误类型分布**\n"
            sorted_errors = sorted(stats["error_summary"].items(), 
                                 key=lambda x: x[1], reverse=True)
            for i, (error_type, count) in enumerate(sorted_errors):
                is_last = i == len(sorted_errors) - 1
                prefix = "└" if is_last else "├"
                display_name = error_type.replace('_', ' ').title()
                message += f"{prefix} {display_name}: {count} 次\n"
            message += "\n"
        
        # 按域名的可用率统计（只显示有问题的域名）
        problem_domains = []
        for domain, stats_item in stats["availability_by_domain"].items():
            if stats_item["failed"] > 0:
                availability = (stats_item["success"] / stats_item["total"]) * 100
                problem_domains.append((domain, availability, stats_item))
        
        if problem_domains:
            # 按可用率排序（从低到高）
            problem_domains.sort(key=lambda x: x[1])
            
            message += f"**⚠️ 需要关注的域名** (可用率低于100%)\n"
            for i, (domain, availability, domain_stats) in enumerate(problem_domains):  # 显示所有有问题的域名
                is_last = i == len(problem_domains) - 1
                prefix = "└" if is_last else "├"
                message += f"{prefix} {domain}: {availability:.1f}% "
                message += f"(成功{domain_stats['success']}/{domain_stats['total']})\n"
            
            # 显示所有有问题的域名，不省略
        else:
            message += "**✅ 所有域名今日运行良好！**\n"
        
        # 发送报告
        try:
            await self.bot.send_message(message)
            self.logger.info("每日统计报告已发送")
        except Exception as e:
            self.logger.error(f"发送每日报告失败: {e}")
    
    async def schedule_daily_report(self) -> None:
        """定时发送每日报告的任务"""
        while self.is_running:
            try:
                # 获取配置
                daily_config = self.config_manager.get('daily_report', {})
                enabled = daily_config.get('enabled', False)
                report_time_str = daily_config.get('time', '00:00')
                
                if not enabled:
                    # 如果未启用，等待1小时后再检查
                    await asyncio.sleep(3600)
                    continue
                
                # 解析报告时间
                try:
                    hour, minute = map(int, report_time_str.split(':'))
                except:
                    self.logger.error(f"无效的报告时间格式: {report_time_str}")
                    hour, minute = 0, 0
                
                # 计算下次报告时间
                now = datetime.now()
                next_report = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # 如果今天的报告时间已过，设置为明天
                if next_report <= now:
                    next_report += timedelta(days=1)
                
                # 等待到报告时间
                wait_seconds = (next_report - now).total_seconds()
                self.logger.info(f"下次每日报告时间: {next_report}, 等待 {wait_seconds/3600:.1f} 小时")
                
                await asyncio.sleep(wait_seconds)
                
                # 发送报告
                if self.is_running:
                    await self.send_daily_report()
                    
                    # 发送后重置统计数据
                    self.daily_stats = {
                        "date": datetime.now().date(),
                        "total_checks": 0,
                        "total_domains_checked": 0,
                        "total_success": 0,
                        "total_failed": 0,
                        "error_summary": {},
                        "availability_by_domain": {}
                    }
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"每日报告任务出错: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时
    
    async def restart_service(self) -> None:
        """重启监控服务
        
        检测运行环境并选择适当的重启方式
        """
        self.logger.info("收到重启命令，准备重启服务...")
        
        # 检测是否运行在systemd下
        is_systemd = self._is_running_under_systemd()
        
        # 发送重启通知
        if self.bot:
            try:
                import platform
                if is_systemd:
                    # systemd 会自动重启，不需要提示
                    pass
                elif platform.system() == 'Windows':
                    await self.bot.send_message(
                        "🔄 **Windows重启**\n\n"
                        "正在创建重启脚本并重新启动程序...\n"
                        "如果重启失败，请手动运行：\n"
                        "`python src/main.py`"
                    )
                else:
                    await self.bot.send_message(
                        "⚠️ **重启请求**\n\n"
                        "检测到程序未通过systemd运行。\n"
                        "程序将停止，请手动重启：\n"
                        "`python src/main.py`\n\n"
                        "💡 建议使用 `./deploy.sh` 部署为系统服务"
                    )
            except Exception as e:
                self.logger.error(f"发送重启通知失败: {e}")
        
        # 停止所有任务
        await self.stop(send_notification=False, force=True)
        
        if is_systemd:
            # 在systemd环境下，使用退出码3触发重启
            import os
            self.logger.info("程序即将退出并由systemd重启...")
            os._exit(3)
        else:
            # 非systemd环境，尝试使用操作系统特定的重启方式
            import platform
            import os
            import sys
            
            if platform.system() == 'Windows':
                # Windows环境：创建重启脚本
                restart_script = """@echo off
timeout /t 2 /nobreak > nul
cd /d "%~dp0"
python src/main.py
pause"""
                try:
                    # 写入重启脚本
                    with open('restart.bat', 'w', encoding='utf-8') as f:
                        f.write(restart_script)
                    
                    self.logger.info("正在通过批处理脚本重启程序...")
                    # 启动重启脚本并退出当前程序
                    os.system('start restart.bat')
                    sys.exit(0)
                except Exception as e:
                    self.logger.error(f"创建重启脚本失败: {e}")
                    self.logger.info("程序已停止，请手动重启")
                    sys.exit(0)
            else:
                # Linux/Unix环境，尝试简单重启
                self.logger.info("程序已停止，请手动重启")
                sys.exit(0)
    
    def _is_running_under_systemd(self) -> bool:
        """检测是否运行在systemd下"""
        import os
        import platform
        
        # Windows环境下肯定不是systemd
        if platform.system() == 'Windows':
            return False
            
        try:
            # 检查是否有systemd相关环境变量
            if 'SYSTEMD_EXEC_PID' in os.environ:
                return True
            # 检查父进程是否为systemd（仅Linux）
            if os.path.exists('/proc/1/comm'):
                with open('/proc/1/comm', 'r') as f:
                    init_process = f.read().strip()
                    if init_process == 'systemd':
                        return True
            # 检查当前进程的服务状态（仅Linux）
            import subprocess
            result = subprocess.run(['systemctl', 'is-active', 'domain-monitor'], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except:
            # 如果检查失败，假设不是systemd环境
            return False
    
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
        
        # 获取新的间隔时间和域名
        new_interval = self.config_manager.get('check.interval_minutes', 30)
        domains = self.config_manager.get_domains()
        
        # 更新内存中的当前间隔时间
        self.current_interval = new_interval
        
        # 更新关键配置
        telegram_config = self.config_manager.get('telegram', {})
        self.bot.bot_token = telegram_config.get('bot_token')
        self.bot.chat_id = telegram_config.get('chat_id')
        self.bot.api_base_url = f"https://api.telegram.org/bot{self.bot.bot_token}"
        
        # 更新通知器的配置
        if self.notifier:
            self.notifier.bot_token = self.bot.bot_token
            self.notifier.chat_id = self.bot.chat_id
            self.notifier.api_base_url = f"https://api.telegram.org/bot{self.bot.bot_token}"
        
        self.logger.info(f"重新加载后，域名列表包含 {len(domains)} 个域名")
        
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
                f"🌐 监控域名：{len(domains)} 个\n"
                f"✅ 新的间隔时间已生效\n"
                f"⏱️ 下次检查将在 {new_interval} 分钟后执行"
            )
        else:
            await self.bot.send_message(
                f"🔄 **配置已重新加载**\n\n"
                f"🌐 监控域名：{len(domains)} 个\n"
                f"✅ 配置更新成功\n"
                f"💡 检查间隔未改变 ({new_interval} 分钟)"
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
        
        # 启动 HTTP API 服务器
        if self.http_server:
            await self.http_server.start_server()
            self.logger.info("HTTP API 服务器已启动")
        
        # 发送启动通知
        domains = self.config_manager.get_domains()
        interval = self.config_manager.get('check.interval_minutes', 30)
        self.current_interval = interval  # 初始化当前间隔时间
        
        # 获取更多配置信息
        notification_config = self.config_manager.get('notification', {})
        check_config = self.config_manager.get('check', {})
        daily_report_config = self.config_manager.get('daily_report', {})
        
        notify_level = notification_config.get('level', 'smart')
        failure_threshold = notification_config.get('failure_threshold', 2)
        max_concurrent = check_config.get('max_concurrent', 50)
        timeout_seconds = check_config.get('timeout_seconds', 10)
        retry_count = check_config.get('retry_count', 3)
        daily_report_enabled = daily_report_config.get('enabled', False)
        daily_report_time = daily_report_config.get('time', '00:00')
        
        level_desc = {
            'all': '始终通知',
            'error': '仅错误时',
            'smart': '智能通知'
        }
        
        # 计算首次检查的预估时间
        domain_count = len(domains)
        batches = (domain_count + max_concurrent - 1) // max_concurrent
        estimated_seconds = batches * (timeout_seconds + 2)
        eta_minutes = estimated_seconds // 60
        eta_seconds = estimated_seconds % 60
        
        await self.bot.send_message(
            f"🚀 **域名监控服务已启动**\n\n"
            f"📊 **监控配置**\n"
            f"├ 监控域名: {len(domains)} 个\n"
            f"├ 检查周期: 每 {interval} 分钟\n"
            f"├ 并发线程: {max_concurrent}\n"
            f"├ 超时限制: {timeout_seconds} 秒\n"
            f"└ 失败重试: {retry_count} 次\n\n"
            f"🔔 **通知模式**\n"
            f"├ 当前级别: {level_desc.get(notify_level, notify_level)}\n"
            f"└ 每日统计: {daily_report_time if daily_report_enabled else '关闭'}\n\n"
            f"⏱️ **启动首次检查**\n"
            f"├ 待检域名: {domain_count} 个\n"
            f"├ 执行批次: {batches} 批\n"
            f"└ 预计用时: 约 {eta_minutes}分{eta_seconds}秒\n\n"
            f"💡 输入 /help 查看完整命令\n"
            f"⚡ 输入 /check 立即执行手动检查"
        )
        
        # 启动定时检查任务（包含首次检查）
        self.logger.info(f"定时检查已启动，最大循环时间 {interval} 分钟")
        self.schedule_task = asyncio.create_task(self.schedule_checks())
        
        # 启动每日报告任务
        daily_config = self.config_manager.get('daily_report', {})
        if daily_config.get('enabled', False):
            self.logger.info(f"每日报告已启用，将在 {daily_config.get('time', '00:00')} 发送")
            self.daily_report_task = asyncio.create_task(self.schedule_daily_report())
        
        print("\n监控服务正在运行中...")
        print("可以在 Telegram 群组中使用 /help 查看所有命令")
        print("按 Ctrl+C 停止服务\n")
        
        # 收集所有任务
        tasks = [self.bot_task, self.schedule_task]
        if self.daily_report_task:
            tasks.append(self.daily_report_task)
        
        try:
            # 等待所有后台任务
            # 使用while循环检查is_running状态，以便及时响应Ctrl+C
            while self.is_running:
                try:
                    # 等待任务一小段时间，并检查是否有任务完成
                    done, pending = await asyncio.wait(
                        tasks,
                        timeout=1.0,  # 1秒超时
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # 如果有任务完成且不是正常结束，停止程序
                    for task in done:
                        if task.exception() and not isinstance(task.exception(), asyncio.CancelledError):
                            self.logger.error(f"任务出错: {task.exception()}")
                            self.is_running = False
                            break
                    
                    # 如果所有任务都完成了，退出循环
                    if not pending:
                        break
                        
                except asyncio.TimeoutError:
                    # 超时是正常的，继续循环
                    continue
        except KeyboardInterrupt:
            self.logger.info("收到Ctrl+C信号，正在停止...")
            self.is_running = False
        finally:
            # 只有在程序还在运行时才调用停止（避免重复调用）
            if self.is_running:
                await self.stop()
            print("\n监控服务已停止")


def main():
    """主函数入口

    程序的入口点，创建监控器实例并运行
    处理退出信号和异常
    支持命令行参数指定配置文件
    """
    import argparse

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="域名监控服务")
    parser.add_argument('--config', '-c', default='config.json',
                       help='配置文件路径 (默认: config.json)')
    args = parser.parse_args()

    # 创建监控器实例，使用指定的配置文件
    monitor = DomainMonitor(config_file=args.config)

    try:
        # 使用 asyncio.run 运行异步主程序
        # 这个函数会创建事件循环并运行直到完成
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        # 处理 Ctrl+C
        print("\n程序已退出")
        sys.exit(0)  # 正常退出
    except Exception as e:
        # 处理其他未捕获的异常
        print(f"程序运行出错：{e}")
        sys.exit(1)  # 退出码 1 表示异常退出


if __name__ == "__main__":
    main()