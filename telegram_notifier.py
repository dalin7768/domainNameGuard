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
                             notify_all_success: bool = False) -> None:
        """
        通知检查结果
        
        Args:
            results: 检查结果列表
            failure_threshold: 失败阈值
            notify_recovery: 是否通知恢复
            notify_all_success: 是否在全部正常时通知
        """
        # 先发送检查完成汇总通知
        await self._send_check_summary(results, notify_all_success)
        
        # 收集需要发送告警的域名（按错误类型分组）
        error_groups = defaultdict(list)  # 按错误类型分组
        recovery_domains = []  # 需要发送恢复通知的域名
        
        # 处理各个域名的结果
        for result in results:
            if result.is_success:
                # 域名正常，检查是否需要发送恢复通知
                if result.url in self.failure_count and self.failure_count[result.url] >= failure_threshold:
                    if notify_recovery:
                        recovery_domains.append(result)
                        self.logger.info(f"域名 {result.domain_name} 已恢复")
                
                # 重置失败计数
                self.failure_count[result.url] = 0
                
            else:
                # 域名异常，增加失败计数
                self.failure_count[result.url] = self.failure_count.get(result.url, 0) + 1
                
                # 检查是否应该发送通知
                if self._should_notify(result.url, failure_threshold):
                    # 按错误类型分组
                    error_groups[result.status].append(result)
                    # 更新最后通知时间
                    self.last_notification_time[result.url] = datetime.now()
        
        # 发送恢复通知（如果有）
        if recovery_domains:
            await self._send_grouped_recovery_message(recovery_domains)
        
        # 发送分组的错误通知
        if error_groups:
            await self._send_grouped_error_messages(error_groups)
    
    async def _send_check_summary(self, results: List[CheckResult], notify_all_success: bool) -> None:
        """发送检查汇总通知
        
        Args:
            results: 检查结果列表  
            notify_all_success: 是否在全部正常时发送通知
        """
        if not results:
            return
            
        # 统计结果
        total_count = len(results)
        success_count = sum(1 for r in results if r.is_success)
        failed_count = total_count - success_count
        
        # 如果有失败的域名，总是发送汇总
        # 如果全部正常，根据notify_all_success决定是否发送
        if failed_count == 0 and not notify_all_success:
            self.logger.info(f"检查完成：{total_count} 个域名全部正常，未发送汇总通知")
            return
        
        # 构建汇总消息
        if failed_count == 0:
            # 全部正常
            message = f"✅ **检查完成**\n\n"
            message += f"🔍 已检查 **{total_count}** 个域名\n"
            message += f"🌟 全部正常运行\n"
            message += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        else:
            # 有异常域名
            message = f"⚠️ **检查完成**\n\n"
            message += f"🔍 已检查 **{total_count}** 个域名\n"
            message += f"✅ **{success_count}** 个正常\n"
            
            if failed_count > 0:
                message += f"❌ **{failed_count}** 个异常\n\n"
                message += f"🔴 **异常域名**：\n"
                
                # 列出异常域名
                for result in results:
                    if not result.is_success:
                        # 简化错误信息
                        error_type = {
                            CheckStatus.DNS_ERROR: "DNS错误",
                            CheckStatus.CONNECTION_ERROR: "连接失败",
                            CheckStatus.TIMEOUT: "超时",
                            CheckStatus.HTTP_ERROR: f"HTTP {result.status_code}",
                            CheckStatus.SSL_ERROR: "SSL错误",
                            CheckStatus.UNKNOWN_ERROR: "未知错误"
                        }.get(result.status, "错误")
                        
                        # 构建可点击的URL
                        clickable_url = result.url if result.url.startswith('http') else f"https://{result.domain_name}"
                        
                        # 使用Markdown格式创建可点击链接
                        message += f"  • [{result.domain_name}]({clickable_url}) - {error_type}\n"
            
            message += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
        
        # 发送汇总消息
        success = await self.send_message(message)
        if success:
            self.logger.info(f"检查汇总通知已发送 - 共 {total_count} 个域名，{success_count} 个正常，{failed_count} 个异常")
        else:
            self.logger.error("检查汇总通知发送失败")
    
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
            
            # 如果超过20个，显示省略信息
            if len(results) > 20:
                message += f"\n  ... 还有 {len(results) - 20} 个域名\n"
            
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
        
        # 如果超过20个，显示省略信息
        if len(recovery_domains) > 20:
            message += f"\n  ... 还有 {len(recovery_domains) - 20} 个域名\n"
        
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