import httpx
import asyncio
from typing import Dict, List, Tuple, Optional, AsyncGenerator
from datetime import datetime
import socket
import logging
from dataclasses import dataclass
from enum import Enum
import gc
import websockets
import ssl

# 尝试导入psutil，如果没有安装则禁用自适应功能
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class CheckStatus(Enum):
    """检查状态枚举"""

    SUCCESS = "success"
    DNS_ERROR = "dns_error"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    SSL_ERROR = "ssl_error"
    WEBSOCKET_ERROR = "websocket_error"
    PHISHING_WARNING = "phishing_warning"
    SECURITY_WARNING = "security_warning"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class CheckResult:
    """检查结果数据类"""

    domain_name: str
    url: str
    status: CheckStatus
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    response_time: Optional[float] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_success(self) -> bool:
        return self.status == CheckStatus.SUCCESS

    def get_error_description(self) -> str:
        """获取错误的详细描述"""
        error_descriptions = {
            CheckStatus.DNS_ERROR: "DNS 解析失败：无法解析域名地址",
            CheckStatus.CONNECTION_ERROR: "连接错误：无法建立与服务器的连接",
            CheckStatus.TIMEOUT: f"请求超时：服务器响应时间过长",
            CheckStatus.HTTP_ERROR: self._get_http_error_description(),
            CheckStatus.SSL_ERROR: "SSL 证书错误：证书验证失败或已过期",
            CheckStatus.WEBSOCKET_ERROR: "WebSocket 连接失败：无法建立 WebSocket 连接",
            CheckStatus.PHISHING_WARNING: "⚠️ 安全警告：该网站可能是钓鱼网站或存在安全风险",
            CheckStatus.SECURITY_WARNING: "⚠️ 浏览器安全警告：该网站被标记为不安全（可能被Google等浏览器拦截）",
            CheckStatus.UNKNOWN_ERROR: "未知错误：请检查日志了解详情",
        }

        base_desc = error_descriptions.get(self.status, "未知错误")
        if self.error_message:
            return f"{base_desc}\n详细信息：{self.error_message}"
        return base_desc

    def _get_http_error_description(self) -> str:
        """根据HTTP状态码返回详细错误描述"""
        if not self.status_code:
            return "HTTP 错误：未知状态码"

        # 详细的HTTP错误映射
        http_errors = {
            400: "错误请求（400）：服务器无法理解请求",
            401: "未授权（401）：需要身份验证",
            403: "禁止访问（403）：服务器拒绝请求",
            404: "页面不存在（404）：请求的资源未找到",
            405: "方法不允许（405）：请求方法不被允许",
            408: "请求超时（408）：服务器等待请求超时",
            429: "请求过多（429）：触发了速率限制",
            500: "服务器内部错误（500）：服务器遇到错误",
            502: "网关错误（502）：上游服务器错误响应",
            503: "服务不可用（503）：服务器暂时无法处理请求",
            504: "网关超时（504）：上游服务器响应超时",
            520: "Web服务器返回未知错误（520）：源站返回空响应",
            521: "Web服务器宕机（521）：源站拒绝连接",
            522: "连接超时（522）：无法连接到源站服务器",
            523: "源站不可达（523）：无法到达源站服务器",
            524: "超时发生（524）：与源站建立连接但未收到响应",
            525: "SSL握手失败（525）：无法与源站协商SSL/TLS连接",
            526: "无效的SSL证书（526）：源站SSL证书无效",
        }

        # 检查特定的安全相关状态码
        if self.status_code == 451:
            return "法律原因不可用（451）：由于法律原因该内容不可用（可能涉及版权或地区限制）"

        # 返回对应的错误描述或通用描述
        return http_errors.get(
            self.status_code,
            f"HTTP 错误（{self.status_code}）：{'客户端错误' if 400 <= self.status_code < 500 else '服务器错误' if 500 <= self.status_code < 600 else '未知错误'}",
        )


