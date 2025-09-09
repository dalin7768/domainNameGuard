#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
错误状态跟踪器

用于跟踪域名的错误状态变化，实现智能通知策略
"""

import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, asdict
import logging
from enum import Enum

from domain_checker import CheckResult, CheckStatus


class ErrorState(Enum):
    """错误状态枚举"""
    HEALTHY = "healthy"  # 健康
    ERROR = "error"  # 错误
    RECOVERED = "recovered"  # 已恢复
    ACKNOWLEDGED = "acknowledged"  # 已确认处理


@dataclass
class DomainHistory:
    """域名历史记录"""
    domain_name: str
    status: str
    error_type: Optional[str]
    timestamp: str
    acknowledged: bool = False
    acknowledged_time: Optional[str] = None
    notes: Optional[str] = None


class ErrorTracker:
    """错误状态跟踪器"""
    
    def __init__(self, history_file: str = "error_history.json", retention_days: int = 30):
        """
        初始化错误跟踪器
        
        Args:
            history_file: 历史记录文件路径
            retention_days: 历史记录保留天数
        """
        self.history_file = Path(history_file)
        self.retention_days = retention_days
        self.logger = logging.getLogger(__name__)
        
        # 当前错误状态
        self.current_errors: Dict[str, CheckResult] = {}
        # 上次检查的错误状态
        self.previous_errors: Dict[str, CheckResult] = {}
        # 已确认处理的错误
        self.acknowledged_errors: Set[str] = set()
        # 历史记录
        self.history: List[DomainHistory] = []
        
        # 加载历史记录
        self.load_history()
        
        # 锁
        self.lock = asyncio.Lock()
    
    def load_history(self):
        """加载历史记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history = [
                        DomainHistory(**record) for record in data.get('history', [])
                    ]
                    self.acknowledged_errors = set(data.get('acknowledged_errors', []))
                    
                # 清理过期记录
                self.cleanup_old_records()
                
                self.logger.info(f"加载 {len(self.history)} 条历史记录")
            except Exception as e:
                self.logger.error(f"加载历史记录失败: {e}")
                self.history = []
                self.acknowledged_errors = set()
    
    def save_history(self):
        """保存历史记录"""
        try:
            # 清理过期记录
            self.cleanup_old_records()
            
            data = {
                'history': [asdict(record) for record in self.history],
                'acknowledged_errors': list(self.acknowledged_errors),
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            self.logger.debug(f"保存 {len(self.history)} 条历史记录")
        except Exception as e:
            self.logger.error(f"保存历史记录失败: {e}")
    
    def cleanup_old_records(self):
        """清理过期的历史记录"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        # 过滤掉过期记录
        self.history = [
            record for record in self.history
            if datetime.fromisoformat(record.timestamp) > cutoff_date
        ]
    
    async def update_status(self, results: List[CheckResult]) -> Tuple[List[CheckResult], List[CheckResult], List[CheckResult]]:
        """
        更新错误状态并返回需要通知的变化
        
        Args:
            results: 检查结果列表
            
        Returns:
            (新增错误, 已恢复, 持续错误)
        """
        async with self.lock:
            # 保存上次的错误状态
            self.previous_errors = self.current_errors.copy()
            
            # 更新当前错误状态
            self.current_errors = {}
            current_healthy = set()
            
            for result in results:
                if not result.is_success:
                    self.current_errors[result.domain_name] = result
                else:
                    current_healthy.add(result.domain_name)
            
            # 计算变化
            new_errors = []  # 新增的错误
            recovered = []  # 已恢复的域名
            persistent_errors = []  # 持续错误的域名
            
            # 找出新增的错误
            for domain, result in self.current_errors.items():
                if domain not in self.previous_errors:
                    new_errors.append(result)
                    # 添加到历史记录
                    self.add_to_history(result, is_new_error=True)
                else:
                    # 检查错误类型是否改变
                    if self.previous_errors[domain].status != result.status:
                        new_errors.append(result)
                        self.add_to_history(result, is_new_error=True)
                    else:
                        persistent_errors.append(result)
            
            # 找出已恢复的域名
            for domain, result in self.previous_errors.items():
                if domain in current_healthy:
                    # 创建恢复记录
                    recovered_result = CheckResult(
                        domain_name=domain,
                        url=result.url,
                        status=CheckStatus.SUCCESS,
                        is_success=True,
                        response_time=0,
                        checked_at=datetime.now()
                    )
                    recovered.append(recovered_result)
                    # 添加恢复记录到历史
                    self.add_to_history(recovered_result, is_recovery=True)
                    # 从已确认列表中移除
                    self.acknowledged_errors.discard(domain)
            
            # 保存历史记录
            self.save_history()
            
            return new_errors, recovered, persistent_errors
    
    def add_to_history(self, result: CheckResult, is_new_error: bool = False, is_recovery: bool = False):
        """添加到历史记录"""
        record = DomainHistory(
            domain_name=result.domain_name,
            status="recovered" if is_recovery else result.status.value,
            error_type=None if is_recovery else result.status.value,
            timestamp=datetime.now().isoformat(),
            acknowledged=False,
            notes="域名已恢复正常" if is_recovery else result.error_message
        )
        self.history.append(record)
        
        # 限制历史记录数量
        max_records = 10000
        if len(self.history) > max_records:
            self.history = self.history[-max_records:]
    
    def acknowledge_error(self, domain: str, notes: Optional[str] = None):
        """
        确认处理错误
        
        Args:
            domain: 域名
            notes: 处理备注
        """
        self.acknowledged_errors.add(domain)
        
        # 更新历史记录中的确认状态
        for record in reversed(self.history):
            if record.domain_name == domain and not record.acknowledged:
                record.acknowledged = True
                record.acknowledged_time = datetime.now().isoformat()
                if notes:
                    record.notes = notes
                break
        
        self.save_history()
        self.logger.info(f"已确认处理域名 {domain} 的错误")
    
    def get_unacknowledged_errors(self) -> List[CheckResult]:
        """获取未确认处理的错误"""
        unacknowledged = []
        for domain, result in self.current_errors.items():
            if domain not in self.acknowledged_errors:
                unacknowledged.append(result)
        return unacknowledged
    
    def get_acknowledged_errors(self) -> List[CheckResult]:
        """获取已确认处理的错误"""
        acknowledged = []
        for domain, result in self.current_errors.items():
            if domain in self.acknowledged_errors:
                acknowledged.append(result)
        return acknowledged
    
    def get_history(self, domain: Optional[str] = None, days: Optional[int] = None) -> List[DomainHistory]:
        """
        获取历史记录
        
        Args:
            domain: 指定域名，None表示所有域名
            days: 查询天数，None表示所有
            
        Returns:
            历史记录列表
        """
        records = self.history
        
        # 按域名过滤
        if domain:
            records = [r for r in records if r.domain_name == domain]
        
        # 按时间过滤
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            records = [
                r for r in records
                if datetime.fromisoformat(r.timestamp) > cutoff_date
            ]
        
        return records
    
    def get_statistics(self, days: int = 7) -> Dict:
        """
        获取统计信息
        
        Args:
            days: 统计天数
            
        Returns:
            统计信息字典
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_records = [
            r for r in self.history
            if datetime.fromisoformat(r.timestamp) > cutoff_date
        ]
        
        # 统计各类错误
        error_counts = {}
        recovery_count = 0
        
        for record in recent_records:
            if record.status == "recovered":
                recovery_count += 1
            elif record.error_type:
                error_counts[record.error_type] = error_counts.get(record.error_type, 0) + 1
        
        # 统计最常出错的域名
        domain_errors = {}
        for record in recent_records:
            if record.status != "recovered":
                domain_errors[record.domain_name] = domain_errors.get(record.domain_name, 0) + 1
        
        top_error_domains = sorted(domain_errors.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            'total_errors': len([r for r in recent_records if r.status != "recovered"]),
            'total_recoveries': recovery_count,
            'error_types': error_counts,
            'top_error_domains': top_error_domains,
            'current_errors': len(self.current_errors),
            'acknowledged_errors': len(self.acknowledged_errors),
            'unacknowledged_errors': len(self.current_errors) - len(self.acknowledged_errors)
        }