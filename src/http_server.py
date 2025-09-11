#!/usr/bin/env python3
"""
HTTP API 服务器模块
提供简单的HTTP接口，支持通过API发送Telegram消息
"""

import json
import logging
import asyncio
from typing import Optional, Dict, Any
from aiohttp import web, ClientSession
import traceback
from datetime import datetime


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
                
                self.logger.info(f"HTTP API配置加载完成: {self.host}:{self.port}, 启用: {self.enabled}")
            except Exception as e:
                self.logger.warning(f"加载HTTP API配置失败，使用默认配置: {e}")
    
    def _create_app(self):
        """创建aiohttp应用"""
        app = web.Application()
        
        # 添加路由
        app.router.add_post('/sendMsg', self.handle_send_message)
        app.router.add_get('/health', self.handle_health_check)
        app.router.add_get('/status', self.handle_status)
        
        # 添加CORS中间件（如果需要）
        app.middlewares.append(self.cors_middleware)
        app.middlewares.append(self.error_middleware)
        
        return app
    
    async def cors_middleware(self, request, handler):
        """CORS中间件"""
        response = await handler(request)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    async def error_middleware(self, request, handler):
        """错误处理中间件"""
        try:
            return await handler(request)
        except Exception as e:
            self.logger.error(f"HTTP请求处理错误: {e}\n{traceback.format_exc()}")
            return web.json_response({
                "success": False,
                "error": f"服务器内部错误: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }, status=500)
    
    async def handle_send_message(self, request):
        """处理发送消息接口"""
        try:
            # 解析请求数据
            if request.content_type == 'application/json':
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
            client_ip = request.remote
            user_agent = request.headers.get('User-Agent', 'Unknown')
            self.logger.info(f"API请求 - IP: {client_ip}, UA: {user_agent}, 消息长度: {len(message)}")
            
            # 发送消息
            success = await self.telegram_bot.send_message(
                message, 
                parse_mode=parse_mode,
                disable_web_page_preview=disable_preview
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