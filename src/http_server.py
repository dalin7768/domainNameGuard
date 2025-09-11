#!/usr/bin/env python3
"""
HTTP API 服务器模块
提供简单的HTTP接口，支持通过API发送Telegram消息
"""

import json
import logging
import asyncio
import time
import ipaddress
from typing import Optional, Dict, Any, List
from aiohttp import web, ClientSession
import traceback
from datetime import datetime, timedelta
from collections import defaultdict


class HttpApiServer:
    """HTTP API 服务器"""
    
    def __init__(self, config_manager=None, telegram_bot=None):
        """
        初始化HTTP API服务器
        
        Args:
            config_manager: 配置管理器实例
            telegram_bot: Telegram机器人实例
        """
        self.config_manager = config_manager
        self.telegram_bot = telegram_bot
        self.logger = logging.getLogger(__name__)
        self.app = None
        self.runner = None
        self.site = None
        
        # 服务器配置
        self.host = "127.0.0.1"
        self.port = 8080
        self.enabled = False
        self.cors_enabled = True
        self.allowed_ips = []
        self.auth_enabled = False
        self.api_key = ""
        self.rate_limit_enabled = False
        self.requests_per_minute = 60
        
        # 频率限制存储
        self.request_counts = defaultdict(list)
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """加载HTTP服务器配置"""
        if self.config_manager:
            try:
                http_config = self.config_manager.config.get("http_api", {})
                self.host = http_config.get("host", "127.0.0.1")
                self.port = http_config.get("port", 8080)
                self.enabled = http_config.get("enabled", False)
                self.cors_enabled = http_config.get("cors_enabled", True)
                self.allowed_ips = http_config.get("allowed_ips", [])
                
                # 认证配置
                auth_config = http_config.get("auth", {})
                self.auth_enabled = auth_config.get("enabled", False)
                self.api_key = auth_config.get("api_key", "")
                
                # 频率限制配置
                rate_config = http_config.get("rate_limit", {})
                self.rate_limit_enabled = rate_config.get("enabled", False)
                self.requests_per_minute = rate_config.get("requests_per_minute", 60)
                
                self.logger.info(f"HTTP API配置加载完成: {self.host}:{self.port}, 启用: {self.enabled}")
                if self.allowed_ips:
                    self.logger.info(f"IP白名单: {self.allowed_ips}")
                if self.auth_enabled:
                    self.logger.info("API密钥认证已启用")
                if self.rate_limit_enabled:
                    self.logger.info(f"频率限制已启用: {self.requests_per_minute}/分钟")
                    
            except Exception as e:
                self.logger.warning(f"加载HTTP API配置失败，使用默认配置: {e}")
    
    def _create_app(self):
        """创建aiohttp应用"""
        app = web.Application()
        
        # 添加路由
        app.router.add_post('/sendMsg', self.handle_send_message)
        app.router.add_get('/health', self.handle_health_check)
        app.router.add_get('/status', self.handle_status)
        
        # 添加中间件（使用装饰器包装）
        app.middlewares.append(self._make_error_middleware())
        app.middlewares.append(self._make_cors_middleware())
        app.middlewares.append(self._make_security_middleware())
        
        return app
    
    def _is_ip_allowed(self, ip: str) -> bool:
        """检查IP是否在白名单中"""
        if not self.allowed_ips:
            return True  # 空白名单表示允许所有IP
        
        try:
            client_ip = ipaddress.ip_address(ip)
            for allowed in self.allowed_ips:
                if '/' in allowed:  # CIDR格式
                    if client_ip in ipaddress.ip_network(allowed, strict=False):
                        return True
                else:  # 单个IP
                    if client_ip == ipaddress.ip_address(allowed):
                        return True
            return False
        except (ipaddress.AddressValueError, ValueError):
            self.logger.warning(f"无效的IP地址: {ip}")
            return False
    
    def _is_rate_limited(self, ip: str) -> bool:
        """检查IP是否超过频率限制"""
        if not self.rate_limit_enabled:
            return False
        
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # 清理过期的请求记录
        self.request_counts[ip] = [
            req_time for req_time in self.request_counts[ip] 
            if req_time > minute_ago
        ]
        
        # 检查当前分钟的请求数
        if len(self.request_counts[ip]) >= self.requests_per_minute:
            return True
        
        # 记录当前请求
        self.request_counts[ip].append(now)
        return False
    
    def _is_authenticated(self, request) -> bool:
        """检查API密钥认证"""
        if not self.auth_enabled:
            return True
        
        # 检查Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            return token == self.api_key
        
        # 检查X-API-Key header
        api_key_header = request.headers.get('X-API-Key', '')
        if api_key_header == self.api_key:
            return True
        
        # 检查查询参数
        api_key_param = request.query.get('api_key', '')
        if api_key_param == self.api_key:
            return True
        
        return False
    
    def _get_client_ip(self, request) -> str:
        """获取客户端IP地址"""
        # 首先检查X-Forwarded-For头（代理情况）
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            # 取第一个IP（原始客户端IP）
            return forwarded_for.split(',')[0].strip()
        
        # 检查X-Real-IP头
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip.strip()
        
        # 最后从transport获取peername
        try:
            if hasattr(request, 'transport') and request.transport:
                peername = request.transport.get_extra_info('peername')
                if peername:
                    return peername[0]
        except Exception:
            pass
        
        # 如果都获取不到，返回默认值
        return '127.0.0.1'
    
    async def handle_send_message(self, request):
        """处理发送消息接口"""
        try:
            # 解析请求数据
            content_type = request.headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                data = await request.json()
            else:
                data = await request.post()
                data = dict(data)
            
            # 验证必要参数
            if 'msg' not in data:
                return web.json_response({
                    "success": False,
                    "error": "缺少必要参数: msg",
                    "timestamp": datetime.now().isoformat()
                }, status=400)
            
            message = data['msg']
            if not message or not isinstance(message, str):
                return web.json_response({
                    "success": False,
                    "error": "消息内容不能为空且必须为字符串",
                    "timestamp": datetime.now().isoformat()
                }, status=400)
            
            # 可选参数
            parse_mode = data.get('parse_mode', 'Markdown')
            disable_preview = data.get('disable_preview', True)
            
            # 发送Telegram消息
            if not self.telegram_bot:
                return web.json_response({
                    "success": False,
                    "error": "Telegram机器人未初始化",
                    "timestamp": datetime.now().isoformat()
                }, status=503)
            
            # 记录API请求
            client_ip = self._get_client_ip(request)
            user_agent = request.headers.get('User-Agent', 'Unknown')
            self.logger.info(f"API请求 - IP: {client_ip}, UA: {user_agent}, 消息长度: {len(message)}")
            
            # 发送消息（TelegramBot.send_message只支持text和parse_mode参数）
            success = await self.telegram_bot.send_message(
                message, 
                parse_mode=parse_mode
            )
            
            if success:
                return web.json_response({
                    "success": True,
                    "message": "消息发送成功",
                    "msg_length": len(message),
                    "timestamp": datetime.now().isoformat()
                })
            else:
                return web.json_response({
                    "success": False,
                    "error": "Telegram消息发送失败",
                    "timestamp": datetime.now().isoformat()
                }, status=500)
                
        except json.JSONDecodeError:
            return web.json_response({
                "success": False,
                "error": "JSON格式错误",
                "timestamp": datetime.now().isoformat()
            }, status=400)
        except Exception as e:
            self.logger.error(f"发送消息接口错误: {e}\n{traceback.format_exc()}")
            return web.json_response({
                "success": False,
                "error": f"处理请求时发生错误: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }, status=500)
    
    async def handle_health_check(self, request):
        """健康检查接口"""
        return web.json_response({
            "status": "healthy",
            "service": "Domain Monitor HTTP API",
            "timestamp": datetime.now().isoformat(),
            "telegram_bot": "connected" if self.telegram_bot else "disconnected"
        })
    
    async def handle_status(self, request):
        """状态查询接口"""
        try:
            # 获取基本状态信息
            status_info = {
                "service": "Domain Monitor HTTP API",
                "status": "running",
                "host": self.host,
                "port": self.port,
                "timestamp": datetime.now().isoformat(),
                "telegram_bot": {
                    "connected": bool(self.telegram_bot),
                    "chat_id": getattr(self.telegram_bot, 'chat_id', None) if self.telegram_bot else None
                }
            }
            
            # 如果有配置管理器，添加更多状态信息
            if self.config_manager:
                status_info["config"] = {
                    "domains_count": len(self.config_manager.get_domains()),
                    "notification_level": self.config_manager.get('notification.level', 'unknown')
                }
            
            return web.json_response(status_info)
            
        except Exception as e:
            self.logger.error(f"获取状态信息错误: {e}")
            return web.json_response({
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, status=500)
    
    async def start_server(self):
        """启动HTTP服务器"""
        if not self.enabled:
            self.logger.info("HTTP API服务器已禁用")
            return False
        
        try:
            self.app = self._create_app()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            self.logger.info(f"HTTP API服务器启动成功: http://{self.host}:{self.port}")
            self.logger.info(f"可用接口:")
            self.logger.info(f"  POST /sendMsg - 发送Telegram消息")
            self.logger.info(f"  GET  /health - 健康检查")
            self.logger.info(f"  GET  /status - 状态查询")
            
            return True
            
        except Exception as e:
            self.logger.error(f"启动HTTP API服务器失败: {e}")
            return False
    
    async def stop_server(self):
        """停止HTTP服务器"""
        try:
            if self.site:
                await self.site.stop()
                self.logger.info("HTTP API服务器已停止")
            
            if self.runner:
                await self.runner.cleanup()
                
        except Exception as e:
            self.logger.error(f"停止HTTP API服务器错误: {e}")
    
    def _make_security_middleware(self):
        """创建安全中间件包装器"""
        @web.middleware
        async def security_middleware(request, handler):
            client_ip = self._get_client_ip(request)
            
            # IP白名单检查
            if not self._is_ip_allowed(client_ip):
                self.logger.warning(f"IP {client_ip} 不在白名单中，拒绝访问")
                return web.json_response({
                    "success": False,
                    "error": "访问被拒绝",
                    "timestamp": datetime.now().isoformat()
                }, status=403)
            
            # 频率限制检查
            if self._is_rate_limited(client_ip):
                self.logger.warning(f"IP {client_ip} 超过频率限制")
                return web.json_response({
                    "success": False,
                    "error": "请求过于频繁，请稍后再试",
                    "timestamp": datetime.now().isoformat()
                }, status=429)
            
            # API密钥认证检查
            if not self._is_authenticated(request):
                self.logger.warning(f"IP {client_ip} 认证失败")
                return web.json_response({
                    "success": False,
                    "error": "认证失败",
                    "timestamp": datetime.now().isoformat()
                }, status=401)
            
            return await handler(request)
        
        return security_middleware
    
    def _make_cors_middleware(self):
        """创建CORS中间件包装器"""
        @web.middleware
        async def cors_middleware(request, handler):
            # 处理OPTIONS预检请求
            if request.method == 'OPTIONS':
                response = web.Response()
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
                response.headers['Access-Control-Max-Age'] = '86400'
                return response
            
            # 调用下一个处理器
            response = await handler(request)
            
            # 添加CORS头到响应
            if hasattr(response, 'headers'):
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
            
            return response
        
        return cors_middleware
    
    def _make_error_middleware(self):
        """创建错误处理中间件包装器"""
        @web.middleware
        async def error_middleware(request, handler):
            try:
                return await handler(request)
            except Exception as e:
                self.logger.error(f"HTTP请求处理错误: {e}\n{traceback.format_exc()}")
                return web.json_response({
                    "success": False,
                    "error": f"服务器内部错误: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }, status=500)
        
        return error_middleware


# 使用示例和测试
async def test_api_server():
    """测试HTTP API服务器"""
    # 模拟配置
    class MockConfig:
        def __init__(self):
            self.config = {
                "http_api": {
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": 8080
                }
            }
        
        def get(self, key, default=None):
            return self.config.get(key, default)
    
    # 模拟Telegram Bot
    class MockTelegramBot:
        def __init__(self):
            self.chat_id = "-1001234567890"
        
        async def send_message(self, text, parse_mode="Markdown", disable_web_page_preview=True):
            print(f"[模拟发送] {text}")
            return True
    
    # 创建并启动服务器
    config = MockConfig()
    bot = MockTelegramBot()
    server = HttpApiServer(config, bot)
    
    # 启动服务器
    await server.start_server()
    
    # 测试请求
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            # 测试发送消息
            test_data = {"msg": "Hello from API!"}
            async with session.post('http://127.0.0.1:8080/sendMsg', json=test_data) as resp:
                result = await resp.json()
                print(f"发送消息响应: {result}")
            
            # 测试健康检查
            async with session.get('http://127.0.0.1:8080/health') as resp:
                result = await resp.json()
                print(f"健康检查响应: {result}")
    
    except Exception as e:
        print(f"测试请求错误: {e}")
    
    # 停止服务器
    await server.stop_server()


if __name__ == "__main__":
    # 运行测试
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_api_server())