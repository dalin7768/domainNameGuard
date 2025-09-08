import httpx
import asyncio
import logging
from typing import Dict, Optional, Callable, Any
from datetime import datetime
import json
from config_manager import ConfigManager


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
        
        # API 基础 URL
        self.api_base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # 上次处理的更新 ID
        self.last_update_id = 0
        # 记录已处理的消息ID，避免重复处理
        self.processed_messages = set()
        
        # 记录正在执行的命令，防止重复执行
        self.executing_commands = set()  # 存储正在执行的命令类型
        self.command_tasks = {}  # 存储命令任务引用
        
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
            '/threshold': self.cmd_set_threshold,
            '/cooldown': self.cmd_set_cooldown,
            '/recovery': self.cmd_toggle_recovery,
            '/allsuccess': self.cmd_toggle_all_success,
            '/admin': self.cmd_admin,
            '/stop': self.cmd_stop,
            '/restart': self.cmd_restart,
            '/reload': self.cmd_reload
        }
        
        # 检查回调函数
        self.check_callback: Optional[Callable] = None
        self.stop_callback: Optional[Callable] = None
        self.restart_callback: Optional[Callable] = None
        self.reload_callback: Optional[Callable] = None
    
    def set_callbacks(self, check: Optional[Callable] = None, 
                      stop: Optional[Callable] = None,
                      restart: Optional[Callable] = None,
                      reload: Optional[Callable] = None):
        """设置回调函数"""
        if check:
            self.check_callback = check
        if stop:
            self.stop_callback = stop
        if restart:
            self.restart_callback = restart
        if reload:
            self.reload_callback = reload
    
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
                    self.logger.error(f"发送消息失败: {response.status_code}")
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
        """帮助命令"""
        help_text = """📚 **域名监控机器人命令**

🌟 **基础命令**:
`/help` - 显示此帮助信息
`/start` - 开始使用机器人
`/status` - 查看监控状态

📝 **域名管理**:
`/list` - 查看所有监控域名
`/add example.com` - 添加域名（支持批量）
`/remove example.com` - 删除域名（支持批量）
`/clear` - 清空所有域名

🔍 **监控控制**:
`/check` - 立即执行域名检查
`/reload` - 重新加载配置文件
`/stop` - 停止监控服务

⚙️ **配置管理**:
`/config` - 显示当前配置
`/interval 10` - 设置检查间隔(分钟)
`/timeout 15` - 设置超时时间(秒)
`/retry 3` - 设置重试次数
`/threshold 3` - 设置失败阈值
`/cooldown 30` - 设置通知冷却时间(分钟)
`/recovery` - 切换恢复通知开关
`/allsuccess` - 切换全部正常时通知开关

👥 **管理员设置**:
`/admin list` - 查看管理员列表
`/admin add 123456` - 添加管理员
`/admin remove 123456` - 删除管理员

🎯 **批量操作示例**:
`/add google.com baidu.com github.com`
`/remove site1.com site2.com`

💡 **提示**:
• 域名不需要添加 http:// 前缀
• 支持空格或逗号分隔多个域名
• 部分命令需要管理员权限"""
        
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
        
        status_text = f"""📊 **监控状态**

**监控域名数**: {len(domains)} 个
**检查间隔**: {interval} 分钟
**服务状态**: 🟢 运行中

使用 /list 查看详细域名列表
使用 /config 查看完整配置"""
        
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
        
        domain_list = "\n".join([f"{i+1}. `{domain}`" for i, domain in enumerate(domains)])
        text = f"""📝 **监控域名列表** ({len(domains)} 个)

{domain_list}

💡 **快速操作**:
`/add example.com` - 添加更多
`/remove example.com` - 删除域名
`/check` - 立即检查所有域名"""
        
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
            await self.send_message("🔍 开始执行域名检查...", reply_to=msg_id)
            asyncio.create_task(self.check_callback())
        else:
            await self.send_message("❌ 检查功能未就绪", reply_to=msg_id)
    
    async def cmd_show_config(self, args: str, msg_id: int, user_id: int, username: str):
        """显示配置命令"""
        summary = self.config_manager.get_config_summary()
        await self.send_message(summary, reply_to=msg_id)
    
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
        """停止监控"""
        if self.stop_callback:
            await self.send_message("⏹️ 正在停止监控服务...", reply_to=msg_id)
            # 调用停止回调，传递send_notification=False避免重复发送消息
            await self.stop_callback(send_notification=False)
            await self.send_message("⏹️ 监控服务已停止", reply_to=msg_id)
        else:
            await self.send_message("❌ 停止功能未就绪", reply_to=msg_id)
    
    async def cmd_restart(self, args: str, msg_id: int, user_id: int, username: str):
        """重启监控（已弃用）"""
        await self.send_message(
            "⚠️ **重启命令已更改**\n\n"
            "请使用 `/reload` 重新加载配置\n"
            "大部分配置更改无需重启即可生效",
            reply_to=msg_id
        )
    
    async def cmd_reload(self, args: str, msg_id: int, user_id: int, username: str):
        """重新加载配置"""
        if self.reload_callback:
            await self.send_message("🔄 正在重新加载配置...", reply_to=msg_id)
            await self.reload_callback()
        else:
            await self.send_message("❌ 重新加载功能未就绪", reply_to=msg_id)
    
    async def listen_for_commands(self):
        """监听命令的主循环"""
        self.logger.info("开始监听 Telegram 命令")
        
        while True:
            try:
                updates = await self.get_updates()
                for update in updates:
                    asyncio.create_task(self.process_update(update))
                
                if not updates:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"监听命令时出错: {e}")
                await asyncio.sleep(5)