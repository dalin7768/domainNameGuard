"""配置管理模块

该模块提供线程安全的配置文件管理功能，支持：
- JSON 配置文件的读写
- 配置项的动态修改
- 域名列表管理
- 参数验证和边界检查
"""

import json
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import logging
from datetime import datetime


class ConfigManager:
    """配置文件管理器，支持线程安全的读写操作
    
    主要功能：
    1. 自动加载和保存 JSON 配置文件
    2. 提供线程安全的配置读写接口
    3. 支持配置项的验证和边界检查
    4. 提供便捷的域名管理方法
    5. 自动备份配置文件防止损坏
    
    使用示例：
        config = ConfigManager('config.json')
        config.add_domain('https://example.com')  # 添加域名
        interval = config.get('check.interval_minutes', 30)  # 获取配置
        config.set('check.timeout_seconds', 15)  # 设置配置
    """
    
    def __init__(self, config_file: str = "config.json"):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径，默认为 config.json
        """
        self.config_file = Path(config_file)  # 转换为 Path 对象，方便路径操作
        self.config: Dict[str, Any] = {}  # 存储配置的字典
        self.lock = threading.RLock()  # 可重入锁，支持嵌套加锁
        self.logger = logging.getLogger(__name__)
        
        # 如果配置文件不存在，创建默认配置
        if not self.config_file.exists():
            self.create_default_config()
        else:
            self.load_config()
    
    def create_default_config(self) -> None:
        """创建默认配置文件"""
        default_config = {
            "telegram": {
                "bot_token": "",
                "chat_id": "",
                "admin_users": []
            },
            "check": {
                "interval_minutes": 30,
                "timeout_seconds": 10,
                "retry_count": 2,
                "retry_delay_seconds": 5
            },
            "domains": [],
            "notification": {
                "notify_on_recovery": True,
                "failure_threshold": 2,
                "cooldown_minutes": 60
            },
            "logging": {
                "level": "INFO",
                "file": "domain_monitor.log",
                "max_size_mb": 10,
                "backup_count": 5
            }
        }
        self.config = default_config
        self.save_config()
        self.logger.info("创建默认配置文件")
    
    def load_config(self) -> bool:
        """从文件加载配置
        
        线程安全地读取 JSON 配置文件，支持 UTF-8 编码
        
        Returns:
            bool: 加载成功返回 True，失败返回 False
        """
        with self.lock:  # 加锁确保线程安全
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                # 添加详细日志
                domain_count = len(self.config.get('domains', []))
                self.logger.info(f"成功加载配置文件，包含 {domain_count} 个域名")
                return True
            except json.JSONDecodeError as e:
                # JSON 格式错误，可能是文件损坏或格式不正确
                self.logger.error(f"配置文件格式错误: {e}")
                return False
            except Exception as e:
                # 其他错误，如文件不存在、权限问题等
                self.logger.error(f"加载配置文件失败: {e}")
                return False
    
    def save_config(self) -> bool:
        """保存配置到文件
        
        保存前会创建备份文件，防止写入失败导致配置丢失
        使用原子操作确保数据完整性
        
        Returns:
            bool: 保存成功返回 True，失败返回 False
        """
        with self.lock:
            try:
                # 步骤1：如果原文件存在，先重命名为备份文件
                if self.config_file.exists():
                    backup_file = self.config_file.with_suffix('.json.bak')
                    self.config_file.rename(backup_file)
                
                # 步骤2：写入新配置文件
                # indent=2 美化输出，ensure_ascii=False 支持中文
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                
                # 步骤3：写入成功后删除备份文件
                backup_file = self.config_file.with_suffix('.json.bak')
                if backup_file.exists():
                    backup_file.unlink()
                
                self.logger.info("配置文件已保存")
                return True
            except Exception as e:
                self.logger.error(f"保存配置文件失败: {e}")
                # 步骤4：如果保存失败，从备份恢复
                backup_file = self.config_file.with_suffix('.json.bak')
                if backup_file.exists():
                    backup_file.rename(self.config_file)
                    self.logger.info("已从备份恢复配置文件")
                return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项的值
        
        支持使用点号访问嵌套配置，例如 'telegram.bot_token'
        
        Args:
            key: 配置键，支持点号分隔的路径
            default: 找不到配置时的默认值
            
        Returns:
            配置值，如果不存在则返回默认值
            
        Example:
            token = config.get('telegram.bot_token')
            interval = config.get('check.interval_minutes', 30)
        """
        with self.lock:
            # 将点号路径分割成键列表
            keys = key.split('.')
            value = self.config
            # 逐层访问嵌套字典
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置项的值
        
        支持设置嵌套配置，会自动创建不存在的中间节点
        设置后会自动保存到文件
        
        Args:
            key: 配置键，支持点号分隔的路径
            value: 要设置的值
            
        Returns:
            bool: 设置成功返回 True，失败返回 False
            
        Example:
            config.set('check.interval_minutes', 10)
            config.set('telegram.admin_users', [123456])
        """
        with self.lock:
            try:
                keys = key.split('.')
                target = self.config
                # 导航到父节点，如果不存在则创建
                for k in keys[:-1]:
                    if k not in target:
                        target[k] = {}
                    target = target[k]
                # 设置最终值
                target[keys[-1]] = value
                # 保存到文件
                return self.save_config()
            except Exception as e:
                self.logger.error(f"设置配置项失败: {e}")
                return False
    
    # 域名管理方法
    def get_domains(self) -> List[str]:
        """获取所有域名"""
        with self.lock:
            return self.config.get('domains', []).copy()
    
    def add_domain(self, url: str) -> Tuple[bool, str]:
        """添加要监控的域名
        
        支持添加纯域名，不需要 http:// 前缀
        
        Args:
            url: 要添加的域名（可以不带协议）
            
        Returns:
            Tuple[bool, str]: (是否成功, 结果消息)
        """
        with self.lock:
            domains = self.config.get('domains', [])
            
            # 去除空格
            url = url.strip()
            
            # 检查是否已存在（忽略协议前缀）
            for domain in domains:
                if domain == url or domain.replace('https://', '').replace('http://', '') == url:
                    return False, f"域名 {url} 已存在"
            
            domains.append(url)
            self.config['domains'] = domains
            
            if self.save_config():
                return True, f"✅ 成功添加: {url}"
            else:
                return False, "保存配置失败"
    
    def remove_domain(self, url: str) -> Tuple[bool, str]:
        """删除监控的域名
        
        Args:
            url: 要删除的域名（可以不带协议）
            
        Returns:
            Tuple[bool, str]: (是否成功, 结果消息)
        """
        with self.lock:
            domains = self.config.get('domains', [])
            url = url.strip()
            
            # 尝试匹配（忽略协议）
            found = None
            for domain in domains:
                if domain == url or domain.replace('https://', '').replace('http://', '') == url:
                    found = domain
                    break
            
            if not found:
                return False, f"域名 {url} 不存在"
            
            domains.remove(found)
            self.config['domains'] = domains
            
            if self.save_config():
                return True, f"❌ 已删除: {url}"
            else:
                return False, "保存配置失败"
    
    def clear_domains(self) -> tuple[bool, str]:
        """清空所有域名"""
        with self.lock:
            count = len(self.config.get('domains', []))
            self.config['domains'] = []
            
            if self.save_config():
                return True, f"已清空 {count} 个域名"
            else:
                return False, "保存配置失败"
    
    # 检查配置管理
    def set_interval(self, minutes: int) -> Tuple[bool, str]:
        """设置域名检查间隔时间
        
        包含参数验证，确保间隔在合理范围内
        
        Args:
            minutes: 间隔时间（分钟），范围 1-1440
            
        Returns:
            Tuple[bool, str]: (是否成功, 结果消息)
        """
        with self.lock:
            # 验证最小值
            if minutes < 1:
                return False, "检查间隔不能小于 1 分钟"
            # 验证最大值（24小时）
            if minutes > 1440:
                return False, "检查间隔不能大于 1440 分钟（24小时）"
            
            self.config['check']['interval_minutes'] = minutes
            
            if self.save_config():
                return True, f"检查间隔已设置为 {minutes} 分钟"
            else:
                return False, "保存配置失败"
    
    def set_timeout(self, seconds: int) -> tuple[bool, str]:
        """设置超时时间"""
        with self.lock:
            if seconds < 1:
                return False, "超时时间不能小于 1 秒"
            if seconds > 300:
                return False, "超时时间不能大于 300 秒"
            
            self.config['check']['timeout_seconds'] = seconds
            
            if self.save_config():
                return True, f"超时时间已设置为 {seconds} 秒"
            else:
                return False, "保存配置失败"
    
    def set_retry(self, count: int) -> tuple[bool, str]:
        """设置重试次数"""
        with self.lock:
            if count < 0:
                return False, "重试次数不能为负数"
            if count > 10:
                return False, "重试次数不能大于 10"
            
            self.config['check']['retry_count'] = count
            
            if self.save_config():
                return True, f"重试次数已设置为 {count}"
            else:
                return False, "保存配置失败"
    
    # 通知配置管理
    def set_failure_threshold(self, threshold: int) -> tuple[bool, str]:
        """设置失败阈值"""
        with self.lock:
            if threshold < 1:
                return False, "失败阈值不能小于 1"
            if threshold > 100:
                return False, "失败阈值不能大于 100"
            
            self.config['notification']['failure_threshold'] = threshold
            
            if self.save_config():
                return True, f"失败阈值已设置为 {threshold}"
            else:
                return False, "保存配置失败"
    
    def set_cooldown(self, minutes: int) -> tuple[bool, str]:
        """设置冷却时间"""
        with self.lock:
            if minutes < 0:
                return False, "冷却时间不能为负数"
            if minutes > 1440:
                return False, "冷却时间不能大于 1440 分钟（24小时）"
            
            self.config['notification']['cooldown_minutes'] = minutes
            
            if self.save_config():
                return True, f"冷却时间已设置为 {minutes} 分钟"
            else:
                return False, "保存配置失败"
    
    def toggle_recovery_notification(self) -> tuple[bool, str]:
        """切换恢复通知开关"""
        with self.lock:
            current = self.config['notification'].get('notify_on_recovery', True)
            self.config['notification']['notify_on_recovery'] = not current
            
            if self.save_config():
                status = "开启" if not current else "关闭"
                return True, f"恢复通知已{status}"
            else:
                return False, "保存配置失败"
    
    def toggle_all_success_notification(self) -> Tuple[bool, str]:
        """切换全部正常时通知开关"""
        with self.lock:
            current = self.config['notification'].get('notify_on_all_success', False)
            self.config['notification']['notify_on_all_success'] = not current
            
            if self.save_config():
                status = "开启" if not current else "关闭"
                return True, f"全部正常通知已{status}"
            else:
                return False, "保存配置失败"
    
    # 管理员管理
    def add_admin(self, user_id: int) -> tuple[bool, str]:
        """添加管理员（已弃用，使用 add_admin_by_username）"""
        return self.add_admin_by_username(str(user_id))
    
    def remove_admin(self, user_id: int) -> tuple[bool, str]:
        """移除管理员（已弃用，使用 remove_admin_by_username）"""
        return self.remove_admin_by_username(str(user_id))
    
    def add_admin_by_username(self, username: str) -> tuple[bool, str]:
        """添加管理员（通过用户名）
        
        Args:
            username: Telegram 用户名，可带或不带@前缀
            
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        with self.lock:
            admins = self.config['telegram'].get('admin_users', [])
            
            # 标准化用户名格式（添加@前缀）
            if username and not username.startswith('@'):
                username = f"@{username}"
            
            if username in admins:
                return False, f"用户 {username} 已是管理员"
            
            admins.append(username)
            self.config['telegram']['admin_users'] = admins
            
            if self.save_config():
                return True, f"成功添加管理员: {username}"
            else:
                return False, "保存配置失败"
    
    def remove_admin_by_username(self, username: str) -> tuple[bool, str]:
        """移除管理员（通过用户名）
        
        Args:
            username: Telegram 用户名，可带或不带@前缀
            
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        with self.lock:
            admins = self.config['telegram'].get('admin_users', [])
            
            # 尝试两种格式
            username_with_at = f"@{username}" if not username.startswith('@') else username
            username_without_at = username[1:] if username.startswith('@') else username
            
            removed = False
            if username_with_at in admins:
                admins.remove(username_with_at)
                removed = True
            elif username_without_at in admins:
                admins.remove(username_without_at)
                removed = True
            elif username in admins:
                admins.remove(username)
                removed = True
            
            if not removed:
                return False, f"用户 {username} 不是管理员"
            
            self.config['telegram']['admin_users'] = admins
            
            if self.save_config():
                return True, f"成功移除管理员: {username}"
            else:
                return False, "保存配置失败"
    
    def is_admin(self, user_id: int) -> bool:
        """检查用户是否为管理员（已弃用，保留兼容性）
        
        Args:
            user_id: Telegram 用户 ID
            
        Returns:
            bool: 是管理员返回 True
        """
        with self.lock:
            admins = self.config['telegram'].get('admin_users', [])
            # 兼容旧配置（数字ID）
            return user_id in admins or len(admins) == 0
    
    def is_admin_by_username(self, username: str) -> bool:
        """检查用户是否为管理员（通过用户名）
        
        如果没有设置任何管理员，则所有人都有权限
        这样在初始配置时不会被锁定
        
        Args:
            username: Telegram 用户名（不带@）
            
        Returns:
            bool: 是管理员返回 True
        """
        with self.lock:
            admins = self.config['telegram'].get('admin_users', [])
            # 重要：如果管理员列表为空，所有人都可以操作
            # 避免配置错误导致无人可以管理
            if len(admins) == 0:
                return True
            
            # 支持带@和不带@的用户名
            if username:
                # 添加@前缀进行比较（如果用户名没有@）
                username_with_at = f"@{username}" if not username.startswith('@') else username
                username_without_at = username[1:] if username.startswith('@') else username
                
                # 检查两种格式
                return username_with_at in admins or username_without_at in admins or username in admins
            
            return False
    
    def get_config_summary(self) -> str:
        """生成配置摘要信息
        
        用于在 Telegram 中展示当前配置状态
        
        Returns:
            str: Markdown 格式的配置摘要
        """
        with self.lock:
            domains_count = len(self.config.get('domains', []))
            interval = self.config['check']['interval_minutes']
            timeout = self.config['check']['timeout_seconds']
            retry = self.config['check']['retry_count']
            concurrent = self.config['check'].get('max_concurrent', 10)
            auto_adjust = "开启" if self.config['check'].get('auto_adjust_concurrent', True) else "关闭"
            threshold = self.config['notification']['failure_threshold']
            cooldown = self.config['notification']['cooldown_minutes']
            recovery = "开启" if self.config['notification']['notify_on_recovery'] else "关闭"
            all_success = "开启" if self.config['notification'].get('notify_on_all_success', False) else "关闭"
            admins_count = len(self.config['telegram'].get('admin_users', []))
            
            summary = f"""📊 **当前配置**

🌐 **监控域名**: {domains_count} 个
⏰ **检查间隔**: {interval} 分钟
⏱️ **超时时间**: {timeout} 秒
🔁 **重试次数**: {retry} 次
⚡ **并发线程**: {concurrent} 个
🎯 **自适应并发**: {auto_adjust}
⚠️ **失败阈值**: {threshold} 次
❄️ **冷却时间**: {cooldown} 分钟
✅ **恢复通知**: {recovery}
📢 **全正常通知**: {all_success}
👥 **管理员数**: {admins_count} 人"""
            
            return summary