import httpx
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
from domain_checker import CheckResult, CheckStatus
from collections import defaultdict


class TelegramNotifier:
    """Telegram 通知器类"""
    
    def __init__(self, bot_token: str, chat_id: str, cooldown_minutes: int = 60):
        """
        初始化 Telegram 通知器
        
        Args:
            bot_token: Telegram Bot Token
            chat_id: 群组或频道 ID
            cooldown_minutes: 通知冷却时间（分钟）
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.cooldown_minutes = cooldown_minutes
        self.logger = logging.getLogger(__name__)
        
        # 记录每个域名的上次通知时间，用于冷却控制
        self.last_notification_time: Dict[str, datetime] = {}
        
        # 记录每个域名的连续失败次数
        self.failure_count: Dict[str, int] = {}
        
        # API 基础 URL
        self.api_base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def _should_notify(self, url: str, failure_threshold: int = 2) -> bool:
        """
        判断是否应该发送通知
        
        Args:
            url: 域名 URL
            failure_threshold: 失败阈值
            
        Returns:
            bool: 是否应该发送通知
        """
        # 检查是否在冷却期内
        if url in self.last_notification_time:
            time_since_last = datetime.now() - self.last_notification_time[url]
            if time_since_last < timedelta(minutes=self.cooldown_minutes):
                remaining_minutes = self.cooldown_minutes - int(time_since_last.total_seconds() / 60)
                self.logger.debug(f"域名 {url} 在冷却期内，还需等待 {remaining_minutes} 分钟")
                return False
        
        # 检查连续失败次数是否达到阈值
        if self.failure_count.get(url, 0) < failure_threshold:
            self.logger.debug(f"域名 {url} 失败次数 {self.failure_count.get(url, 0)} 未达到阈值 {failure_threshold}")
            return False
        
        return True
    
    def _format_error_message(self, result: CheckResult) -> str:
        """
        格式化错误消息
        
        Args:
            result: 检查结果
            
        Returns:
            str: 格式化后的消息
        """
        # 使用 emoji 来让消息更直观
        status_emoji = {
            CheckStatus.DNS_ERROR: "🔍",
            CheckStatus.CONNECTION_ERROR: "🔌",
            CheckStatus.TIMEOUT: "⏱️",
            CheckStatus.HTTP_ERROR: "❌",
            CheckStatus.SSL_ERROR: "🔒",
            CheckStatus.UNKNOWN_ERROR: "❓"
        }
        
        emoji = status_emoji.get(result.status, "⚠️")
        
        # 构建可点击的URL
        clickable_url = result.url if result.url.startswith('http') else f"https://{result.domain_name}"
        
        message = f"{emoji} **域名监控告警**\n\n"
        message += f"📛 **域名**: [{result.domain_name}]({clickable_url})\n"
        message += f"🔗 **URL**: {clickable_url}\n"
        message += f"⚠️ **错误类型**: {result.status.value}\n"
        message += f"📝 **错误描述**: \n{result.get_error_description()}\n"
        message += f"🕐 **检测时间**: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if result.status == CheckStatus.HTTP_ERROR and result.status_code:
            message += f"📊 **HTTP 状态码**: {result.status_code}\n"
        
        # 添加建议
        suggestions = {
            CheckStatus.DNS_ERROR: "请检查域名配置是否正确，DNS 服务器是否正常",
            CheckStatus.CONNECTION_ERROR: "请检查服务器是否在线，防火墙设置是否正确",
            CheckStatus.TIMEOUT: "请检查服务器负载，网络连接是否稳定",
            CheckStatus.HTTP_ERROR: "请检查网站服务是否正常运行",
            CheckStatus.SSL_ERROR: "请检查 SSL 证书是否有效，是否已过期",
            CheckStatus.UNKNOWN_ERROR: "请查看详细日志了解具体错误"
        }
        
        if result.status in suggestions:
            message += f"\n💡 **建议**: {suggestions[result.status]}"
        
        return message
    
    def _format_recovery_message(self, result: CheckResult) -> str:
        """
        格式化恢复消息
        
        Args:
            result: 检查结果
            
        Returns:
            str: 格式化后的消息
        """
        # 构建可点击的URL
        clickable_url = result.url if result.url.startswith('http') else f"https://{result.domain_name}"
        
        message = f"✅ **域名恢复正常**\n\n"
        message += f"📛 **域名**: [{result.domain_name}]({clickable_url})\n"
        message += f"🔗 **URL**: {clickable_url}\n"
        message += f"📊 **状态码**: {result.status_code}\n"
        if result.response_time:
            message += f"⚡ **响应时间**: {result.response_time:.2f} 秒\n"
        message += f"🕐 **恢复时间**: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        return message
    
    async def send_message(self, message: str, parse_mode: str = "Markdown") -> bool:
        """
        发送消息到 Telegram
        
        Args:
            message: 要发送的消息
            parse_mode: 消息格式（Markdown 或 HTML）
            
        Returns:
            bool: 是否发送成功
        """
        # Telegram 消息长度限制
        MAX_MESSAGE_LENGTH = 4096
        
        # 如果消息过长，截断并添加提示
        if len(message) > MAX_MESSAGE_LENGTH:
            # 保留一些空间用于添加截断提示
            truncate_at = MAX_MESSAGE_LENGTH - 100
            message = message[:truncate_at] + "\n\n... [消息已截断，请查看日志获取完整信息]"
            self.logger.warning(f"消息过长，已截断至 {MAX_MESSAGE_LENGTH} 字符")
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.api_base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        self.logger.info("Telegram 消息发送成功")
                        return True
                    else:
                        self.logger.error(f"Telegram API 返回错误：{data.get('description')}")
                        return False
                else:
                    self.logger.error(f"Telegram 消息发送失败，状态码：{response.status_code}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"发送 Telegram 消息时发生错误：{str(e)}")
            return False
    
    async def notify_failures(self, 
                             results: List[CheckResult], 
                             failure_threshold: int = 2,
                             notify_recovery: bool = True,
                             notify_all_success: bool = False,
                             quiet_on_success: bool = False,
                             is_manual: bool = False,
                             next_run_time: Optional[datetime] = None,
                             new_errors: Optional[List[CheckResult]] = None,
                             recovered: Optional[List[CheckResult]] = None,
                             persistent_errors: Optional[List[CheckResult]] = None) -> None:
        """
        通知检查结果（简化版，只发送汇总）
        
        Args:
            results: 检查结果列表
            failure_threshold: 失败阈值
            notify_recovery: 是否通知恢复
            notify_all_success: 是否在全部正常时通知
            quiet_on_success: 定时检查时，如果全部成功是否静默（不发送通知）
            is_manual: 是否为手动触发的检查
            new_errors: 新增的错误（智能模式）
            recovered: 已恢复的域名（智能模式）
            persistent_errors: 持续错误（智能模式）
        """
        # 更新失败计数（用于内部跟踪）
        for result in results:
            if result.is_success:
                self.failure_count[result.url] = 0
            else:
                self.failure_count[result.url] = self.failure_count.get(result.url, 0) + 1
        
        # 如果是智能模式并提供了详细信息
        if new_errors is not None or recovered is not None:
            await self._send_smart_notification(
                new_errors=new_errors or [],
                recovered=recovered or [],
                persistent_errors=persistent_errors or [],
                total_results=results,
                next_run_time=next_run_time
            )
        else:
            # 发送传统的检查完成通知
            await self._send_check_summary(results, notify_all_success, quiet_on_success, is_manual, next_run_time=next_run_time)
    
    async def _send_check_summary(self, results: List[CheckResult], notify_all_success: bool, 
                                  quiet_on_success: bool = False, is_manual: bool = False, 
                                  next_run_time: Optional[datetime] = None) -> None:
        """发送检查汇总通知（优化版，按错误类型分组）
        
        Args:
            results: 检查结果列表  
            notify_all_success: 是否在全部正常时发送通知
            quiet_on_success: 定时检查时，如果全部成功是否静默（不发送通知）
            is_manual: 是否为手动触发的检查
        """
        if not results:
            return
            
        # 统计结果
        total_count = len(results)
        success_count = sum(1 for r in results if r.is_success)
        failed_count = total_count - success_count
        
        # 添加调试日志
        self.logger.info(f"检查汇总 - is_manual: {is_manual}, total: {total_count}, success: {success_count}, failed: {failed_count}")
        
        # 决定是否发送通知的逻辑：
        # 1. 手动检查：总是发送通知
        # 2. 定时检查且有失败：总是发送通知
        # 3. 定时检查且全部成功：根据quiet_on_success和notify_all_success决定
        if not is_manual and failed_count == 0:
            if quiet_on_success:
                self.logger.info(f"定时检查完成：{total_count} 个域名全部正常，静默模式已启用，不发送通知")
                return
            elif not notify_all_success:
                self.logger.info(f"定时检查完成：{total_count} 个域名全部正常，未启用全部成功通知")
                return
        
        # 手动检查时，总是发送通知
        if is_manual:
            self.logger.info(f"手动检查触发，将发送检查结果通知")
        
        # 构建汇总消息
        if failed_count == 0:
            # 全部正常
            message = f"✅ **全部正常**\n\n"
            message += f"🔍 检查域名: {total_count} 个\n"
            message += f"🌟 状态: 全部在线\n"
            message += f"⏰ 时间: {datetime.now().strftime('%H:%M:%S')}\n\n"
            
            # 添加下次执行时间
            if next_run_time:
                time_diff = (next_run_time - datetime.now()).total_seconds()
                if time_diff > 0:
                    minutes = int(time_diff // 60)
                    seconds = int(time_diff % 60)
                    message += f"⏰ 下次检查将在 {minutes} 分 {seconds} 秒后开始\n"
                    message += f"📅 具体时间: {next_run_time.strftime('%H:%M:%S')}"
                else:
                    message += f"⏰ 下次检查将立即开始"
        else:
            # 有异常域名，按更细致的错误类型分组
            error_groups = defaultdict(list)
            for result in results:
                if not result.is_success:
                    # 对HTTP错误进行更细致的分类，每个状态码单独分组
                    if result.status == CheckStatus.HTTP_ERROR and result.status_code:
                        # 每个状态码都单独作为一个分组
                        error_groups[f'http_{result.status_code}'].append(result)
                    else:
                        # 使用枚举对象作为键，保持一致性
                        error_groups[result.status].append(result)
            
            message = f"⚠️ **检查结果**\n\n"
            message += f"📊 **整体状态**\n"
            message += f"🔍 检查域名: {total_count} 个\n"
            message += f"✅ 正常在线: {success_count} 个\n"
            message += f"❌ 异常域名: {failed_count} 个\n\n"
            
            # 按错误类型显示（更细致的分类）
            error_names = {
                CheckStatus.DNS_ERROR: ("🔍", "DNS解析失败"),
                CheckStatus.CONNECTION_ERROR: ("🔌", "无法建立连接"),
                CheckStatus.TIMEOUT: ("⏱️", "访问超时"),
                CheckStatus.SSL_ERROR: ("🔒", "SSL证书问题"),
                CheckStatus.WEBSOCKET_ERROR: ("🌐", "WebSocket连接失败"),
                CheckStatus.PHISHING_WARNING: ("🎣", "钓鱼网站警告"),
                CheckStatus.SECURITY_WARNING: ("🚨", "安全风险警告"),
                CheckStatus.UNKNOWN_ERROR: ("❓", "未知错误"),
                # HTTP状态码具体分类
                'http_520': ("⚠️", "Cloudflare错误 (520未知错误)"),
                'http_521': ("⚠️", "Cloudflare错误 (521服务器离线)"),
                'http_522': ("⚠️", "Cloudflare错误 (522连接超时)"),
                'http_523': ("⚠️", "Cloudflare错误 (523源站不可达)"),
                'http_524': ("⚠️", "Cloudflare错误 (524超时)"),
                'http_525': ("⚠️", "Cloudflare错误 (525SSL握手失败)"),
                'http_526': ("⚠️", "Cloudflare错误 (526SSL证书无效)"),
                'http_502': ("🚪", "网关错误 (502坏网关)"),
                'http_503': ("🚪", "网关错误 (503服务暂不可用)"),
                'http_504': ("🚪", "网关错误 (504网关超时)"),
                'http_500': ("💥", "服务器内部错误 (500)"),
                'http_403': ("🚫", "访问被拒绝 (403禁止访问)"),
                'http_401': ("🚫", "访问被拒绝 (401未授权)"),
                'http_451': ("🚫", "访问被拒绝 (451法律原因)"),
                'http_404': ("🔎", "页面不存在 (404)"),
                'http_400': ("⚠️", "请求错误 (400错误请求)"),
                'http_429': ("⚠️", "请求错误 (429请求过多)")
            }
            
            # 收集所有错误域名信息
            error_messages = []
            current_message = f"⚠️ **检查结果**\n\n"
            current_message += f"📊 **整体状态**\n"
            current_message += f"🔍 检查域名: {total_count} 个\n"
            current_message += f"✅ 正常在线: {success_count} 个\n"
            current_message += f"❌ 异常域名: {failed_count} 个\n\n"
            
            # 定义显示顺序（具体的HTTP状态码和其他错误类型）
            display_order = [
                # Cloudflare错误
                'http_520', 'http_521', 'http_522', 'http_523', 'http_524', 'http_525', 'http_526',
                # 网关错误
                'http_502', 'http_503', 'http_504',
                # 其他HTTP错误
                'http_500', 'http_403', 'http_401', 'http_451', 'http_404', 'http_400', 'http_429',
                # 非HTTP错误
                CheckStatus.DNS_ERROR, CheckStatus.CONNECTION_ERROR, 
                CheckStatus.TIMEOUT, CheckStatus.SSL_ERROR,
                CheckStatus.WEBSOCKET_ERROR, CheckStatus.PHISHING_WARNING,
                CheckStatus.SECURITY_WARNING, CheckStatus.UNKNOWN_ERROR
            ]
            
            # 处理所有错误组（包括预定义的和未知的）
            all_statuses = list(display_order) + [s for s in error_groups.keys() if s not in display_order]
            
            for status in all_statuses:
                if status not in error_groups:
                    continue
                    
                domains = error_groups[status]
                if not domains:
                    continue
                    
                # 获取错误名称，如果是枚举则使用其值
                if isinstance(status, CheckStatus):
                    status_value = status.value
                else:
                    status_value = status
                
                # 对未知的HTTP状态码生成默认名称
                if isinstance(status, str) and status.startswith('http_') and status not in error_names:
                    code = status.replace('http_', '')
                    emoji, name = ("❌", f"HTTP错误 ({code})")
                else:
                    emoji, name = error_names.get(status, ("⚠️", status_value.upper()))
                    
                domain_count = len(domains)
                
                # 添加错误类型标题
                section_header = f"**{emoji} {name} ({domain_count}个):**\n"
                
                # 检查是否需要新消息
                if len(current_message) + len(section_header) > 3500:
                    error_messages.append(current_message)
                    current_message = f"⚠️ **错误详情（续）**\n\n"
                
                current_message += section_header
                
                # 显示域名列表
                for result in domains:
                    domain_line = f"  • {result.domain_name}\n"
                        
                    # 检查是否会超过消息长度限制
                    if len(current_message) + len(domain_line) > 3500:
                        error_messages.append(current_message + "\n")
                        current_message = f"⚠️ **错误详情（续）**\n\n"
                        current_message += f"**{emoji} {name}（续）:**\n"
                    
                    current_message += domain_line
                
                current_message += "\n"
            
            # 添加时间戳到最后一条消息
            time_info = f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # 添加下次执行时间
            if next_run_time:
                time_diff = (next_run_time - datetime.now()).total_seconds()
                if time_diff > 0:
                    minutes = int(time_diff // 60)
                    seconds = int(time_diff % 60)
                    time_info += f"⏰ 下次检查将在 {minutes} 分 {seconds} 秒后开始\n"
                    time_info += f"📅 具体时间: {next_run_time.strftime('%H:%M:%S')}"
                else:
                    time_info += f"⏰ 下次检查将立即开始"
            
            # 添加时间信息到最后一条消息
            if len(current_message) + len(time_info) > 4000:
                error_messages.append(current_message)
                error_messages.append(time_info)
            else:
                current_message += time_info
                error_messages.append(current_message)
            
            # 发送所有消息
            send_success = True
            for i, msg in enumerate(error_messages):
                if i > 0:
                    # 在消息之间添加小延迟，避免被限流
                    await asyncio.sleep(0.5)
                
                success = await self.send_message(msg)
                if success:
                    self.logger.info(f"检查汇总通知 {i+1}/{len(error_messages)} 已发送")
                else:
                    self.logger.error(f"检查汇总通知 {i+1}/{len(error_messages)} 发送失败")
                    send_success = False
            
            if send_success:
                self.logger.info(f"所有检查汇总通知已发送 - 共 {total_count} 个域名，{success_count} 个正常，{failed_count} 个异常")
            else:
                self.logger.error("部分检查汇总通知发送失败")
    
    async def _send_smart_notification(self, 
                                       new_errors: List[CheckResult],
                                       recovered: List[CheckResult],
                                       persistent_errors: List[CheckResult],
                                       total_results: List[CheckResult],
                                       next_run_time: Optional[datetime] = None) -> None:
        """
        发送智能通知（只通知变化）
        
        Args:
            new_errors: 新增的错误
            recovered: 已恢复的域名
            persistent_errors: 持续错误
            total_results: 所有检查结果
            next_run_time: 下次检查时间
        """
        # 如果没有任何变化，不发送通知
        if not new_errors and not recovered:
            self.logger.info("智能模式：没有新的变化，不发送通知")
            return
        
        # 构建消息
        message = "🔔 **状态变化通知**\n\n"
        
        # 新增错误
        if new_errors:
            message += f"🆕 **新出现问题 ({len(new_errors)}个)**:\n"
            for error in new_errors:  # 显示所有新错误
                # 为HTTP错误提供具体的状态码描述
                if error.status == CheckStatus.HTTP_ERROR and error.status_code:
                    if error.status_code == 520:
                        status_desc = "Cloudflare错误 (520未知错误)"
                    elif error.status_code == 521:
                        status_desc = "Cloudflare错误 (521服务器离线)"
                    elif error.status_code == 522:
                        status_desc = "Cloudflare错误 (522连接超时)"
                    elif error.status_code == 523:
                        status_desc = "Cloudflare错误 (523源站不可达)"
                    elif error.status_code == 524:
                        status_desc = "Cloudflare错误 (524超时)"
                    elif error.status_code == 525:
                        status_desc = "Cloudflare错误 (525SSL握手失败)"
                    elif error.status_code == 526:
                        status_desc = "Cloudflare错误 (526SSL证书无效)"
                    elif error.status_code == 502:
                        status_desc = "网关错误 (502坏网关)"
                    elif error.status_code == 503:
                        status_desc = "网关错误 (503服务暂不可用)"
                    elif error.status_code == 504:
                        status_desc = "网关错误 (504网关超时)"
                    elif error.status_code == 500:
                        status_desc = "服务器内部错误 (500)"
                    elif error.status_code == 403:
                        status_desc = "访问被拒绝 (403禁止访问)"
                    elif error.status_code == 401:
                        status_desc = "访问被拒绝 (401未授权)"
                    elif error.status_code == 451:
                        status_desc = "访问被拒绝 (451法律原因)"
                    elif error.status_code == 404:
                        status_desc = "页面不存在 (404)"
                    elif error.status_code == 400:
                        status_desc = "请求错误 (400错误请求)"
                    elif error.status_code == 429:
                        status_desc = "请求错误 (429请求过多)"
                    else:
                        status_desc = f"HTTP错误 ({error.status_code})"
                else:
                    # 非HTTP错误的描述
                    status_desc = {
                        'DNS_ERROR': 'DNS异常',
                        'CONNECTION_ERROR': '连接失败',
                        'TIMEOUT': '响应超时',
                        'HTTP_ERROR': 'HTTP错误',
                        'SSL_ERROR': 'SSL问题',
                        'WEBSOCKET_ERROR': 'WebSocket异常',
                        'PHISHING_WARNING': '钓鱼警告',
                        'SECURITY_WARNING': '安全警告'
                    }.get(error.status.value, error.status.value)
                message += f"• {error.domain_name} - {status_desc}\n"
            # 显示所有新错误，不省略
            message += "\n"
        
        # 已恢复
        if recovered:
            message += f"✅ **已恢复正常 ({len(recovered)}个)**:\n"
            for rec in recovered:  # 显示所有恢复的域名
                message += f"• {rec.domain_name}\n"
            message += "\n"
        
        # 持续错误提醒
        unack_count = len([e for e in persistent_errors if e.domain_name not in [r.domain_name for r in recovered]])
        if unack_count > 0:
            message += f"🔴 **持续异常**: 仍有 {unack_count} 个域名未恢复\n"
            message += "输入 `/errors` 查看完整列表\n\n"
        
        # 总体统计
        total_count = len(total_results)
        failed_count = len([r for r in total_results if not r.is_success])
        success_count = total_count - failed_count
        
        message += f"📊 **当前总体**:\n"
        message += f"• 监控总数: {total_count}\n"
        message += f"• 在线正常: {success_count}\n"
        message += f"• 异常域名: {failed_count}\n\n"
        
        # 时间信息
        message += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # 下次检查时间
        if next_run_time:
            time_diff = (next_run_time - datetime.now()).total_seconds()
            if time_diff > 0:
                minutes = int(time_diff // 60)
                seconds = int(time_diff % 60)
                message += f"⏰ 下次检查: {minutes}分{seconds}秒后"
        
        # 发送消息
        success = await self.send_message(message)
        if success:
            self.logger.info("智能通知已发送")
        else:
            self.logger.error("智能通知发送失败")
    
    async def _send_grouped_error_messages(self, error_groups: Dict[CheckStatus, List[CheckResult]]) -> None:
        """
        发送分组的错误通知
        
        Args:
            error_groups: 按错误类型分组的检查结果
        """
        # 错误类型的emoji和中文名称
        error_info = {
            CheckStatus.DNS_ERROR: ("🔍", "DNS解析错误"),
            CheckStatus.CONNECTION_ERROR: ("🔌", "连接失败"),
            CheckStatus.TIMEOUT: ("⏱️", "请求超时"),
            CheckStatus.HTTP_ERROR: ("❌", "HTTP错误"),
            CheckStatus.SSL_ERROR: ("🔒", "SSL证书错误"),
            CheckStatus.UNKNOWN_ERROR: ("❓", "未知错误")
        }
        
        # 建议信息
        suggestions = {
            CheckStatus.DNS_ERROR: "请检查域名配置是否正确，DNS服务器是否正常",
            CheckStatus.CONNECTION_ERROR: "请检查服务器是否在线，防火墙设置是否正确",
            CheckStatus.TIMEOUT: "请检查服务器负载，网络连接是否稳定",
            CheckStatus.HTTP_ERROR: "请检查网站服务是否正常运行",
            CheckStatus.SSL_ERROR: "请检查SSL证书是否有效，是否已过期",
            CheckStatus.UNKNOWN_ERROR: "请查看详细日志了解具体错误"
        }
        
        # 为每种错误类型发送一条合并消息
        for status, results in error_groups.items():
            if not results:
                continue
            
            emoji, error_name = error_info.get(status, ("⚠️", "错误"))
            
            # 构建消息
            message = f"{emoji} **域名监控告警 - {error_name}**\n\n"
            message += f"📊 **异常数量**: {len(results)} 个域名\n"
            message += f"🕐 **检测时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # 列出所有异常域名
            message += f"🔴 **异常域名列表**:\n"
            for result in results[:20]:  # 最多显示20个，避免消息过长
                clickable_url = result.url if result.url.startswith('http') else f"https://{result.domain_name}"
                message += f"  • [{result.domain_name}]({clickable_url})"
                
                # 如果是HTTP错误，显示状态码
                if status == CheckStatus.HTTP_ERROR and result.status_code:
                    message += f" (状态码: {result.status_code})"
                
                # 如果有特定错误信息，显示摘要
                if result.error_message and len(result.error_message) < 50:
                    message += f"\n    └ {result.error_message[:50]}"
                
                message += "\n"
            
            # 显示所有域名，不省略
            
            # 添加建议
            if status in suggestions:
                message += f"\n💡 **建议**: {suggestions[status]}"
            
            # 发送消息
            success = await self.send_message(message)
            if success:
                self.logger.info(f"{error_name} 类型的 {len(results)} 个域名异常通知已发送")
            else:
                self.logger.error(f"{error_name} 类型的异常通知发送失败")
    
    async def _send_grouped_recovery_message(self, recovery_domains: List[CheckResult]) -> None:
        """
        发送分组的恢复通知
        
        Args:
            recovery_domains: 恢复的域名列表
        """
        if not recovery_domains:
            return
        
        message = f"✅ **域名恢复通知**\n\n"
        message += f"📊 **恢复数量**: {len(recovery_domains)} 个域名\n"
        message += f"🕐 **恢复时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 列出恢复的域名
        message += f"🟢 **已恢复域名列表**:\n"
        for result in recovery_domains[:20]:  # 最多显示20个
            clickable_url = result.url if result.url.startswith('http') else f"https://{result.domain_name}"
            message += f"  • [{result.domain_name}]({clickable_url})"
            
            if result.status_code:
                message += f" (状态码: {result.status_code})"
            
            if result.response_time:
                message += f" - 响应时间: {result.response_time:.2f}秒"
            
            message += "\n"
        
        # 显示所有恢复的域名，不省略
        
        message += f"\n🎉 所有域名已恢复正常运行"
        
        # 发送消息
        success = await self.send_message(message)
        if success:
            self.logger.info(f"{len(recovery_domains)} 个域名的恢复通知已发送")
        else:
            self.logger.error("恢复通知发送失败")
    
    async def test_connection(self) -> bool:
        """
        测试 Telegram Bot 连接
        
        Returns:
            bool: 连接是否正常
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.api_base_url}/getMe")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        bot_info = data.get("result", {})
                        self.logger.info(f"Telegram Bot 连接成功：@{bot_info.get('username')}")
                        # 不再发送测试消息，避免重复
                        return True
                    else:
                        self.logger.error(f"Telegram Bot Token 无效：{data.get('description')}")
                        return False
                else:
                    self.logger.error(f"无法连接到 Telegram API，状态码：{response.status_code}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"测试 Telegram 连接时发生错误：{str(e)}")
            return False