class DomainChecker:
    """域名检测器类"""

    def __init__(
        self,
        timeout: int = 10,
        retry_count: int = 2,
        retry_delay: int = 5,
        max_concurrent: int = 10,
        auto_adjust: bool = True,
    ):
        """
        初始化域名检测器

        Args:
            timeout: 请求超时时间（秒）
            retry_count: 重试次数
            retry_delay: 重试延迟（秒）
            max_concurrent: 最大并发数
            auto_adjust: 是否自动调整并发数
        """
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.max_concurrent = max_concurrent
        self.initial_concurrent = max_concurrent  # 保存初始值
        self.auto_adjust = auto_adjust
        self.logger = logging.getLogger(__name__)

        # 存储域名的上次状态，用于判断是否恢复
        # 使用LRU缓存避免无限增长
        self.last_status: Dict[str, bool] = {}
        self.max_status_cache = 1000  # 最多缓存1000个域名状态

        # HTTP连接池，复用连接以提高性能
        self._client: Optional[httpx.AsyncClient] = None
        self._client_no_verify: Optional[httpx.AsyncClient] = None  # 不验证SSL的客户端
        self._client_lock = asyncio.Lock()

        # 性能统计
        self.last_check_duration = 0  # 上次检查耗时
        self.avg_response_time = 0  # 平均响应时间

        # 自适应控制参数
        self.performance_history = []  # 记录历史性能
        self.last_adjustment_time = datetime.now()

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建HTTP客户端（连接池复用）"""
        async with self._client_lock:
            if self._client is None:
                # 检查是否支持HTTP/2
                try:
                    import h2

                    http2_support = True
                except ImportError:
                    http2_support = False
                    self.logger.warning(
                        "HTTP/2 不可用，使用 HTTP/1.1（安装 pip install httpx[http2] 以启用）"
                    )

                # 创建支持连接复用的客户端
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout),
                    follow_redirects=True,
                    verify=True,
                    http2=http2_support,  # 根据是否安装h2包决定
                    limits=httpx.Limits(
                        max_keepalive_connections=self.max_concurrent,
                        max_connections=self.max_concurrent * 2,
                        keepalive_expiry=30,  # 连接保持30秒
                    ),
                )
                self.logger.info(
                    f"创建HTTP连接池，最大连接数: {self.max_concurrent}，HTTP/2: {http2_support}"
                )
            return self._client

    async def _get_client_no_verify(self) -> httpx.AsyncClient:
        """获取不验证SSL的HTTP客户端（用于降级后的请求）"""
        async with self._client_lock:
            if self._client_no_verify is None:
                # 创建不验证SSL的客户端
                self._client_no_verify = httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout),
                    follow_redirects=True,
                    verify=False,  # 不验证SSL证书
                    http2=False,  # 降级请求不使用HTTP/2
                    limits=httpx.Limits(
                        max_keepalive_connections=self.max_concurrent,
                        max_connections=self.max_concurrent * 2,
                        keepalive_expiry=30,
                    ),
                )
                self.logger.info("创建不验证SSL的HTTP连接池")
            return self._client_no_verify

    async def close_client(self):
        """关闭HTTP客户端"""
        async with self._client_lock:
            if self._client:
                await self._client.aclose()
                self._client = None
                self.logger.info("HTTP连接池已关闭")
            if self._client_no_verify:
                await self._client_no_verify.aclose()
                self._client_no_verify = None
                self.logger.info("不验证SSL的HTTP连接池已关闭")

    def _adjust_concurrent_by_resources(self) -> int:
        """根据系统资源自动调整并发数"""
        if not self.auto_adjust:
            return self.max_concurrent

        # 如果psutil未安装，跳过自适应
        if not PSUTIL_AVAILABLE:
            return self.max_concurrent

        try:
            # 获取系统资源状态
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent

            # 计算建议的并发数
            suggested_concurrent = self.initial_concurrent

            # CPU 使用率调整
            if cpu_percent > 80:
                # CPU 高负载，减少并发
                suggested_concurrent = max(1, int(self.initial_concurrent * 0.5))
                self.logger.warning(
                    f"CPU 使用率 {cpu_percent:.1f}%，降低并发数到 {suggested_concurrent}"
                )
            elif cpu_percent > 60:
                # CPU 中等负载
                suggested_concurrent = max(2, int(self.initial_concurrent * 0.7))
            elif cpu_percent < 30:
                # CPU 低负载，可以增加并发
                suggested_concurrent = min(self.initial_concurrent * 2, 200)

            # 内存使用率调整
            if memory_percent > 85:
                # 内存紧张，减少并发
                suggested_concurrent = min(
                    suggested_concurrent, max(1, int(self.initial_concurrent * 0.3))
                )
                self.logger.warning(
                    f"内存使用率 {memory_percent:.1f}%，限制并发数到 {suggested_concurrent}"
                )
            elif memory_percent > 70:
                suggested_concurrent = min(
                    suggested_concurrent, max(2, int(self.initial_concurrent * 0.6))
                )

            # 根据历史性能调整
            if len(self.performance_history) >= 3:
                # 计算最近3次的平均响应时间
                recent_avg = sum(self.performance_history[-3:]) / 3
                if recent_avg > self.timeout * 0.8:
                    # 响应时间接近超时，减少并发
                    suggested_concurrent = max(1, int(suggested_concurrent * 0.7))
                    self.logger.info(
                        f"平均响应时间 {recent_avg:.1f}秒，接近超时，减少并发"
                    )

            # 确保在合理范围内
            suggested_concurrent = max(1, min(suggested_concurrent, 200))

            # 如果变化超过20%，才真正调整
            if (
                abs(suggested_concurrent - self.max_concurrent) / self.max_concurrent
                > 0.2
            ):
                old_concurrent = self.max_concurrent
                self.max_concurrent = suggested_concurrent
                self.logger.info(
                    f"自动调整并发数: {old_concurrent} -> {suggested_concurrent} (CPU:{cpu_percent:.1f}%, MEM:{memory_percent:.1f}%)"
                )

                # 需要重建连接池
                asyncio.create_task(self.close_client())

            return self.max_concurrent

        except Exception as e:
            self.logger.error(f"自适应并发调整失败: {e}")
            return self.max_concurrent

    async def _check_websocket(self, url: str, timeout: int = 10) -> CheckResult:
        """
        检查WebSocket连接

        Args:
            url: WebSocket URL (wss://...)
            timeout: 超时时间

        Returns:
            CheckResult: 检查结果
        """
        # 从URL中提取域名
        from urllib.parse import urlparse

        parsed = urlparse(url)
        name = parsed.netloc or url

        start_time = datetime.now()

        try:
            # 创建SSL上下文（用于wss连接）
            ssl_context = ssl.create_default_context()

            # 尝试建立WebSocket连接
            async with asyncio.timeout(timeout):
                async with websockets.connect(
                    url,
                    ssl=ssl_context if url.startswith("wss") else None,
                    close_timeout=1,
                ) as websocket:
                    # 连接成功
                    response_time = (datetime.now() - start_time).total_seconds()
                    self.logger.info(f"WebSocket域名 {name} ({url}) 连接成功")
                    return CheckResult(
                        domain_name=name,
                        url=url,
                        status=CheckStatus.SUCCESS,
                        response_time=response_time,
                    )

        except asyncio.TimeoutError:
            self.logger.error(f"WebSocket域名 {name} ({url}) 连接超时")
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.TIMEOUT,
                error_message=f"WebSocket连接超时（{timeout}秒）",
            )

        except websockets.exceptions.InvalidURI:
            self.logger.error(f"WebSocket域名 {name} ({url}) URL格式无效")
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.WEBSOCKET_ERROR,
                error_message="无效的WebSocket URL格式",
            )

        except websockets.exceptions.WebSocketException as e:
            self.logger.error(f"WebSocket域名 {name} ({url}) 连接失败：{e}")
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.WEBSOCKET_ERROR,
                error_message=str(e),
            )

        except ssl.SSLError as e:
            self.logger.error(f"WebSocket域名 {name} ({url}) SSL错误：{e}")
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.SSL_ERROR,
                error_message=str(e),
            )

        except Exception as e:
            error_msg = str(e)
            if (
                "Name or service not known" in error_msg
                or "getaddrinfo failed" in error_msg
            ):
                status = CheckStatus.DNS_ERROR
            else:
                status = CheckStatus.WEBSOCKET_ERROR

            self.logger.error(f"WebSocket域名 {name} ({url}) 检查失败：{error_msg}")
            return CheckResult(
                domain_name=name, url=url, status=status, error_message=error_msg
            )

    def _check_for_security_issues(
        self, response: httpx.Response
    ) -> Optional[CheckStatus]:
        """
        检查响应是否包含安全问题标识

        Args:
            response: HTTP响应

        Returns:
            Optional[CheckStatus]: 如果检测到安全问题返回对应状态，否则返回None
        """
        try:
            # 检查响应头中的安全标识
            content_type = response.headers.get("content-type", "").lower()

            # 检查是否被标记为钓鱼网站（某些安全服务会在响应头中标记）
            if (
                "x-phishing-warning" in response.headers
                or "x-malware-warning" in response.headers
            ):
                return CheckStatus.PHISHING_WARNING

            # 检查响应内容（仅当content-type为html时）
            if "text/html" in content_type:
                content_lower = response.text[:5000].lower()  # 只检查前5000个字符

                # 检查Google Safe Browsing警告
                google_warnings = [
                    "deceptive site ahead",
                    "this site may harm your computer",
                    "the site ahead contains malware",
                    "phishing attack ahead",
                    "this site has been reported as unsafe",
                ]

                for warning in google_warnings:
                    if warning in content_lower:
                        self.logger.warning(f"检测到Google安全警告: {warning}")
                        return CheckStatus.SECURITY_WARNING

                # 检查其他浏览器的安全警告
                browser_warnings = [
                    "reported attack site",
                    "suspected phishing site",
                    "warning: suspected phishing",
                    "this website has been reported",
                    "dangerous site",
                    "unsafe website",
                ]

                for warning in browser_warnings:
                    if warning in content_lower:
                        self.logger.warning(f"检测到浏览器安全警告: {warning}")
                        return CheckStatus.SECURITY_WARNING

                # 检查CloudFlare等CDN的安全拦截页面
                if (
                    "blocked for security reasons" in content_lower
                    or "access denied" in content_lower
                ):
                    if (
                        "cloudflare" in content_lower
                        or "security challenge" in content_lower
                    ):
                        self.logger.warning("网站被安全服务拦截")
                        return CheckStatus.SECURITY_WARNING

        except Exception as e:
            self.logger.debug(f"安全检查时发生错误: {e}")

        return None

    async def _check_once(
        self, url: str, quick_mode: bool = False, try_http: bool = False
    ) -> CheckResult:
        """
        执行单次域名检查（不重试）

        Args:
            url: 要检查的URL或域名
            quick_mode: 快速模式
            try_http: 是否尝试HTTP（用于HTTPS失败后的降级）

        Returns:
            CheckResult: 检查结果
        """
        # 检查是否是WebSocket URL
        if url.startswith(("ws://", "wss://")):
            return await self._check_websocket(
                url, timeout=5 if quick_mode else self.timeout
            )

        # 自动添加 https:// 前缀（如果没有协议）
        original_url = url
        if not url.startswith(("http://", "https://")):
            # 检查是否应该使用wss协议（通过域名判断）
            # 更严格的判断：只有明确以ws.开头的域名才视为WebSocket
            if url.startswith("ws."):
                url = f"wss://{url}"
                return await self._check_websocket(
                    url, timeout=5 if quick_mode else self.timeout
                )
            else:
                # 如果是降级尝试，使用HTTP，否则使用HTTPS
                url = f"http://{url}" if try_http else f"https://{url}"

        # 从 URL 中提取域名作为名称
        from urllib.parse import urlparse

        parsed = urlparse(url)
        name = parsed.netloc or original_url
        # 扩展接受的状态码，包含更多正常的响应
        expected_codes = [
            200,  # OK
            201,
            202,
            203,
            204,  # 其他成功状态
            301,
            302,
            303,
            304,
            307,
            308,  # 各种重定向
            401,
            403,  # 认证相关（网站正常但需要登录）
        ]

        start_time = datetime.now()

        # 快速模式下使用更短的超时
        timeout = 5 if quick_mode else self.timeout

        try:
            # 根据是否是降级请求或HTTP请求选择不同的客户端
            if try_http or url.startswith("http://"):
                # HTTP请求或降级请求使用不验证SSL的客户端（避免重定向到HTTPS时的SSL错误）
                client = await self._get_client_no_verify()
            else:
                # HTTPS请求使用标准客户端
                client = await self._get_client()
            response = await client.get(url)
            response_time = (datetime.now() - start_time).total_seconds()

            # 先检查安全问题
            security_status = self._check_for_security_issues(response)
            if security_status:
                self.logger.warning(f"域名 {name} ({url}) 检测到安全问题")
                return CheckResult(
                    domain_name=name,
                    url=url,
                    status=security_status,
                    status_code=response.status_code,
                    error_message="网站可能存在安全风险",
                    response_time=response_time,
                )

            # 检查状态码
            if response.status_code in expected_codes:
                self.logger.info(
                    f"域名 {name} ({url}) 检查成功，状态码：{response.status_code}"
                )
                return CheckResult(
                    domain_name=name,
                    url=url,
                    status=CheckStatus.SUCCESS,
                    status_code=response.status_code,
                    response_time=response_time,
                )
            else:
                self.logger.warning(
                    f"域名 {name} ({url}) 状态码异常：{response.status_code}"
                )
                # HTTP错误通常是服务器配置问题，不重试
                return CheckResult(
                    domain_name=name,
                    url=url,
                    status=CheckStatus.HTTP_ERROR,
                    status_code=response.status_code,
                    error_message=f"状态码：{response.status_code}",
                    response_time=response_time,
                )

        except httpx.ConnectError as e:
            error_msg = str(e)
            # 更详细的DNS错误判断
            if any(
                dns_err in error_msg.lower()
                for dns_err in [
                    "name or service not known",
                    "getaddrinfo failed",
                    "nodename nor servname",
                    "cannot resolve",
                    "no such host",
                    "temporary failure in name resolution",
                    "dns lookup failed",
                    "nxdomain",
                ]
            ):
                status = CheckStatus.DNS_ERROR
                self.logger.error(f"域名 {name} ({url}) DNS 解析失败：{error_msg}")
            # 连接被拒绝
            elif "connection refused" in error_msg.lower():
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(
                    f"域名 {name} ({url}) 连接被拒绝（服务未启动或端口关闭）：{error_msg}"
                )
            # 网络不可达
            elif any(
                net_err in error_msg.lower()
                for net_err in [
                    "network unreachable",
                    "no route to host",
                    "host is unreachable",
                ]
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 网络不可达：{error_msg}")
            # 连接重置
            elif "connection reset" in error_msg.lower():
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 连接被重置：{error_msg}")
            else:
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 连接失败：{error_msg}")

            return CheckResult(
                domain_name=name, url=url, status=status, error_message=error_msg
            )

        except httpx.TimeoutException as e:
            error_msg = str(e)
            # 区分不同类型的超时
            if isinstance(e, httpx.ConnectTimeout):
                self.logger.error(f"域名 {name} ({url}) 连接建立超时")
                timeout_msg = f"连接建立超时（{timeout}秒，未重试）"
            elif isinstance(e, httpx.ReadTimeout):
                self.logger.error(f"域名 {name} ({url}) 读取响应超时")
                timeout_msg = f"读取响应超时（{timeout}秒，未重试）"
            elif isinstance(e, httpx.WriteTimeout):
                self.logger.error(f"域名 {name} ({url}) 发送请求超时")
                timeout_msg = f"发送请求超时（{timeout}秒，未重试）"
            elif isinstance(e, httpx.PoolTimeout):
                self.logger.error(f"域名 {name} ({url}) 连接池超时")
                timeout_msg = f"连接池超时（{timeout}秒，未重试）"
            else:
                self.logger.error(f"域名 {name} ({url}) 请求超时")
                timeout_msg = f"请求超时（{timeout}秒，未重试）"

            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.TIMEOUT,
                error_message=timeout_msg,
            )

        except Exception as e:
            error_msg = str(e)
            error_lower = error_msg.lower()

            # SSL/TLS相关错误
            if any(
                ssl_err in error_lower
                for ssl_err in [
                    "ssl",
                    "tls",
                    "certificate",
                    "cert",
                    "handshake",
                    "verification",
                    "verify failed",
                    "self signed",
                    "expired",
                ]
            ):
                status = CheckStatus.SSL_ERROR
                # 识别具体的SSL问题
                if "expired" in error_lower:
                    self.logger.error(
                        f"域名 {name} ({url}) SSL 证书已过期：{error_msg}"
                    )
                elif "self signed" in error_lower or "self-signed" in error_lower:
                    self.logger.error(
                        f"域名 {name} ({url}) 使用自签名证书：{error_msg}"
                    )
                elif "verification" in error_lower or "verify" in error_lower:
                    self.logger.error(
                        f"域名 {name} ({url}) SSL 证书验证失败：{error_msg}"
                    )
                elif "handshake" in error_lower:
                    self.logger.error(f"域名 {name} ({url}) SSL 握手失败：{error_msg}")
                else:
                    self.logger.error(f"域名 {name} ({url}) SSL 证书错误：{error_msg}")
            # 代理相关错误
            elif any(
                proxy_err in error_lower
                for proxy_err in ["proxy", "socks", "authentication required"]
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 代理连接问题：{error_msg}")
            # 协议错误
            elif (
                "unsupported protocol" in error_lower or "protocol error" in error_lower
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 协议不支持或错误：{error_msg}")
            # 编码错误
            elif "codec" in error_lower or "decode" in error_lower:
                status = CheckStatus.UNKNOWN_ERROR
                self.logger.error(f"域名 {name} ({url}) 响应解码错误：{error_msg}")
            else:
                status = CheckStatus.UNKNOWN_ERROR
                self.logger.error(
                    f"域名 {name} ({url}) 检查时发生未知错误：{error_msg}"
                )

            return CheckResult(
                domain_name=name, url=url, status=status, error_message=error_msg
            )

    async def check_single_domain(
        self,
        url: str,
        retry_attempt: int = 0,
        quick_mode: bool = False,
        try_http: bool = False,
    ) -> CheckResult:
        """
        检查单个域名

        Args:
            url: 要检查的 URL或域名
            retry_attempt: 当前重试次数
            quick_mode: 快速模式，减少超时和重试
            try_http: 是否尝试HTTP（用于HTTPS失败后的降级）

        Returns:
            CheckResult: 检查结果
        """
        # 检查是否是WebSocket URL
        if url.startswith(("ws://", "wss://")):
            return await self._check_websocket(
                url, timeout=5 if quick_mode else self.timeout
            )

        # 自动添加 https:// 前缀（如果没有协议）
        original_url = url  # 保存原始输入
        if not url.startswith(("http://", "https://")):
            # 检查是否应该使用wss协议（通过域名判断）
            # 更严格的判断：只有明确以ws.开头的域名才视为WebSocket
            if url.startswith("ws."):
                url = f"wss://{url}"
                return await self._check_websocket(
                    url, timeout=5 if quick_mode else self.timeout
                )
            else:
                # 如果是降级尝试，使用HTTP，否则使用HTTPS
                url = f"http://{url}" if try_http else f"https://{url}"

        # 从 URL 中提取域名作为名称
        from urllib.parse import urlparse

        parsed = urlparse(url)
        name = parsed.netloc or original_url  # 使用原始输入作为名称
        # 扩展接受的状态码，包含更多正常的响应
        expected_codes = [
            200,  # OK
            201,
            202,
            203,
            204,  # 其他成功状态
            301,
            302,
            303,
            304,
            307,
            308,  # 各种重定向
            401,
            403,  # 认证相关（网站正常但需要登录）
        ]

        start_time = datetime.now()

        # 快速模式下使用更短的超时和更少的重试
        timeout = 5 if quick_mode else self.timeout
        max_retries = 1 if quick_mode else self.retry_count
        retry_delay = 2 if quick_mode else self.retry_delay

        try:
            # 根据是否是降级请求或HTTP请求选择不同的客户端
            if try_http or url.startswith("http://"):
                # HTTP请求或降级请求使用不验证SSL的客户端（避免重定向到HTTPS时的SSL错误）
                client = await self._get_client_no_verify()
            else:
                # HTTPS请求使用标准客户端
                client = await self._get_client()
            response = await client.get(url)
            response_time = (datetime.now() - start_time).total_seconds()

            # 先检查安全问题
            security_status = self._check_for_security_issues(response)
            if security_status:
                self.logger.warning(f"域名 {name} ({url}) 检测到安全问题")
                return CheckResult(
                    domain_name=name,
                    url=url,
                    status=security_status,
                    status_code=response.status_code,
                    error_message="网站可能存在安全风险",
                    response_time=response_time,
                )

            # 检查状态码是否在预期范围内
            if response.status_code in expected_codes:
                self.logger.info(
                    f"域名 {name} ({url}) 检查成功，状态码：{response.status_code}"
                )
                return CheckResult(
                    domain_name=name,
                    url=url,
                    status=CheckStatus.SUCCESS,
                    status_code=response.status_code,
                    response_time=response_time,
                )
            else:
                self.logger.warning(
                    f"域名 {name} ({url}) 状态码异常：{response.status_code}"
                )
                # HTTP错误通常是服务器配置问题，不重试
                return CheckResult(
                    domain_name=name,
                    url=url,
                    status=CheckStatus.HTTP_ERROR,
                    status_code=response.status_code,
                    error_message=f"状态码：{response.status_code}",
                    response_time=response_time,
                )

        except httpx.ConnectError as e:
            error_msg = str(e)
            if (
                "Name or service not known" in error_msg
                or "getaddrinfo failed" in error_msg
            ):
                status = CheckStatus.DNS_ERROR
                self.logger.error(f"域名 {name} ({url}) DNS 解析失败：{error_msg}")
                # DNS错误不重试，域名本身有问题
                return CheckResult(
                    domain_name=name, url=url, status=status, error_message=error_msg
                )
            elif "SSL" in error_msg or "certificate" in error_msg.lower():
                # SSL错误应该被单独处理
                status = CheckStatus.SSL_ERROR
                self.logger.error(f"域名 {name} ({url}) SSL 证书错误：{error_msg}")

                # SSL错误时，如果还没尝试过HTTP，尝试降级到HTTP
                if url.startswith("https://") and not try_http:
                    self.logger.info(f"域名 {name} SSL证书错误，尝试降级到HTTP")
                    # 如果原始URL带有https://，需要替换为http://
                    http_url = (
                        original_url.replace("https://", "http://")
                        if original_url.startswith("https://")
                        else original_url
                    )
                    return await self.check_single_domain(
                        http_url, 0, quick_mode, try_http=True
                    )

                return CheckResult(
                    domain_name=name, url=url, status=status, error_message=error_msg
                )
            # 连接被拒绝
            elif (
                "connection refused" in error_msg.lower()
                or "actively refused" in error_msg.lower()
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(
                    f"域名 {name} ({url}) 连接被拒绝（服务未启动或端口关闭）：{error_msg}"
                )
            # 网络不可达
            elif any(
                net_err in error_msg.lower()
                for net_err in [
                    "network unreachable",
                    "no route to host",
                    "host is unreachable",
                    "network is unreachable",
                ]
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 网络不可达：{error_msg}")
            # 连接重置
            elif (
                "connection reset" in error_msg.lower()
                or "reset by peer" in error_msg.lower()
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 连接被重置：{error_msg}")
            # 连接中断
            elif any(
                abort_err in error_msg.lower()
                for abort_err in [
                    "connection aborted",
                    "broken pipe",
                    "connection lost",
                ]
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 连接中断：{error_msg}")
            else:
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 连接失败：{error_msg}")

            # 如果是HTTPS连接失败，且还没尝试过HTTP，尝试降级到HTTP
            if url.startswith("https://") and not try_http and retry_attempt == 0:
                self.logger.info(f"域名 {name} HTTPS连接失败，尝试降级到HTTP")
                # 如果原始URL带有https://，需要替换为http://
                http_url = (
                    original_url.replace("https://", "http://")
                    if original_url.startswith("https://")
                    else original_url
                )
                return await self.check_single_domain(
                    http_url, 0, quick_mode, try_http=True
                )

            # 连接错误可能是暂时的，可以重试
            if retry_attempt < max_retries:
                self.logger.info(
                    f"域名 {name} 将在 {retry_delay} 秒后进行第 {retry_attempt + 1} 次重试"
                )
                await asyncio.sleep(retry_delay)
                return await self.check_single_domain(
                    url, retry_attempt + 1, quick_mode, try_http
                )

            return CheckResult(
                domain_name=name, url=url, status=status, error_message=error_msg
            )

        except httpx.TimeoutException:
            self.logger.error(f"域名 {name} ({url}) 请求超时")

            # 如果还有重试次数，进行重试
            if retry_attempt < max_retries:
                self.logger.info(
                    f"域名 {name} 将在 {retry_delay} 秒后进行第 {retry_attempt + 1} 次重试"
                )
                await asyncio.sleep(retry_delay)
                return await self.check_single_domain(
                    url, retry_attempt + 1, quick_mode, try_http
                )

            # 构建详细的超时错误信息
            retry_info = f"" if retry_attempt == 0 else f"，已重试{retry_attempt}次"
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.TIMEOUT,
                error_message=f"请求超时（{timeout}秒{retry_info}）",
            )

        except httpx.ConnectTimeout:
            self.logger.error(f"域名 {name} ({url}) 连接超时")

            if retry_attempt < max_retries:
                self.logger.info(
                    f"域名 {name} 将在 {retry_delay} 秒后进行第 {retry_attempt + 1} 次重试"
                )
                await asyncio.sleep(retry_delay)
                return await self.check_single_domain(
                    url, retry_attempt + 1, quick_mode, try_http
                )

            # 构建详细的超时错误信息
            retry_info = f"" if retry_attempt == 0 else f"，已重试{retry_attempt}次"
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.TIMEOUT,
                error_message=f"连接建立超时（{timeout}秒{retry_info}）",
            )

        except Exception as e:
            error_msg = str(e)
            if "SSL" in error_msg or "certificate" in error_msg.lower():
                status = CheckStatus.SSL_ERROR
                self.logger.error(f"域名 {name} ({url}) SSL 证书错误：{error_msg}")

                # SSL错误时，如果还没尝试过HTTP，尝试降级到HTTP
                if url.startswith("https://") and not try_http:
                    self.logger.info(f"域名 {name} SSL证书错误，尝试降级到HTTP")
                    # 如果原始URL带有https://，需要替换为http://
                    http_url = (
                        original_url.replace("https://", "http://")
                        if original_url.startswith("https://")
                        else original_url
                    )
                    return await self.check_single_domain(
                        http_url, 0, quick_mode, try_http=True
                    )

                # SSL错误通常是配置问题，不重试
                return CheckResult(
                    domain_name=name, url=url, status=status, error_message=error_msg
                )
            # 代理错误
            elif any(
                proxy_err in error_msg.lower()
                for proxy_err in ["proxy", "socks", "authentication required"]
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 代理连接问题：{error_msg}")
            # 协议错误
            elif (
                "unsupported protocol" in error_msg.lower()
                or "protocol error" in error_msg.lower()
            ):
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 协议不支持或错误：{error_msg}")
            # 编码错误
            elif "codec" in error_msg.lower() or "decode" in error_msg.lower():
                status = CheckStatus.UNKNOWN_ERROR
                self.logger.error(f"域名 {name} ({url}) 响应编码错误：{error_msg}")
            else:
                status = CheckStatus.UNKNOWN_ERROR
                self.logger.error(
                    f"域名 {name} ({url}) 检查时发生未知错误：{error_msg}"
                )

            # 对于未知错误和编码错误，不重试，避免浪费时间
            return CheckResult(
                domain_name=name, url=url, status=status, error_message=error_msg
            )

    async def check_domains_batch(
        self,
        urls: List[str],
        batch_callback: Optional[callable] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[CheckResult]:
        """
        批处理检查域名，按最大并发数分批执行

        Args:
            urls: 域名 URL 列表
            batch_callback: 批次完成回调（用于分批通知）
            progress_callback: 进度回调函数

        Returns:
            List[CheckResult]: 检查结果列表
        """
        domain_count = len(urls)
        if domain_count == 0:
            return []

        # 计算批次信息
        batch_size = self.max_concurrent
        total_batches = (domain_count + batch_size - 1) // batch_size

        self.logger.info(
            f"开始检查 {domain_count} 个域名，并发数：{self.max_concurrent}，预计分 {total_batches} 批处理"
        )

        # 记录开始时间用于估算剩余时间
        start_time = datetime.now()
        all_results = []

        # 快速模式：超过50个域名启用
        quick_mode = domain_count > 50

        # 分批处理 - 使用while循环确保处理所有域名
        batch_idx = 0
        processed_count = 0

        while processed_count < domain_count:
            # 每批开始前检查是否需要调整并发数
            if self.auto_adjust and batch_idx > 0:
                self._adjust_concurrent_by_resources()
                # 如果并发数变了，重新计算批次大小
                if self.max_concurrent != batch_size:
                    batch_size = self.max_concurrent

            batch_start = processed_count
            batch_end = min(batch_start + batch_size, domain_count)
            batch_urls = urls[batch_start:batch_end]
            current_batch = batch_idx + 1

            # 重新计算总批次数（基于当前批次大小）
            remaining_domains = domain_count - processed_count
            remaining_batches = (remaining_domains + batch_size - 1) // batch_size
            total_batches = batch_idx + remaining_batches

            self.logger.info(
                f"处理第 {current_batch}/{total_batches} 批，包含 {len(batch_urls)} 个域名，当前并发数: {self.max_concurrent}"
            )

            # 记录批次开始时间
            batch_start_time = datetime.now()

            # 使用固定的并发槽位，不让重试阻塞整批
            async def check_single_no_retry(url: str) -> CheckResult:
                """单次检查，不内部重试"""
                try:
                    return await self._check_once(url, quick_mode, try_http=False)
                except Exception as e:
                    self.logger.error(f"检查 {url} 失败: {e}")
                    return CheckResult(
                        domain_name=url,
                        url=url if url.startswith("http") else f"https://{url}",
                        status=CheckStatus.UNKNOWN_ERROR,
                        error_message=str(e),
                    )

            # 第一次尝试：并发检查所有URL
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def check_with_semaphore(url: str) -> CheckResult:
                async with semaphore:
                    return await check_single_no_retry(url)

            # 并发执行当前批次（第一次尝试）
            tasks = [
                asyncio.create_task(check_with_semaphore(url)) for url in batch_urls
            ]
            first_results = await asyncio.gather(*tasks)

            # 收集需要重试的URL
            retry_needed = []
            batch_results = list(first_results)  # 直接复制所有结果，避免索引问题

            for i, result in enumerate(first_results):
                if result.status in [CheckStatus.TIMEOUT, CheckStatus.CONNECTION_ERROR]:
                    # 只对超时和连接错误进行重试
                    retry_needed.append((batch_urls[i], i))

            # 如果有需要重试的，进行重试（不阻塞，使用相同的并发限制）
            if retry_needed and self.retry_count > 0:
                self.logger.info(
                    f"第 {current_batch} 批有 {len(retry_needed)} 个域名需要重试"
                )

                # 短暂延迟后重试
                await asyncio.sleep(self.retry_delay)

                # 对需要重试的域名进行第二次尝试
                retry_semaphore = asyncio.Semaphore(
                    min(len(retry_needed), self.max_concurrent)
                )

                async def retry_with_semaphore(url: str) -> CheckResult:
                    async with retry_semaphore:
                        return await self.check_single_domain(
                            url, retry_attempt=1, quick_mode=quick_mode, try_http=False
                        )

                retry_tasks = []
                for url, original_idx in retry_needed:
                    retry_tasks.append(
                        (original_idx, asyncio.create_task(retry_with_semaphore(url)))
                    )

                # 执行重试并更新结果
                for original_idx, task in retry_tasks:
                    retry_result = await task
                    # 更新原始位置的结果
                    batch_results[original_idx] = retry_result

            # 更新结果
            all_results.extend(batch_results)

            # 更新状态缓存
            for result in batch_results:
                self._update_status_cache(result.url, result.is_success)

            # 计算批次耗时和预估剩余时间
            batch_duration = (datetime.now() - batch_start_time).total_seconds()
            avg_batch_time = (
                datetime.now() - start_time
            ).total_seconds() / current_batch
            remaining_batches = total_batches - current_batch
            eta_seconds = remaining_batches * avg_batch_time

            # 调用批次回调（用于分批通知）
            if batch_callback:
                try:
                    if asyncio.iscoroutinefunction(batch_callback):
                        await batch_callback(
                            batch_results, current_batch, total_batches, eta_seconds
                        )
                    else:
                        batch_callback(
                            batch_results, current_batch, total_batches, eta_seconds
                        )
                except Exception as e:
                    self.logger.error(f"批次回调执行失败：{e}")

            # 调用进度回调
            if progress_callback:
                completed = batch_end
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(completed, domain_count, eta_seconds)
                    else:
                        progress_callback(completed, domain_count, eta_seconds)
                except Exception as e:
                    self.logger.error(f"进度回调执行失败：{e}")

            # 更新已处理计数和批次索引
            processed_count += len(batch_urls)
            batch_idx += 1

            # 批次间短暂延迟，避免过度压力
            if processed_count < domain_count:
                await asyncio.sleep(0.5)

        # 计算总耗时
        total_duration = (datetime.now() - start_time).total_seconds()
        self.last_check_duration = total_duration

        # 统计结果
        success_count = sum(1 for r in all_results if r.is_success)
        failed_count = len(all_results) - success_count

        self.logger.info(
            f"全部检查完成：共处理 {len(all_results)}/{domain_count} 个域名，成功 {success_count} 个，失败 {failed_count} 个，耗时 {total_duration:.1f} 秒"
        )

        # 每次检查完成后都清理资源，避免连接泄漏
        try:
            await self.close_client()  # 关闭连接池，释放资源
        except Exception as e:
            self.logger.debug(f"清理客户端资源时出错: {e}")

        # 大量域名检查后触发垃圾回收
        if domain_count > 500:
            gc.collect()
            self.logger.debug("已进行垃圾回收")

        return all_results

    async def check_domains(self, urls: List[str], **kwargs) -> List[CheckResult]:
        """
        兼容旧接口的检查方法

        Args:
            urls: 域名列表
            **kwargs: 其他参数（忽略）

        Returns:
            List[CheckResult]: 检查结果
        """
        return await self.check_domains_batch(urls)

    def _update_status_cache(self, url: str, status: bool) -> None:
        """
        更新状态缓存，限制缓存大小

        Args:
            url: 域名URL
            status: 状态
        """
        # 如果缓存太大，删除最旧的一半
        if len(self.last_status) >= self.max_status_cache:
            # 保留最近的一半
            items = list(self.last_status.items())
            self.last_status = dict(items[len(items) // 2 :])
            self.logger.debug(f"状态缓存已清理，当前大小：{len(self.last_status)}")

        self.last_status[url] = status

    def is_recovered(self, url: str, current_status: bool) -> bool:
        """
        判断域名是否从故障状态恢复

        Args:
            url: 域名 URL
            current_status: 当前状态（True 为正常）

        Returns:
            bool: 是否恢复
        """
        if url not in self.last_status:
            return False

        # 如果上次是失败，这次是成功，说明恢复了
        return not self.last_status[url] and current_status

    async def check_domains_stream(
        self, urls: List[str], max_concurrent: int = 50
    ) -> AsyncGenerator[CheckResult, None]:
        """
        流式检查域名，适合超大量域名的内存优化处理

        Args:
            urls: 域名列表
            max_concurrent: 最大并发数

        Yields:
            CheckResult: 逐个返回检查结果
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        quick_mode = len(urls) > 50

        async def check_with_limit(url: str) -> CheckResult:
            async with semaphore:
                return await self.check_single_domain(
                    url, 0, quick_mode, try_http=False
                )

        # 创建任务并流式返回结果
        tasks = [asyncio.create_task(check_with_limit(url)) for url in urls]

        for task in asyncio.as_completed(tasks):
            result = await task
            self._update_status_cache(result.url, result.is_success)
            yield result

        # 清理任务
        for task in tasks:
            if not task.done():
                task.cancel()

    def cleanup(self) -> None:
        """
        清理资源，释放内存
        """
        # 清理状态缓存
        if len(self.last_status) > 100:
            # 只保留最近100个
            items = list(self.last_status.items())
            self.last_status = dict(items[-100:])

        # 强制垃圾回收
        gc.collect()
        self.logger.debug("资源清理完成")
