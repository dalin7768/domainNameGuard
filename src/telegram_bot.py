import httpx
import asyncio
import logging
from typing import Dict, Optional, Callable, Any
from datetime import datetime
import json
from config_manager import ConfigManager
from cloudflare_manager import CloudflareManager


class TelegramBot:
    """Telegram Bot 命令处理器"""
    
    def __init__(self, config_manager: ConfigManager):
        """
        初始化 Telegram Bot
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.bot_token = config_manager.get('telegram.bot_token')
        self.chat_id = config_manager.get('telegram.chat_id')
        self.logger = logging.getLogger(__name__)
        
        # Cloudflare管理器
        self.cf_manager = CloudflareManager(config_manager=config_manager)
        
        # API 基础 URL
        self.api_base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # 上次处理的更新 ID
        self.last_update_id = 0
        # 记录已处理的消息ID，避免重复处理
        self.processed_messages = set()
        
        # 记录正在执行的命令，防止重复执行
        self.executing_commands = set()  # 存储正在执行的命令类型
        self.command_tasks = {}  # 存储命令任务引用
        
        # 运行标志
        self.is_running = True
        
        # 命令处理器映射
        self.commands: Dict[str, Callable] = {
            '/help': self.cmd_help,
            '/start': self.cmd_start,
            '/status': self.cmd_status,
            '/list': self.cmd_list_domains,
            '/add': self.cmd_add_domain,
            '/remove': self.cmd_remove_domain,
            '/clear': self.cmd_clear_domains,
            '/check': self.cmd_check_now,
            '/config': self.cmd_show_config,
            '/interval': self.cmd_set_interval,
            '/timeout': self.cmd_set_timeout,
            '/retry': self.cmd_set_retry,
            '/concurrent': self.cmd_set_concurrent,
            '/threshold': self.cmd_set_threshold,
            '/cooldown': self.cmd_set_cooldown,
            '/recovery': self.cmd_toggle_recovery,
            '/notify': self.cmd_set_notify_level,  # 新的通知级别命令
            '/autoadjust': self.cmd_toggle_autoadjust,
            '/errors': self.cmd_show_errors,  # 查看错误状态
            '/history': self.cmd_show_history,  # 查看历史记录
            '/ack': self.cmd_acknowledge_error,  # 确认处理错误
            '/admin': self.cmd_admin,
            '/stop': self.cmd_stop,
            '/restart': self.cmd_restart,
            '/reload': self.cmd_reload,
            '/dailyreport': self.cmd_daily_report,
            '/apikey': self.cmd_update_api_key,
            
            # Cloudflare相关命令
            '/cfhelp': self.cmd_cloudflare_help,
            '/cftoken': self.cmd_manage_cf_token,
            '/cflist': self.cmd_list_cf_tokens,
            '/cfzones': self.cmd_get_cf_zones,
            '/cfexport': self.cmd_export_cf_domains,
            '/cfexportall': self.cmd_export_all_cf_domains,
            '/cfverify': self.cmd_verify_cf_token,
            '/cfmerge': self.cmd_merge_cf_domains
        }
        
        # 检查回调函数
        self.check_callback: Optional[Callable] = None
        self.stop_callback: Optional[Callable] = None
        self.restart_callback: Optional[Callable] = None
        self.reload_callback: Optional[Callable] = None
        self.get_status_callback: Optional[Callable] = None  # 获取状态信息的回调
        self.send_daily_report_callback: Optional[Callable] = None  # 发送每日报告的回调
        self.error_tracker_callback: Optional[Callable] = None  # 获取错误跟踪器的回调
    
    def set_callbacks(self, check: Optional[Callable] = None, 
                      stop: Optional[Callable] = None,
                      restart: Optional[Callable] = None,
                      reload: Optional[Callable] = None,
                      get_status: Optional[Callable] = None,
                      send_daily_report: Optional[Callable] = None,
                      error_tracker: Optional[Callable] = None):
        """设置回调函数"""
        if check:
            self.check_callback = check
        if stop:
            self.stop_callback = stop
        if restart:
            self.restart_callback = restart
        if reload:
            self.reload_callback = reload
        if get_status:
            self.get_status_callback = get_status
        if send_daily_report:
            self.send_daily_report_callback = send_daily_report
        if error_tracker:
            self.error_tracker_callback = error_tracker
    
    async def send_message(self, text: str, parse_mode: str = "Markdown", 
                          reply_to: Optional[int] = None) -> bool:
        """发送消息"""
        try:
            params = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            if reply_to:
                params["reply_to_message_id"] = reply_to
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.api_base_url}/sendMessage",
                    json=params
                )
                
                if response.status_code == 200:
                    return True
                else:
                    try:
                        error_data = response.json()
                        self.logger.error(f"发送消息失败: {response.status_code}, 详情: {error_data}")
                    except:
                        self.logger.error(f"发送消息失败: {response.status_code}, 响应: {response.text[:200]}")
                    
                    # 如果是400错误且是Markdown格式问题，尝试用纯文本重发
                    if response.status_code == 400 and parse_mode == "Markdown":
                        self.logger.info("尝试使用纯文本格式重新发送")
                        return await self.send_message(text, parse_mode="", reply_to=reply_to)
                    
                    return False
                    
        except Exception as e:
            self.logger.error(f"发送消息时出错: {e}")
            return False
    
    async def get_updates(self) -> list:
        """获取新消息"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.api_base_url}/getUpdates",
                    params={
                        "offset": self.last_update_id + 1,
                        "timeout": 25
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        return data.get("result", [])
            return []
            
        except Exception as e:
            self.logger.error(f"获取更新时出错: {e}")
            return []
    
    def is_authorized(self, user_id: int, username: str = None) -> bool:
        """检查用户是否有权限
        
        Args:
            user_id: 用户ID（已弃用）
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        return self.config_manager.is_admin_by_username(username)
    
    async def process_update(self, update: dict) -> None:
        """处理单个更新"""
        try:
            # 更新最后处理的 ID
            update_id = update.get("update_id", 0)
            if update_id > self.last_update_id:
                self.last_update_id = update_id
            
            # 只处理消息
            if "message" not in update:
                return
            
            message = update["message"]
            message_id = message.get("message_id")
            
            # 检查消息是否已处理过
            if message_id in self.processed_messages:
                return
            
            # 标记消息为已处理
            self.processed_messages.add(message_id)
            
            # 清理旧的已处理消息ID（保留最近100个）
            if len(self.processed_messages) > 100:
                # 保留最新的100个
                sorted_ids = sorted(self.processed_messages)
                self.processed_messages = set(sorted_ids[-100:])
            
            # 只处理群组消息
            chat = message.get("chat", {})
            if str(chat.get("id")) != self.chat_id:
                return
            
            # 获取消息文本
            text = message.get("text", "").strip()
            if not text:
                return
            
            # 获取发送者信息
            from_user = message.get("from", {})
            user_id = from_user.get("id")
            username = from_user.get("username", "Unknown")
            
            # 解析命令和参数
            parts = text.split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            # 处理 @机器人 的命令（兼容旧版）
            if '@' in command:
                command = command.split('@')[0]
            
            # 如果不是命令（不以 / 开头），忽略
            if not command.startswith('/'):
                return
            
            # 执行命令
            if command in self.commands:
                # 检查权限
                if command not in ['/help', '/start', '/status', '/list']:
                    if not self.is_authorized(user_id, username):
                        await self.send_message(
                            "❌ 您没有权限执行此命令",
                            reply_to=message_id
                        )
                        return
                
                # 检查是否有同类命令正在执行（针对特定命令）
                blocking_commands = ['/check', '/reload', '/stop', '/restart']
                if command in blocking_commands:
                    if command in self.executing_commands:
                        await self.send_message(
                            f"⏳ {command} 命令正在执行中，请稍后再试",
                            reply_to=message_id
                        )
                        self.logger.warning(f"命令 {command} 正在执行中，忽略重复请求")
                        return
                
                self.logger.info(f"用户 @{username} ({user_id}) 执行命令: {command} {args}")
                
                # 创建命令执行的包装函数
                async def execute_command_wrapper():
                    try:
                        # 标记命令开始执行
                        if command in blocking_commands:
                            self.executing_commands.add(command)
                        
                        # 执行命令
                        await self.commands[command](args, message_id, user_id, username)
                        
                    finally:
                        # 命令执行完成，移除标记
                        if command in blocking_commands:
                            self.executing_commands.discard(command)
                            if command in self.command_tasks:
                                del self.command_tasks[command]
                
                # 使用 create_task 异步执行命令，不阻塞消息处理循环
                task = asyncio.create_task(execute_command_wrapper())
                
                # 保存任务引用（用于特定命令）
                if command in blocking_commands:
                    self.command_tasks[command] = task
                
        except Exception as e:
            self.logger.error(f"处理更新时出错: {e}")
    
    # 命令处理函数
    async def cmd_help(self, args: str, msg_id: int, user_id: int, username: str):
        """帮助和配置命令"""
        # 获取当前配置信息
        check_config = self.config_manager.get('check', {})
        notification_config = self.config_manager.get('notification', {})
        domains = self.config_manager.get_domains()
        
        notify_level = notification_config.get('level', 'smart')
        level_desc = {
            'all': '始终通知',
            'error': '仅错误',
            'smart': '智能通知'
        }
        
        help_text = f"""📚 **域名监控机器人帮助**

⚙️ **当前配置**:
• 监控域名: {len(domains)} 个
• 检查间隔: {check_config.get('interval_minutes', 30)} 分钟
• 超时时间: {check_config.get('timeout_seconds', 10)} 秒
• 并发数: {check_config.get('max_concurrent', 10)} 个
• 通知级别: {level_desc.get(notify_level, notify_level)}
• 自适应并发: {'开启' if check_config.get('auto_adjust_concurrent', True) else '关闭'}

🌟 **基础命令**:
`/help` - 显示帮助和配置信息
`/status` - 查看详细监控状态
`/check` - 立即执行域名检查

📝 **域名管理**:
`/list` - 查看所有监控域名
`/add example.com` - 添加域名（支持批量）
`/remove example.com` - 删除域名（支持批量）
`/clear` - 清空所有域名

🔔 **通知设置**:
`/notify` - 查看/设置通知级别
`/notify all` - 始终通知
`/notify error` - 仅错误时通知
`/notify smart` - 智能通知（只通知变化）

🔍 **错误管理**:
`/errors` - 查看当前错误状态
`/history [days]` - 查看历史记录
`/ack domain.com` - 确认处理错误

🔧 **配置调整**:
`/interval 10` - 设置检查间隔（分钟）
`/timeout 15` - 设置超时时间（秒）
`/retry 3` - 设置重试次数
`/concurrent 20` - 设置并发数
`/threshold 3` - 设置失败阈值
`/cooldown 30` - 设置通知冷却（分钟）
`/recovery` - 切换恢复通知
`/autoadjust` - 切换自适应并发

🔄 **服务控制**:
`/reload` - 重新加载配置
`/restart` - 重启监控服务
`/stop` - 停止监控服务

📊 **统计报告**:
`/dailyreport` - 管理每日报告
`/dailyreport now` - 立即发送报告

👥 **管理员**:
`/admin list` - 查看管理员
`/admin add/remove ID` - 管理管理员

☁️ **Cloudflare集成**:
`/cfhelp` - 查看Cloudflare帮助
`/cftoken add/remove` - 管理API Token
`/cflist` - 查看我的Token列表
`/cfzones 名称` - 获取域名列表
`/cfexport 名称` - 导出域名到文件
`/cfmerge 名称` - 同步到监控配置

💡 **使用说明**:
• 支持批量操作，用空格或逗号分隔
• 域名无需 http:// 前缀
• 支持 WebSocket (wss://) 域名
• 配置修改立即生效，无需重启"""
        
        await self.send_message(help_text, reply_to=msg_id)
    
    async def cmd_start(self, args: str, msg_id: int, user_id: int, username: str):
        """启动命令"""
        welcome_text = f"""🚀 **域名监控机器人已启动**

欢迎 @{username}！

我可以帮助您监控域名的可用性，并在域名异常时发送告警。

🌟 **快速开始**:
`/add example.com` - 添加域名
`/add site1.com site2.com` - 批量添加
`/list` - 查看所有域名
`/check` - 立即检查
`/help` - 查看更多命令

💡 **提示**: 直接输入命令即可，不需要@机器人"""
        
        await self.send_message(welcome_text, reply_to=msg_id)
    
    async def cmd_status(self, args: str, msg_id: int, user_id: int, username: str):
        """状态命令"""
        domains = self.config_manager.get_domains()
        interval = self.config_manager.get('check.interval_minutes')
        
        # 构建基础状态信息
        status_text = f"""📊 **监控状态详情**

🔧 **基础信息**
├ 监控域名数: {len(domains)} 个
├ 检查间隔: {interval} 分钟
└ 服务状态: 🟢 运行中
"""
        
        # 如果有状态回调，获取详细统计信息
        if self.get_status_callback:
            try:
                status_info = await self.get_status_callback()
                
                # 添加运行时间信息
                if status_info.get('service_start_time'):
                    uptime = datetime.now() - status_info['service_start_time']
                    days = uptime.days
                    hours = uptime.seconds // 3600
                    minutes = (uptime.seconds % 3600) // 60
                    uptime_str = f"{days}天 {hours}小时 {minutes}分钟" if days > 0 else f"{hours}小时 {minutes}分钟"
                    status_text += f"\n⏱️ **运行时间**\n└ {uptime_str}\n"
                
                # 添加检查时间信息
                if status_info.get('last_check_time') or status_info.get('next_check_time'):
                    status_text += "\n🕐 **检查时间**\n"
                    
                    if status_info.get('last_check_time'):
                        last_check = status_info['last_check_time']
                        time_since = datetime.now() - last_check
                        mins_ago = int(time_since.total_seconds() / 60)
                        status_text += f"├ 上次检查: {last_check.strftime('%H:%M:%S')} ({mins_ago}分钟前)\n"
                    
                    if status_info.get('next_check_time'):
                        next_check = status_info['next_check_time']
                        time_until = next_check - datetime.now()
                        mins_until = max(0, int(time_until.total_seconds() / 60))
                        status_text += f"└ 下次检查: {next_check.strftime('%H:%M:%S')} ({mins_until}分钟后)\n"
                
                # 添加上次检查结果统计
                if status_info.get('last_check_results'):
                    results = status_info['last_check_results']
                    if results['total'] > 0:
                        success_rate = (results['success'] / results['total']) * 100
                        status_text += f"\n📈 **上次检查结果**\n"
                        status_text += f"├ 总数: {results['total']} 个\n"
                        status_text += f"├ ✅ 正常: {results['success']} 个\n"
                        status_text += f"├ ❌ 异常: {results['failed']} 个\n"
                        status_text += f"└ 成功率: {success_rate:.1f}%\n"
                        
                        # 显示错误类型分布
                        if results.get('error_types') and results['error_types']:
                            status_text += "\n🔍 **错误类型分布**\n"
                            error_types = results['error_types']
                            # 按数量排序
                            sorted_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
                            for i, (error_type, count) in enumerate(sorted_errors):
                                is_last = i == len(sorted_errors) - 1
                                prefix = "└" if is_last else "├"
                                # 简化错误类型名称
                                display_name = error_type.replace('_', ' ').title()
                                status_text += f"{prefix} {display_name}: {count} 个\n"
                
                # 添加总体统计
                if status_info.get('total_checks_count'):
                    status_text += f"\n📊 **总体统计**\n"
                    status_text += f"└ 总检查次数: {status_info['total_checks_count']} 次\n"
                    
            except Exception as e:
                self.logger.error(f"获取状态信息时出错: {e}")
                # 继续显示基础信息
        
        status_text += "\n💡 **快速操作**\n"
        status_text += "├ /list - 查看域名列表\n"
        status_text += "├ /check - 立即检查\n"
        status_text += "└ /help - 查看帮助和配置"
        
        await self.send_message(status_text, reply_to=msg_id)
    
    async def cmd_list_domains(self, args: str, msg_id: int, user_id: int, username: str):
        """列出域名命令"""
        domains = self.config_manager.get_domains()
        
        if not domains:
            await self.send_message(
                "📝 **当前没有监控的域名**\n\n"
                "💡 快速添加：\n"
                "`/add example.com`\n"
                "`/add google.com baidu.com github.com`",
                reply_to=msg_id
            )
            return
        
        # 检查重复域名
        unique_domains = list(dict.fromkeys(domains))
        has_duplicates = len(domains) != len(unique_domains)
        
        domain_list = "\n".join([f"{i+1}. `{domain}`" for i, domain in enumerate(domains)])
        
        # 构建消息
        text = f"""📝 **监控域名列表** ({len(domains)} 个)

{domain_list}

💡 **快速操作**:
`/add example.com` - 添加更多
`/remove example.com` - 删除域名
`/check` - 立即检查所有域名"""
        
        # 如果有重复，添加提示
        if has_duplicates:
            duplicate_count = len(domains) - len(unique_domains)
            text += f"\n\n⚠️ **发现 {duplicate_count} 个重复域名**"
            text += f"\n实际唯一域名数: {len(unique_domains)} 个"
        
        await self.send_message(text, reply_to=msg_id)
    
    async def cmd_add_domain(self, args: str, msg_id: int, user_id: int, username: str):
        """添加域名命令（支持批量）"""
        if not args:
            await self.send_message(
                "❌ 请提供要添加的域名\n\n"
                "💡 **使用示例**:\n"
                "`/add example.com`\n"
                "`/add google.com baidu.com`\n"
                "`/add example1.com example2.com example3.com`\n\n"
                "⚠️ 不需要添加 http:// 前缀",
                reply_to=msg_id
            )
            return
        
        # 支持批量添加（空格或逗号分隔）
        urls = args.replace(',', ' ').split()
        success_list = []
        fail_list = []
        
        for url in urls:
            url = url.strip()
            if url:
                success, message = self.config_manager.add_domain(url)
                if success:
                    success_list.append(url)
                else:
                    fail_list.append(f"{url} ({message.split(':')[-1].strip()})")
        
        # 构建响应消息
        response = ""
        if success_list:
            response += f"✅ **成功添加 {len(success_list)} 个域名**:\n"
            for url in success_list:
                response += f"  • {url}\n"
        
        if fail_list:
            response += f"\n❌ **失败 {len(fail_list)} 个**:\n"
            for item in fail_list:
                response += f"  • {item}\n"
        
        if response:
            domains_count = len(self.config_manager.get_domains())
            response += f"\n📋 当前共监控 **{domains_count}** 个域名"
            await self.send_message(response, reply_to=msg_id)
        else:
            await self.send_message("❌ 没有有效的域名", reply_to=msg_id)
    
    async def cmd_remove_domain(self, args: str, msg_id: int, user_id: int, username: str):
        """删除域名命令（支持批量）"""
        if not args:
            await self.send_message(
                "❌ 请提供要删除的域名\n\n"
                "💡 **使用示例**:\n"
                "`/remove example.com`\n"
                "`/remove google.com baidu.com`\n"
                "`/remove example1.com example2.com`",
                reply_to=msg_id
            )
            return
        
        # 支持批量删除
        urls = args.replace(',', ' ').split()
        success_list = []
        fail_list = []
        
        for url in urls:
            url = url.strip()
            if url:
                success, message = self.config_manager.remove_domain(url)
                if success:
                    success_list.append(url)
                else:
                    fail_list.append(f"{url} (不存在)")
        
        # 构建响应消息
        response = ""
        if success_list:
            response += f"❌ **成功删除 {len(success_list)} 个域名**:\n"
            for url in success_list:
                response += f"  • {url}\n"
        
        if fail_list:
            response += f"\n⚠️ **未找到 {len(fail_list)} 个**:\n"
            for item in fail_list:
                response += f"  • {item}\n"
        
        if response:
            domains_count = len(self.config_manager.get_domains())
            response += f"\n📋 当前剩余 **{domains_count}** 个域名"
            await self.send_message(response, reply_to=msg_id)
        else:
            await self.send_message("❌ 没有有效的域名", reply_to=msg_id)
    
    async def cmd_clear_domains(self, args: str, msg_id: int, user_id: int, username: str):
        """清空域名命令"""
        success, message = self.config_manager.clear_domains()
        
        if success:
            await self.send_message(f"✅ {message}", reply_to=msg_id)
        else:
            await self.send_message(f"❌ {message}", reply_to=msg_id)
    
    async def cmd_check_now(self, args: str, msg_id: int, user_id: int, username: str):
        """立即检查命令"""
        if self.check_callback:
            # 直接触发检查，详细信息由 main.py 发送
            asyncio.create_task(self.check_callback(is_manual=True))
        else:
            await self.send_message("❌ 检查功能未就绪", reply_to=msg_id)
    
    async def cmd_show_config(self, args: str, msg_id: int, user_id: int, username: str):
        """显示当前配置"""
        try:
            config_info = []
            config_info.append("⚙️ **当前配置信息**\n")
            
            # 检查间隔
            interval = self.config_manager.get('check.interval_minutes', 30)
            config_info.append(f"🔄 检查间隔: {interval} 分钟")
            
            # 并发数
            max_concurrent = self.config_manager.get('check.max_concurrent', 5)
            config_info.append(f"⚡ 最大并发: {max_concurrent}")
            
            # 超时时间
            timeout = self.config_manager.get('check.timeout_seconds', 10)
            config_info.append(f"⏱️ 超时时间: {timeout} 秒")
            
            # 通知级别
            notify_level = self.config_manager.get('notification.level', 'smart')
            config_info.append(f"🔔 通知级别: {notify_level}")
            
            # 域名数量
            domains = self.config_manager.get_domains()
            config_info.append(f"🌐 监控域名: {len(domains)} 个")
            
            # HTTP API状态
            http_enabled = self.config_manager.get('http_api.enabled', False)
            http_port = self.config_manager.get('http_api.port', 8080)
            config_info.append(f"🌍 HTTP API: {'启用' if http_enabled else '禁用'} (端口: {http_port})")
            
            # Cloudflare 令牌数量
            cf_tokens = self.config_manager.config.get('cloudflare_tokens', {})
            config_info.append(f"☁️ Cloudflare 令牌: {len(cf_tokens)} 个")
            
            await self.send_message("\n".join(config_info), reply_to=msg_id)
            
        except Exception as e:
            self.logger.error(f"获取配置信息错误: {e}")
            await self.send_message(f"❌ 获取配置失败: {str(e)}", reply_to=msg_id)
    
    async def cmd_set_interval(self, args: str, msg_id: int, user_id: int, username: str):
        """设置检查间隔"""
        if not args:
            await self.send_message("❌ 请提供间隔时间（分钟）\n\n示例: `/interval 10`", reply_to=msg_id)
            return
        
        try:
            minutes = int(args.strip())
            old_interval = self.config_manager.get('check.interval_minutes', 30)
            success, message = self.config_manager.set_interval(minutes)
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
                
                # 如果间隔改变了，触发配置重新加载以立即生效
                if old_interval != minutes and self.reload_callback:
                    await self.send_message("🔄 正在重新加载配置以应用新的间隔时间...", reply_to=msg_id)
                    await self.reload_callback()
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        except ValueError:
            await self.send_message("❌ 请输入有效的数字", reply_to=msg_id)
    
    async def cmd_set_timeout(self, args: str, msg_id: int, user_id: int, username: str):
        """设置超时时间"""
        if not args:
            await self.send_message("❌ 请提供超时时间（秒）\n\n示例: `/timeout 10`", reply_to=msg_id)
            return
        
        try:
            seconds = int(args.strip())
            success, message = self.config_manager.set_timeout(seconds)
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        except ValueError:
            await self.send_message("❌ 请输入有效的数字", reply_to=msg_id)
    
    async def cmd_set_retry(self, args: str, msg_id: int, user_id: int, username: str):
        """设置重试次数"""
        if not args:
            await self.send_message("❌ 请提供重试次数\n\n示例: `/retry 3`", reply_to=msg_id)
            return
        
        try:
            count = int(args.strip())
            success, message = self.config_manager.set_retry(count)
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        except ValueError:
            await self.send_message("❌ 请输入有效的数字", reply_to=msg_id)
    
    async def cmd_set_concurrent(self, args: str, msg_id: int, user_id: int, username: str):
        """设置并发线程数"""
        if not args:
            await self.send_message("❌ 请提供并发数\n\n示例: `/concurrent 20`", reply_to=msg_id)
            return
        
        try:
            concurrent = int(args.strip())
            if concurrent < 1 or concurrent > 100:
                await self.send_message("❌ 并发数必须在 1-100 之间", reply_to=msg_id)
                return
            
            self.config_manager.set('check.max_concurrent', concurrent)
            self.config_manager.save_config()
            await self.send_message(f"✅ 并发线程数已设置为: {concurrent}", reply_to=msg_id)
        except ValueError:
            await self.send_message("❌ 请输入有效的数字", reply_to=msg_id)
    
    async def cmd_set_threshold(self, args: str, msg_id: int, user_id: int, username: str):
        """设置失败阈值"""
        if not args:
            await self.send_message("❌ 请提供失败阈值\n\n示例: `/threshold 3`", reply_to=msg_id)
            return
        
        try:
            threshold = int(args.strip())
            success, message = self.config_manager.set_failure_threshold(threshold)
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        except ValueError:
            await self.send_message("❌ 请输入有效的数字", reply_to=msg_id)
    
    async def cmd_set_cooldown(self, args: str, msg_id: int, user_id: int, username: str):
        """设置冷却时间"""
        if not args:
            await self.send_message("❌ 请提供冷却时间（分钟）\n\n示例: `/cooldown 30`", reply_to=msg_id)
            return
        
        try:
            minutes = int(args.strip())
            success, message = self.config_manager.set_cooldown(minutes)
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        except ValueError:
            await self.send_message("❌ 请输入有效的数字", reply_to=msg_id)
    
    async def cmd_toggle_recovery(self, args: str, msg_id: int, user_id: int, username: str):
        """切换恢复通知"""
        success, message = self.config_manager.toggle_recovery_notification()
        
        if success:
            await self.send_message(f"✅ {message}", reply_to=msg_id)
        else:
            await self.send_message(f"❌ {message}", reply_to=msg_id)
    
    async def cmd_toggle_all_success(self, args: str, msg_id: int, user_id: int, username: str):
        """切换全部正常时通知"""
        success, message = self.config_manager.toggle_all_success_notification()
        
        if success:
            await self.send_message(f"✅ {message}", reply_to=msg_id)
        else:
            await self.send_message(f"❌ {message}", reply_to=msg_id)
    
    async def cmd_toggle_autoadjust(self, args: str, msg_id: int, user_id: int, username: str):
        """切换自适应并发"""
        current = self.config_manager.get('check.auto_adjust_concurrent', True)
        new_value = not current
        self.config_manager.set('check.auto_adjust_concurrent', new_value)
        self.config_manager.save_config()
        
        status = "开启" if new_value else "关闭"
        await self.send_message(f"✅ 自适应并发已{status}", reply_to=msg_id)
    
    async def cmd_admin(self, args: str, msg_id: int, user_id: int, username: str):
        """管理员命令"""
        if not args:
            await self.send_message(
                "❌ 请提供子命令\n\n"
                "**示例**:\n"
                "`/admin add @username` - 添加管理员\n"
                "`/admin remove @username` - 移除管理员\n"
                "`/admin list` - 查看管理员列表", 
                reply_to=msg_id
            )
            return
        
        parts = args.split()
        if len(parts) < 1:
            await self.send_message("❌ 参数错误", reply_to=msg_id)
            return
        
        action = parts[0].lower()
        
        if action == "list":
            admins = self.config_manager.get('telegram.admin_users', [])
            if not admins:
                await self.send_message("📝 当前没有设置管理员\n\n所有人都可以执行命令", reply_to=msg_id)
            else:
                admin_list = "\n".join([f"• `{admin}`" for admin in admins])
                await self.send_message(f"👥 **管理员列表**:\n\n{admin_list}", reply_to=msg_id)
        
        elif action in ["add", "remove"]:
            if len(parts) < 2:
                await self.send_message("❌ 请提供用户名\n\n示例: `/admin add @username`", reply_to=msg_id)
                return
            
            target_username = parts[1]
            
            if action == "add":
                success, message = self.config_manager.add_admin_by_username(target_username)
            else:
                success, message = self.config_manager.remove_admin_by_username(target_username)
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        
        else:
            await self.send_message("❌ 未知的子命令", reply_to=msg_id)
    
    async def cmd_stop(self, args: str, msg_id: int, user_id: int, username: str):
        """停止监控 - 立即强制停止"""
        if self.stop_callback:
            await self.send_message("🛑 正在强制停止监控服务...", reply_to=msg_id)
            # 设置停止标志，结束监听循环
            self.is_running = False
            # 调用停止回调，传递send_notification=False避免重复发送消息
            await self.stop_callback(send_notification=False, force=True)
            # 停止后立即退出程序
            import sys
            self.logger.info("收到停止命令，程序即将退出")
            sys.exit(0)
        else:
            await self.send_message("❌ 停止功能未就绪", reply_to=msg_id)
    
    async def cmd_restart(self, args: str, msg_id: int, user_id: int, username: str):
        """重启监控服务"""
        if self.restart_callback:
            await self.send_message(
                "🔄 **正在重启服务**\n\n"
                "服务将在几秒后重新启动...",
                reply_to=msg_id
            )
            # 调用重启回调
            await self.restart_callback()
        else:
            # 如果没有重启回调，使用系统重启
            await self.send_message(
                "🔄 **正在重启服务**\n\n"
                "使用 systemd 或 PM2 管理的服务将自动重启...",
                reply_to=msg_id
            )
            # 设置停止标志
            self.is_running = False
            if self.stop_callback:
                await self.stop_callback(send_notification=False, force=True)
            # 退出程序，让 systemd/PM2 重启
            import sys
            import os
            self.logger.info("收到重启命令，程序即将退出并重启")
            # 退出码3表示需要重启
            os._exit(3)
    
    async def cmd_reload(self, args: str, msg_id: int, user_id: int, username: str):
        """重新加载配置"""
        if self.reload_callback:
            await self.send_message("🔄 正在重新加载配置...", reply_to=msg_id)
            await self.reload_callback()
        else:
            await self.send_message("❌ 重新加载功能未就绪", reply_to=msg_id)
    
    async def cmd_update_api_key(self, args: str, msg_id: int, user_id: int, username: str):
        """更新HTTP API密钥"""
        try:
            # 生成新的安全API密钥
            import secrets
            new_api_key = secrets.token_urlsafe(32)
            
            # 更新配置
            self.config_manager.set('http_api.auth.api_key', new_api_key)
            self.config_manager.save_config()
            
            # 发送确认消息（不显示完整密钥，只显示前8位和后4位）
            masked_key = f"{new_api_key[:8]}***{new_api_key[-4:]}"
            
            await self.send_message(
                f"🔑 **API密钥已更新**\n\n"
                f"新密钥: `{masked_key}`\n"
                f"完整密钥已保存到配置文件\n\n"
                f"⚠️ **重要提醒**:\n"
                f"• 请更新所有使用API的客户端\n"
                f"• 旧密钥将立即失效\n"
                f"• 如需重启服务请使用 `/restart`",
                reply_to=msg_id
            )
            
            self.logger.info(f"API密钥已更新，操作者: {username}")
            
        except Exception as e:
            self.logger.error(f"更新API密钥失败: {e}")
            await self.send_message(f"❌ 更新API密钥失败: {str(e)}", reply_to=msg_id)
    
    async def cmd_set_notify_level(self, args: str, msg_id: int, user_id: int, username: str):
        """设置通知级别"""
        if not args:
            current = self.config_manager.get('notification.level', 'smart')
            await self.send_message(
                f"🔔 **通知级别设置**\n\n"
                f"当前级别: `{current}`\n\n"
                f"可用级别：\n"
                f"`/notify all` - 始终通知（不管成功与否）\n"
                f"`/notify error` - 仅错误时通知\n"
                f"`/notify smart` - 智能通知（只通知变化）\n\n"
                f"💡 **智能通知说明**：\n"
                f"• 新增错误时通知\n"
                f"• 域名恢复时通知\n"
                f"• 错误类型变化时通知\n"
                f"• 重复错误不通知",
                reply_to=msg_id
            )
            return
        
        level = args.strip().lower()
        if level not in ['all', 'error', 'smart']:
            await self.send_message(
                f"❌ 无效的通知级别\n\n"
                f"请使用: `all`, `error` 或 `smart`",
                reply_to=msg_id
            )
            return
        
        self.config_manager.set('notification.level', level)
        self.config_manager.save_config()
        
        level_desc = {
            'all': '始终通知',
            'error': '仅错误时通知',
            'smart': '智能通知（只通知变化）'
        }
        
        await self.send_message(
            f"✅ **通知级别已更改**\n\n"
            f"当前设置: {level_desc[level]}",
            reply_to=msg_id
        )
    
    async def cmd_show_errors(self, args: str, msg_id: int, user_id: int, username: str):
        """显示当前错误状态"""
        if hasattr(self, 'error_tracker_callback') and self.error_tracker_callback:
            tracker = await self.error_tracker_callback()
            if tracker:
                unack_errors = tracker.get_unacknowledged_errors()
                ack_errors = tracker.get_acknowledged_errors()
                
                message = "🔴 **当前错误状态**\n\n"
                
                if unack_errors:
                    message += f"⚠️ **未处理错误 ({len(unack_errors)}个)**:\n"
                    for error in unack_errors[:10]:  # 最多显示10个
                        message += f"• {error.domain_name} - {error.status.value}\n"
                    if len(unack_errors) > 10:
                        message += f"• ... 还有 {len(unack_errors) - 10} 个\n"
                    message += "\n"
                
                if ack_errors:
                    message += f"✅ **已确认处理 ({len(ack_errors)}个)**:\n"
                    for error in ack_errors[:5]:
                        message += f"• {error.domain_name}\n"
                    if len(ack_errors) > 5:
                        message += f"• ... 还有 {len(ack_errors) - 5} 个\n"
                    message += "\n"
                
                if not unack_errors and not ack_errors:
                    message += "✨ 没有错误域名\n\n"
                
                message += "💡 **使用说明**:\n"
                message += "`/ack domain.com` - 确认处理某个错误\n"
                message += "`/history` - 查看历史记录"
                
                await self.send_message(message, reply_to=msg_id)
            else:
                await self.send_message("❌ 错误跟踪器未就绪", reply_to=msg_id)
        else:
            await self.send_message("❌ 错误跟踪功能未启用", reply_to=msg_id)
    
    async def cmd_show_history(self, args: str, msg_id: int, user_id: int, username: str):
        """显示历史记录"""
        if hasattr(self, 'error_tracker_callback') and self.error_tracker_callback:
            tracker = await self.error_tracker_callback()
            if tracker:
                # 解析参数
                domain = None
                days = 7
                
                if args:
                    parts = args.split()
                    for part in parts:
                        if part.isdigit():
                            days = int(part)
                        else:
                            domain = part
                
                # 获取历史记录
                history = tracker.get_history(domain=domain, days=days)
                
                # 获取统计信息
                stats = tracker.get_statistics(days=days)
                
                message = f"📈 **历史记录 (过去{days}天)**\n\n"
                
                # 统计摘要
                message += f"📊 **统计摘要**:\n"
                message += f"• 总错误次数: {stats['total_errors']}\n"
                message += f"• 恢复次数: {stats['total_recoveries']}\n"
                message += f"• 当前错误: {stats['current_errors']}\n"
                message += f"• 未处理: {stats['unacknowledged_errors']}\n\n"
                
                # 错误类型分布
                if stats['error_types']:
                    message += f"🔍 **错误类型**:\n"
                    for error_type, count in stats['error_types'].items():
                        message += f"• {error_type}: {count}次\n"
                    message += "\n"
                
                # 最常出错的域名
                if stats['top_error_domains']:
                    message += f"🔝 **TOP错误域名**:\n"
                    for domain_name, count in stats['top_error_domains'][:5]:
                        message += f"• {domain_name}: {count}次\n"
                    message += "\n"
                
                # 最近记录
                if history:
                    message += f"🕒 **最近记录**:\n"
                    for record in history[-10:]:  # 最近10条
                        time_str = record.timestamp.split('T')[1][:8]
                        status_emoji = '✅' if record.status == 'recovered' else '❌'
                        message += f"{status_emoji} {time_str} - {record.domain_name}\n"
                
                await self.send_message(message, reply_to=msg_id)
            else:
                await self.send_message("❌ 错误跟踪器未就绪", reply_to=msg_id)
        else:
            await self.send_message("❌ 历史记录功能未启用", reply_to=msg_id)
    
    async def cmd_acknowledge_error(self, args: str, msg_id: int, user_id: int, username: str):
        """确认处理错误"""
        if not args:
            await self.send_message(
                f"❌ 请指定域名\n\n"
                f"示例: `/ack example.com`\n"
                f"或: `/ack example.com 已联系运维处理`",
                reply_to=msg_id
            )
            return
        
        parts = args.split(maxsplit=1)
        domain = parts[0]
        notes = parts[1] if len(parts) > 1 else None
        
        if hasattr(self, 'error_tracker_callback') and self.error_tracker_callback:
            tracker = await self.error_tracker_callback()
            if tracker:
                # 检查域名是否在错误列表中
                current_errors = tracker.current_errors
                if domain in current_errors:
                    tracker.acknowledge_error(domain, notes)
                    await self.send_message(
                        f"✅ **已确认处理**\n\n"
                        f"域名: {domain}\n"
                        f"备注: {notes or '无'}\n\n"
                        f"该域名将不再重复通知，直到恢复正常",
                        reply_to=msg_id
                    )
                else:
                    await self.send_message(
                        f"⚠️ 域名 {domain} 当前没有错误",
                        reply_to=msg_id
                    )
            else:
                await self.send_message("❌ 错误跟踪器未就绪", reply_to=msg_id)
        else:
            await self.send_message("❌ 确认功能未启用", reply_to=msg_id)
    
    async def cmd_daily_report(self, args: str, msg_id: int, user_id: int, username: str):
        """管理每日统计报告"""
        if not args:
            # 显示当前状态
            daily_config = self.config_manager.get('daily_report', {})
            enabled = daily_config.get('enabled', False)
            report_time = daily_config.get('time', '00:00')
            
            status_text = f"📊 **每日报告设置**\n\n"
            status_text += f"状态: {'✅ 已启用' if enabled else '❌ 已禁用'}\n"
            status_text += f"发送时间: {report_time}\n\n"
            status_text += "**使用方法**:\n"
            status_text += "`/dailyreport enable` - 启用每日报告\n"
            status_text += "`/dailyreport disable` - 禁用每日报告\n"
            status_text += "`/dailyreport time 08:00` - 设置发送时间\n"
            status_text += "`/dailyreport now` - 立即发送今日报告"
            
            await self.send_message(status_text, reply_to=msg_id)
            return
        
        parts = args.split()
        action = parts[0].lower()
        
        if action == "enable":
            self.config_manager.set('daily_report.enabled', True)
            self.config_manager.save_config()
            await self.send_message(
                "✅ 每日报告已启用\n\n"
                "报告将在每天指定时间发送（需重启服务生效）",
                reply_to=msg_id
            )
        
        elif action == "disable":
            self.config_manager.set('daily_report.enabled', False)
            self.config_manager.save_config()
            await self.send_message("❌ 每日报告已禁用", reply_to=msg_id)
        
        elif action == "time":
            if len(parts) < 2:
                await self.send_message(
                    "❌ 请提供时间\n\n示例: `/dailyreport time 08:00`",
                    reply_to=msg_id
                )
                return
            
            time_str = parts[1]
            # 验证时间格式
            try:
                hour, minute = map(int, time_str.split(':'))
                if 0 <= hour < 24 and 0 <= minute < 60:
                    self.config_manager.set('daily_report.time', time_str)
                    self.config_manager.save_config()
                    await self.send_message(
                        f"⏰ 每日报告时间已设置为: {time_str}\n\n"
                        "（需重启服务生效）",
                        reply_to=msg_id
                    )
                else:
                    await self.send_message("❌ 无效的时间格式", reply_to=msg_id)
            except:
                await self.send_message(
                    "❌ 无效的时间格式\n\n请使用 HH:MM 格式，如 08:00",
                    reply_to=msg_id
                )
        
        elif action == "now":
            # 立即发送今日报告
            if self.send_daily_report_callback:
                await self.send_message("📊 正在生成今日统计报告...", reply_to=msg_id)
                await self.send_daily_report_callback()
            else:
                await self.send_message("❌ 报告功能未就绪", reply_to=msg_id)
        
        else:
            await self.send_message("❌ 未知的子命令", reply_to=msg_id)
    
    async def listen_for_commands(self):
        """监听命令的主循环"""
        self.logger.info("开始监听 Telegram 命令")
        
        while self.is_running:  # 检查运行标志
            try:
                updates = await self.get_updates()
                for update in updates:
                    asyncio.create_task(self.process_update(update))
                
                if not updates:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"监听命令时出错: {e}")
                await asyncio.sleep(5)
        
        self.logger.info("Telegram 命令监听已停止")
    
    # ==================== Cloudflare 相关命令 ====================
    
    async def cmd_cloudflare_help(self, args: str, msg_id: int, user_id: int, username: str):
        """Cloudflare帮助命令"""
        help_text = """☁️ **Cloudflare 域名管理**

🔑 **Token 管理**:
`/cftoken add 名称 YOUR_API_TOKEN` - 添加API Token
`/cftoken remove 名称` - 删除API Token  
`/cflist` - 查看我的Token列表
`/cfverify 名称` - 验证Token是否有效

🌐 **域名操作**:
`/cfzones 名称` - 获取Token下的所有域名
`/cfexport 名称 [格式] [sync]` - 导出单个Token域名到文件
`/cfexportall [格式] [sync]` - 导出所有Token域名到文件（合并）
`/cfmerge [名称] [模式]` - 导出并直接合并到监控配置

🔄 **cfmerge 合并模式详解**:
• `replace` - 完全替换现有监控域名（清空后重新添加CF域名）
• `merge` - 合并域名（保留现有 + 添加CF域名，去重）
• `add` - 仅添加新域名（只添加监控中不存在的CF域名）

⚠️ **注意**: cfmerge操作过程中不会频繁发送进度通知，只在完成或出错时通知

📝 **使用说明**:
• 每个用户可以添加多个API Token
• Token名称用于区分不同账号
• 导出支持txt、json、csv格式
• 支持同步删除功能（sync参数）
• 可单独或合并导出所有Token域名
• cfmerge直接更新监控配置，无需手动同步

💡 **示例**:
`/cftoken add 主账号 abcd1234...`
`/cfzones 主账号`
`/cfexport 主账号 json sync` - 导出为JSON并同步删除
`/cfexportall txt` - 合并导出所有Token为TXT格式
`/cfmerge 主账号 replace` - 用主账号域名完全替换监控列表
`/cfmerge 主账号 merge` - 合并主账号域名到现有监控列表
`/cfmerge merge` - 合并所有Token域名到监控列表"""
        
        await self.send_message(help_text, reply_to=msg_id)
    
    async def cmd_manage_cf_token(self, args: str, msg_id: int, user_id: int, username: str):
        """管理Cloudflare Token"""
        if not args:
            await self.send_message(
                "❌ 请提供操作类型\n\n"
                "**使用方法**:\n"
                "`/cftoken add 名称 TOKEN` - 添加Token\n"
                "`/cftoken remove 名称` - 删除Token\n\n"
                "**示例**:\n"
                "`/cftoken add 主账号 abcd1234efgh5678...`",
                reply_to=msg_id
            )
            return
        
        parts = args.split()
        if len(parts) < 2:
            await self.send_message("❌ 参数不足", reply_to=msg_id)
            return
        
        action = parts[0].lower()
        token_name = parts[1]
        
        if action == "add":
            if len(parts) < 3:
                await self.send_message("❌ 请提供API Token", reply_to=msg_id)
                return
            
            api_token = parts[2]
            success, message = self.cf_manager.token_manager.add_user_token(
                str(user_id), token_name, api_token
            )
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        
        elif action == "remove":
            success, message = self.cf_manager.token_manager.remove_user_token(
                str(user_id), token_name
            )
            
            if success:
                await self.send_message(f"✅ {message}", reply_to=msg_id)
            else:
                await self.send_message(f"❌ {message}", reply_to=msg_id)
        
        else:
            await self.send_message("❌ 无效的操作，请使用 add 或 remove", reply_to=msg_id)
    
    async def cmd_list_cf_tokens(self, args: str, msg_id: int, user_id: int, username: str):
        """列出用户的Cloudflare Tokens"""
        token_list = self.cf_manager.token_manager.list_user_tokens(str(user_id))
        await self.send_message(token_list, reply_to=msg_id)
    
    async def cmd_verify_cf_token(self, args: str, msg_id: int, user_id: int, username: str):
        """验证Cloudflare Token"""
        if not args:
            await self.send_message(
                "❌ 请提供Token名称\n\n"
                "**示例**: `/cfverify 主账号`",
                reply_to=msg_id
            )
            return
        
        token_name = args.strip()
        await self.send_message("🔄 正在验证Token...", reply_to=msg_id)
        
        result = await self.cf_manager.verify_user_token(str(user_id), token_name)
        
        if result["valid"]:
            await self.send_message(
                f"✅ **Token验证成功**\n\n"
                f"Token名称: {token_name}\n"
                f"Token ID: {result.get('token_id', 'N/A')}\n"
                f"状态: {result.get('status', 'active')}",
                reply_to=msg_id
            )
        else:
            await self.send_message(
                f"❌ **Token验证失败**\n\n"
                f"错误: {result.get('error', '未知错误')}",
                reply_to=msg_id
            )
    
    async def cmd_get_cf_zones(self, args: str, msg_id: int, user_id: int, username: str):
        """获取Cloudflare域名zones"""
        if not args:
            await self.send_message(
                "❌ 请提供Token名称\n\n"
                "**示例**: `/cfzones 主账号`",
                reply_to=msg_id
            )
            return
        
        token_name = args.strip()
        await self.send_message("🔄 正在获取域名列表...", reply_to=msg_id)
        
        result = await self.cf_manager.get_user_zones(str(user_id), token_name)
        
        if result["success"]:
            zones = result["zones"]
            if not zones:
                await self.send_message(
                    f"📝 **Token '{token_name}' 下没有域名**",
                    reply_to=msg_id
                )
                return
            
            # 构建域名列表
            zone_list = f"🌐 **域名列表** ({len(zones)} 个)\n\n"
            for i, zone in enumerate(zones[:20], 1):  # 最多显示20个
                zone_name = zone.get("name", "")
                zone_status = zone.get("status", "")
                status_emoji = "🟢" if zone_status == "active" else "🟡"
                zone_list += f"{i}. {status_emoji} `{zone_name}`\n"
            
            if len(zones) > 20:
                zone_list += f"\n... 还有 {len(zones) - 20} 个域名"
            
            zone_list += f"\n\n💡 使用 `/cfexport {token_name}` 导出所有域名"
            
            await self.send_message(zone_list, reply_to=msg_id)
        else:
            await self.send_message(
                f"❌ **获取域名失败**\n\n"
                f"错误: {result.get('error', '未知错误')}",
                reply_to=msg_id
            )
    
    async def cmd_export_cf_domains(self, args: str, msg_id: int, user_id: int, username: str):
        """导出单个Token的Cloudflare域名"""
        if not args:
            await self.send_message(
                "❌ 请提供Token名称\n\n"
                "**示例**: `/cfexport 主账号 [格式] [sync]`\n"
                "• **格式**: txt, json, csv (可选)\n"
                "• **sync**: 添加此参数启用同步删除功能",
                reply_to=msg_id
            )
            return
        
        parts = args.split()
        token_name = parts[0]
        format_type = parts[1] if len(parts) > 1 and parts[1] in ["txt", "json", "csv"] else None
        sync_delete = "sync" in parts
        
        await self.send_message("🔄 正在导出域名，请稍候...", reply_to=msg_id)
        
        result = await self.cf_manager.export_single_token_domains(
            str(user_id), token_name, format_type, sync_delete
        )
        
        if result["success"]:
            # 构建响应消息
            response = f"✅ **单个Token域名导出成功**\n\n"
            response += f"📊 **统计信息**:\n"
            response += f"• Token名称: `{token_name}`\n"
            response += f"• 域名总数: {result['total_domains']}\n"
            response += f"• Zone数量: {result['total_zones']}\n"
            response += f"• 导出文件: `{result['export_filename']}`\n"
            response += f"• 文件路径: `{result['export_file']}`\n"
            
            if result.get("sync_delete_count", 0) > 0:
                response += f"• 同步删除: {result['sync_delete_count']} 个域名\n"
            
            # 显示前10个域名作为预览
            domains = result["domains"]
            if domains:
                response += f"\n📝 **域名预览** (前10个):\n"
                for i, domain in enumerate(domains[:10], 1):
                    response += f"{i}. `{domain}`\n"
                
                if len(domains) > 10:
                    response += f"... 还有 {len(domains) - 10} 个域名\n"
            
            response += f"\n💡 **其他操作**:\n"
            response += f"• `/cfmerge {token_name}` - 同步到监控配置\n"
            response += f"• `/cfexportall` - 导出所有Token域名"
            
            await self.send_message(response, reply_to=msg_id)
        else:
            await self.send_message(
                f"❌ **导出失败**\n\n"
                f"错误: {result.get('error', '未知错误')}",
                reply_to=msg_id
            )
    
    async def cmd_export_all_cf_domains(self, args: str, msg_id: int, user_id: int, username: str):
        """导出用户所有Token的域名（合并）"""
        parts = args.split() if args else []
        format_type = None
        sync_delete = False
        merge_to_config = False
        merge_mode = "replace"
        
        # 解析参数
        for part in parts:
            if part in ["txt", "json", "csv"]:
                format_type = part
            elif part == "sync":
                sync_delete = True
            elif part == "merge":
                merge_to_config = True
            elif part in ["replace", "add"]:
                merge_mode = part
                merge_to_config = True
        
        if merge_to_config:
            # 合并到配置模式
            await self.send_message(f"🔄 正在导出所有Token域名并{merge_mode}到配置中...", reply_to=msg_id)
            
            # 不发送进度通知，只记录错误
            async def progress_callback(domain: str, added_count: int, total_processed: int):
                # 仅记录到日志，不发送Telegram消息
                self.logger.debug(f"cfmerge进度: 已处理{total_processed}个域名，已添加{added_count}个域名")
            
            # 执行实时合并操作（所有Token）
            result = await self.cf_manager.export_and_merge_domains_realtime(
                str(user_id), None, merge_mode, progress_callback
            )
        else:
            # 原来的导出到文件模式
            await self.send_message("🔄 正在导出所有Token的域名，请稍候...", reply_to=msg_id)
            
            result = await self.cf_manager.export_all_user_tokens_domains(
                str(user_id), format_type, sync_delete
            )
        
        if result["success"]:
            if merge_to_config:
                # 合并到配置模式的响应
                try:
                    operation = str(result.get('operation', '导出'))
                    token_name = str(result.get('token_name', '所有Token'))
                    
                    response = f"✅ **所有Token域名{operation}成功**\n\n"
                    response += f"📊 **操作统计**:\n"
                    response += f"• Token: {token_name}\n"
                    response += f"• 合并模式: {merge_mode}\n"
                    response += f"• CF域名数: {result.get('cf_domains_count', 0)}\n"
                    response += f"• 操作前: {result.get('before_count', 0)} 个域名\n"
                    response += f"• 操作后: {result.get('after_count', 0)} 个域名\n"
                    
                    if result.get('added_count', 0) > 0:
                        response += f"• 新增域名: {result['added_count']} 个\n"
                    if result.get('removed_count', 0) > 0:
                        response += f"• 删除域名: {result['removed_count']} 个\n"
                    
                    response += f"\n💡 **提示**:\n"
                    response += f"• 配置已自动更新并保存\n"
                    response += f"• 使用 `/list` 查看当前监控域名\n"
                    response += f"• 使用 `/check` 立即开始监控"
                    
                    # 确保消息不太长
                    if len(response) > 4000:
                        response = response[:4000] + "..."
                    
                except Exception as e:
                    self.logger.error(f"构建合并响应消息失败: {e}")
                    response = "✅ 所有Token域名导出并合并到配置成功"
                    
            else:
                # 原来的导出到文件模式响应
                response = f"✅ **所有Token域名导出成功**\n\n"
                response += f"📊 **统计信息**:\n"
                response += f"• Token总数: {result.get('total_tokens', 0)}\n"
                response += f"• 域名总数: {result.get('total_domains', 0)}\n"
                response += f"• Zone总数: {result.get('total_zones', 0)}\n"
                
                if result.get('export_filename'):
                    response += f"• 导出文件: `{result['export_filename']}`\n"
                if result.get('export_file'):
                    response += f"• 文件路径: `{result['export_file']}`\n"
                
                if result.get("sync_delete_count", 0) > 0:
                    response += f"• 同步删除: {result['sync_delete_count']} 个域名\n"
                
                # 显示每个Token的详情
                token_results = result.get("token_results", {})
                if token_results:
                    response += f"\n📝 **Token详情**:\n"
                    for token_name, token_result in token_results.items():
                        if token_result.get("success"):
                            response += f"• `{token_name}`: {token_result.get('count', 0)} 个域名 ({token_result.get('zones', 0)} zones)\n"
                        else:
                            response += f"• `{token_name}`: ❌ {token_result.get('error', '未知错误')}\n"
                
                # 显示前10个域名作为预览
                domains = result.get("domains", [])
                if domains:
                    response += f"\n📝 **域名预览** (前10个):\n"
                    for i, domain in enumerate(domains[:10], 1):
                        response += f"{i}. `{domain}`\n"
                
                if len(domains) > 10:
                    response += f"... 还有 {len(domains) - 10} 个域名\n"
            
            response += f"\n💡 **其他操作**:\n"
            response += f"• `/cfmerge merge` - 合并所有Token到监控配置"
            
            await self.send_message(response, reply_to=msg_id)
        else:
            await self.send_message(
                f"❌ **导出失败**\n\n"
                f"错误: {result.get('error', '未知错误')}",
                reply_to=msg_id
            )
    
    async def cmd_merge_cf_domains(self, args: str, msg_id: int, user_id: int, username: str):
        """导出CF域名并直接合并到domains配置"""
        parts = args.split() if args else []
        
        # 解析参数
        token_name = None
        merge_mode = "replace"  # 默认替换模式
        
        # 解析命令参数
        for part in parts:
            if part in ["replace", "merge", "add"]:
                merge_mode = part
            elif part not in ["replace", "merge", "add"]:
                token_name = part
        
        # 如果没有指定token名称，询问用户
        if not token_name and merge_mode == "replace":
            # 获取用户的token列表
            user_tokens = self.cf_manager.token_manager.get_user_tokens(str(user_id))
            if not user_tokens:
                await self.send_message("❌ 您还没有添加任何Cloudflare Token", reply_to=msg_id)
                return
                
            if len(user_tokens) == 1:
                token_name = user_tokens[0]["name"]
            else:
                token_list = "\n".join([f"• `{token['name']}`" for token in user_tokens])
                await self.send_message(
                    "❌ 请指定Token名称或合并模式\n\n"
                    "**用法**:\n"
                    "`/cfmerge [Token名称] [模式]`\n\n"
                    "**可用Token**:\n"
                    f"{token_list}\n\n"
                    "**合并模式**:\n"
                    "• `replace` - 完全替换现有域名（默认）\n"
                    "• `merge` - 合并现有域名和CF域名\n"
                    "• `add` - 只添加新的CF域名\n\n"
                    "**示例**:\n"
                    "`/cfmerge 主账号 replace` - 用主账号域名替换\n"
                    "`/cfmerge merge` - 合并所有Token域名",
                    reply_to=msg_id
                )
                return
        
        # 显示操作提示
        mode_desc = {
            "replace": "替换所有域名",
            "merge": "合并域名", 
            "add": "添加新域名"
        }
        
        token_desc = token_name or "所有Token"
        await self.send_message(
            f"🔄 正在{mode_desc[merge_mode]}...\n"
            f"• Token: {token_desc}\n"
            f"• 模式: {merge_mode}",
            reply_to=msg_id
        )
        
        # 不发送进度通知，只记录错误
        async def progress_callback(domain: str, added_count: int, total_processed: int):
            # 仅记录到日志，不发送Telegram消息
            self.logger.debug(f"cfmerge进度: 已处理{total_processed}个域名，已添加{added_count}个域名")
        
        # 执行实时合并操作
        result = await self.cf_manager.export_and_merge_domains_realtime(
            str(user_id), token_name, merge_mode, progress_callback
        )
        
        if result["success"]:
            # 构建成功响应消息
            try:
                operation = str(result.get('operation', '操作'))
                token_name = str(result.get('token_name', '未知'))
                merge_mode = str(result.get('merge_mode', '未知'))
                
                response = f"✅ **域名{operation}成功**\n\n"
                response += f"📊 **操作统计**:\n"
                response += f"• Token: {token_name}\n"
                response += f"• 合并模式: {merge_mode}\n"
                response += f"• CF域名数: {result.get('cf_domains_count', 0)}\n"
                response += f"• 操作前: {result.get('before_count', 0)} 个域名\n"
                response += f"• 操作后: {result.get('after_count', 0)} 个域名\n"
                
                if result.get('added_count', 0) > 0:
                    response += f"• 新增域名: {result['added_count']} 个\n"
                if result.get('removed_count', 0) > 0:
                    response += f"• 删除域名: {result['removed_count']} 个\n"
                
                response += f"\n💡 **提示**:\n"
                response += f"• 配置已自动更新并保存\n"
                response += f"• 使用 `/list` 查看当前监控域名\n"
                response += f"• 使用 `/check` 立即开始监控"
                
                # 确保消息不太长
                if len(response) > 4000:
                    response = response[:4000] + "..."
                
                await self.send_message(response, reply_to=msg_id)
                
            except Exception as e:
                self.logger.error(f"发送成功消息失败: {e}")
                await self.send_message("✅ 域名合并操作成功完成", reply_to=msg_id)
            
        else:
            error_msg = result.get('error', '未知错误')
            # 确保错误消息不会导致Telegram格式问题
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "..."
            # 转义可能有问题的字符
            error_msg = error_msg.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
            
            await self.send_message(
                f"❌ **合并失败**\n\n"
                f"错误: {error_msg}",
                reply_to=msg_id
            )