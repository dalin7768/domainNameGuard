import httpx
import asyncio
from typing import Dict, List, Tuple, Optional, AsyncGenerator
from datetime import datetime
import socket
import logging
from dataclasses import dataclass
from enum import Enum
import gc


class CheckStatus(Enum):
    """检查状态枚举"""
    SUCCESS = "success"
    DNS_ERROR = "dns_error"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    SSL_ERROR = "ssl_error"
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
            CheckStatus.HTTP_ERROR: f"HTTP 错误：状态码 {self.status_code}",
            CheckStatus.SSL_ERROR: "SSL 证书错误：证书验证失败或已过期",
            CheckStatus.UNKNOWN_ERROR: "未知错误：请检查日志了解详情"
        }
        
        base_desc = error_descriptions.get(self.status, "未知错误")
        if self.error_message:
            return f"{base_desc}\n详细信息：{self.error_message}"
        return base_desc


class DomainChecker:
    """域名检测器类"""
    
    def __init__(self, timeout: int = 10, retry_count: int = 2, retry_delay: int = 5):
        """
        初始化域名检测器
        
        Args:
            timeout: 请求超时时间（秒）
            retry_count: 重试次数
            retry_delay: 重试延迟（秒）
        """
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)
        
        # 存储域名的上次状态，用于判断是否恢复
        # 使用LRU缓存避免无限增长
        self.last_status: Dict[str, bool] = {}
        self.max_status_cache = 1000  # 最多缓存1000个域名状态
        
        # HTTP客户端池，复用连接
        self._client_pool: List[httpx.AsyncClient] = []
        self._pool_size = 0
        self._max_pool_size = 10
    
    async def check_single_domain(self, 
                                 url: str,
                                 retry_attempt: int = 0,
                                 quick_mode: bool = False) -> CheckResult:
        """
        检查单个域名
        
        Args:
            url: 要检查的 URL或域名
            retry_attempt: 当前重试次数
            quick_mode: 快速模式，减少超时和重试
            
        Returns:
            CheckResult: 检查结果
        """
        # 自动添加 https:// 前缀（如果没有协议）
        original_url = url  # 保存原始输入
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        
        # 从 URL 中提取域名作为名称
        from urllib.parse import urlparse
        parsed = urlparse(url)
        name = parsed.netloc or original_url  # 使用原始输入作为名称
        expected_codes = [200, 301, 302]  # 默认接受的状态码
        
        start_time = datetime.now()
        
        # 快速模式下使用更短的超时和更少的重试
        timeout = 5 if quick_mode else self.timeout
        max_retries = 1 if quick_mode else self.retry_count
        retry_delay = 2 if quick_mode else self.retry_delay
        
        try:
            # 使用 httpx 进行异步请求
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
                verify=True
            ) as client:
                response = await client.get(url)
                response_time = (datetime.now() - start_time).total_seconds()
                
                # 检查状态码是否在预期范围内
                if response.status_code in expected_codes:
                    self.logger.info(f"域名 {name} ({url}) 检查成功，状态码：{response.status_code}")
                    return CheckResult(
                        domain_name=name,
                        url=url,
                        status=CheckStatus.SUCCESS,
                        status_code=response.status_code,
                        response_time=response_time
                    )
                else:
                    self.logger.warning(f"域名 {name} ({url}) 状态码异常：{response.status_code}")
                    return CheckResult(
                        domain_name=name,
                        url=url,
                        status=CheckStatus.HTTP_ERROR,
                        status_code=response.status_code,
                        error_message=f"预期状态码：{expected_codes}，实际：{response.status_code}",
                        response_time=response_time
                    )
                    
        except httpx.ConnectError as e:
            error_msg = str(e)
            if "Name or service not known" in error_msg or "getaddrinfo failed" in error_msg:
                status = CheckStatus.DNS_ERROR
                self.logger.error(f"域名 {name} ({url}) DNS 解析失败：{error_msg}")
            else:
                status = CheckStatus.CONNECTION_ERROR
                self.logger.error(f"域名 {name} ({url}) 连接失败：{error_msg}")
            
            # 如果还有重试次数，进行重试
            if retry_attempt < max_retries:
                self.logger.info(f"域名 {name} 将在 {retry_delay} 秒后进行第 {retry_attempt + 1} 次重试")
                await asyncio.sleep(retry_delay)
                return await self.check_single_domain(url, retry_attempt + 1, quick_mode)
            
            return CheckResult(
                domain_name=name,
                url=url,
                status=status,
                error_message=error_msg
            )
            
        except httpx.TimeoutException:
            self.logger.error(f"域名 {name} ({url}) 请求超时")
            
            # 如果还有重试次数，进行重试
            if retry_attempt < max_retries:
                self.logger.info(f"域名 {name} 将在 {retry_delay} 秒后进行第 {retry_attempt + 1} 次重试")
                await asyncio.sleep(retry_delay)
                return await self.check_single_domain(url, retry_attempt + 1, quick_mode)
            
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.TIMEOUT,
                error_message=f"请求超时（{timeout}秒）"
            )
            
        except httpx.ConnectTimeout:
            self.logger.error(f"域名 {name} ({url}) 连接超时")
            
            if retry_attempt < max_retries:
                self.logger.info(f"域名 {name} 将在 {retry_delay} 秒后进行第 {retry_attempt + 1} 次重试")
                await asyncio.sleep(retry_delay)
                return await self.check_single_domain(url, retry_attempt + 1, quick_mode)
            
            return CheckResult(
                domain_name=name,
                url=url,
                status=CheckStatus.TIMEOUT,
                error_message="连接建立超时"
            )
            
        except Exception as e:
            error_msg = str(e)
            if "SSL" in error_msg or "certificate" in error_msg.lower():
                status = CheckStatus.SSL_ERROR
                self.logger.error(f"域名 {name} ({url}) SSL 证书错误：{error_msg}")
            else:
                status = CheckStatus.UNKNOWN_ERROR
                self.logger.error(f"域名 {name} ({url}) 检查时发生未知错误：{error_msg}")
            
            if retry_attempt < max_retries:
                self.logger.info(f"域名 {name} 将在 {retry_delay} 秒后进行第 {retry_attempt + 1} 次重试")
                await asyncio.sleep(retry_delay)
                return await self.check_single_domain(url, retry_attempt + 1, quick_mode)
            
            return CheckResult(
                domain_name=name,
                url=url,
                status=status,
                error_message=error_msg
            )
    
    async def check_domains(self, 
                          urls: List[str], 
                          max_concurrent: Optional[int] = None,
                          progress_callback: Optional[callable] = None) -> List[CheckResult]:
        """
        并发检查多个域名，支持大量域名的高效处理
        
        Args:
            urls: 域名 URL 列表
            max_concurrent: 最大并发数，None时自动计算
            progress_callback: 进度回调函数，用于发送进度通知
            
        Returns:
            List[CheckResult]: 检查结果列表
        """
        domain_count = len(urls)
        
        # 智能计算并发数
        if max_concurrent is None:
            if domain_count <= 10:
                max_concurrent = domain_count  # 少量域名，全部并发
            elif domain_count <= 50:
                max_concurrent = 20  # 中等数量
            elif domain_count <= 200:
                max_concurrent = 50  # 较多域名
            elif domain_count <= 500:
                max_concurrent = 100  # 大量域名
            else:
                max_concurrent = 200  # 超大量域名
        
        self.logger.info(f"开始检查 {domain_count} 个域名，最大并发数：{max_concurrent}")
        
        # 决定是否使用批处理
        use_batch = domain_count > 500
        batch_size = 500 if use_batch else domain_count
        
        all_results = []
        
        # 分批处理超大量域名
        for batch_num in range(0, domain_count, batch_size):
            batch_urls = urls[batch_num:min(batch_num + batch_size, domain_count)]
            batch_index = batch_num // batch_size + 1
            total_batches = (domain_count + batch_size - 1) // batch_size
            
            if use_batch:
                self.logger.info(f"处理第 {batch_index}/{total_batches} 批，包含 {len(batch_urls)} 个域名")
            
            # 处理当前批次
            batch_results = await self._check_batch(
                batch_urls, 
                max_concurrent,
                progress_callback,
                batch_index if use_batch else None,
                total_batches if use_batch else None
            )
            
            all_results.extend(batch_results)
            
            # 批次间稍微延迟，避免过度压力
            if use_batch and batch_num + batch_size < domain_count:
                await asyncio.sleep(1)
        
        # 更新域名状态记录（带缓存限制）
        for result in all_results:
            self._update_status_cache(result.url, result.is_success)
        
        # 统计最终结果
        success_count = sum(1 for r in all_results if r.is_success)
        failed_count = len(all_results) - success_count
        
        self.logger.info(f"全部检查完成：成功 {success_count} 个，失败 {failed_count} 个")
        
        # 大量域名检查后触发垃圾回收
        if domain_count > 500:
            gc.collect()
            self.logger.debug("已触发垃圾回收，释放内存")
        
        return all_results
    
    async def _check_batch(self,
                          urls: List[str],
                          max_concurrent: int,
                          progress_callback: Optional[callable],
                          batch_index: Optional[int],
                          total_batches: Optional[int]) -> List[CheckResult]:
        """
        检查一批域名
        
        Args:
            urls: 域名列表
            max_concurrent: 最大并发数
            progress_callback: 进度回调
            batch_index: 批次索引
            total_batches: 总批次数
            
        Returns:
            List[CheckResult]: 检查结果
        """
        results = []
        domain_count = len(urls)
        
        # 使用信号量限制并发
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # 根据域名数量决定检查模式
        quick_mode = domain_count > 50
        if quick_mode and batch_index == 1:  # 只在第一批时输出
            self.logger.info("检测到大量域名，启用快速模式（减少超时和重试）")
        
        async def check_with_limit(url: str) -> CheckResult:
            """带并发限制的检查"""
            async with semaphore:
                return await self.check_single_domain(url, 0, quick_mode)
        
        # 创建所有任务
        tasks = [check_with_limit(url) for url in urls]
        
        # 使用 as_completed 逐步获取结果
        completed = 0
        last_progress_report = 0
        
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1
            
            # 计算进度百分比
            progress_percent = (completed / domain_count) * 100
            
            # 每10%或每50个域名报告一次进度（取较小值）
            report_interval = min(50, max(1, domain_count // 10))
            
            if completed - last_progress_report >= report_interval or completed == domain_count:
                # 构建进度信息
                if batch_index:
                    progress_msg = f"批次 {batch_index}/{total_batches} - 进度：{completed}/{domain_count} ({progress_percent:.1f}%)"
                else:
                    progress_msg = f"检查进度：{completed}/{domain_count} ({progress_percent:.1f}%)"
                
                self.logger.info(progress_msg)
                
                # 调用进度回调（如果提供）
                if progress_callback and (completed == domain_count or completed % 100 == 0):
                    try:
                        # 异步调用回调
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback(completed, domain_count, batch_index, total_batches)
                        else:
                            progress_callback(completed, domain_count, batch_index, total_batches)
                    except Exception as e:
                        self.logger.error(f"进度回调执行失败：{e}")
                
                last_progress_report = completed
        
        return results
    
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
            self.last_status = dict(items[len(items)//2:])
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
    
    async def check_domains_stream(self, 
                                  urls: List[str],
                                  max_concurrent: int = 50) -> AsyncGenerator[CheckResult, None]:
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
                return await self.check_single_domain(url, 0, quick_mode)
        
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