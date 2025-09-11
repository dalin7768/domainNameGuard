#!/usr/bin/env python3
"""
Cloudflare API 管理器
支持多用户API token管理和域名操作
整合了demo中的cloudflare_dns_export.py功能
"""

import asyncio
import json
import csv
import sys
import os
import time
import logging
from typing import List, Dict, Set, Optional, Any, Tuple
import httpx
from datetime import datetime
from pathlib import Path


class CloudflareTokenManager:
    """Cloudflare API Token 管理器"""
    
    def __init__(self, tokens_file: str = "cloudflare_tokens.json"):
        """
        初始化Token管理器
        
        Args:
            tokens_file: Token存储文件路径
        """
        self.tokens_file = tokens_file
        self.tokens_data = self._load_tokens()
        self.logger = logging.getLogger(__name__)
    
    def _load_tokens(self) -> Dict[str, Dict]:
        """加载Token数据"""
        if os.path.exists(self.tokens_file):
            try:
                with open(self.tokens_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加载Token文件失败: {e}")
        
        return {
            "users": {},  # 格式: {telegram_user_id: {"tokens": [{"name": "...", "token": "...", "permissions": [...]}]}}
            "global_tokens": []  # 全局可用的token
        }
    
    def _save_tokens(self) -> bool:
        """保存Token数据"""
        try:
            with open(self.tokens_file, 'w', encoding='utf-8') as f:
                json.dump(self.tokens_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"保存Token文件失败: {e}")
            return False
    
    def add_user_token(self, user_id: str, token_name: str, api_token: str, permissions: Optional[List[str]] = None) -> Tuple[bool, str]:
        """
        为用户添加API Token
        
        Args:
            user_id: Telegram用户ID
            token_name: Token名称
            api_token: Cloudflare API Token
            permissions: Token权限列表
            
        Returns:
            (成功状态, 消息)
        """
        if user_id not in self.tokens_data["users"]:
            self.tokens_data["users"][user_id] = {"tokens": []}
        
        # 检查token名称是否重复
        user_tokens = self.tokens_data["users"][user_id]["tokens"]
        for token in user_tokens:
            if token["name"] == token_name:
                return False, f"Token名称 '{token_name}' 已存在"
        
        # 添加新token
        new_token = {
            "name": token_name,
            "token": api_token,
            "permissions": permissions or ["Zone:Read", "DNS:Read"],
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        user_tokens.append(new_token)
        
        if self._save_tokens():
            return True, f"成功添加Token '{token_name}'"
        else:
            return False, "保存Token失败"
    
    def remove_user_token(self, user_id: str, token_name: str) -> Tuple[bool, str]:
        """
        删除用户的API Token
        
        Args:
            user_id: Telegram用户ID
            token_name: Token名称
            
        Returns:
            (成功状态, 消息)
        """
        if user_id not in self.tokens_data["users"]:
            return False, "用户没有Token"
        
        user_tokens = self.tokens_data["users"][user_id]["tokens"]
        for i, token in enumerate(user_tokens):
            if token["name"] == token_name:
                del user_tokens[i]
                if self._save_tokens():
                    return True, f"成功删除Token '{token_name}'"
                else:
                    return False, "保存失败"
        
        return False, f"未找到Token '{token_name}'"
    
    def get_user_tokens(self, user_id: str) -> List[Dict]:
        """获取用户的所有Token"""
        if user_id not in self.tokens_data["users"]:
            return []
        return self.tokens_data["users"][user_id]["tokens"]
    
    def get_user_token(self, user_id: str, token_name: str) -> Optional[str]:
        """获取指定用户的指定Token"""
        tokens = self.get_user_tokens(user_id)
        for token in tokens:
            if token["name"] == token_name and token["status"] == "active":
                return token["token"]
        return None
    
    def list_user_tokens(self, user_id: str) -> str:
        """列出用户的所有Token"""
        tokens = self.get_user_tokens(user_id)
        if not tokens:
            return "您还没有添加任何API Token"
        
        result = f"📋 **您的API Token列表**:\n\n"
        for i, token in enumerate(tokens, 1):
            status_emoji = "🟢" if token["status"] == "active" else "🔴"
            result += f"{i}. {status_emoji} **{token['name']}**\n"
            result += f"   权限: {', '.join(token.get('permissions', []))}\n"
            result += f"   创建时间: {token['created_at'][:10]}\n\n"
        
        return result


class CloudflareAPIClient:
    """Cloudflare API 客户端"""
    
    def __init__(self, api_token: str):
        """
        初始化API客户端
        
        Args:
            api_token: Cloudflare API Token
        """
        self.api_token = api_token
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        self.logger = logging.getLogger(__name__)
    
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None, method: str = "GET") -> Dict:
        """
        发送API请求
        
        Args:
            endpoint: API端点
            params: 请求参数
            method: HTTP方法
            
        Returns:
            API响应数据
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if method == "GET":
                    response = await client.get(url, headers=self.headers, params=params)
                elif method == "POST":
                    response = await client.post(url, headers=self.headers, json=params)
                elif method == "PUT":
                    response = await client.put(url, headers=self.headers, json=params)
                elif method == "DELETE":
                    response = await client.delete(url, headers=self.headers)
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")
                
                response.raise_for_status()
                data = response.json()
                
                if not data.get("success"):
                    errors = data.get("errors", [])
                    error_msg = "; ".join([e.get("message", str(e)) for e in errors])
                    raise Exception(f"API请求失败: {error_msg}")
                
                return data
                
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP错误 {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"网络请求失败: {str(e)}")
    
    async def verify_token(self) -> Dict:
        """验证API Token"""
        try:
            data = await self._make_request("/user/tokens/verify")
            return {
                "valid": True,
                "token_id": data.get("result", {}).get("id"),
                "status": data.get("result", {}).get("status")
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    async def get_user_info(self) -> Dict:
        """获取用户信息"""
        data = await self._make_request("/user")
        return data.get("result", {})
    
    async def get_zones(self) -> List[Dict]:
        """获取所有域名zones"""
        zones = []
        page = 1
        
        while True:
            params = {
                "page": page,
                "per_page": 50,
                "status": "active"
            }
            
            data = await self._make_request("/zones", params)
            result = data.get("result", [])
            zones.extend(result)
            
            result_info = data.get("result_info", {})
            total_pages = result_info.get("total_pages", 1)
            
            if page >= total_pages:
                break
            
            page += 1
        
        return zones
    
    async def get_dns_records(self, zone_id: str, record_type: Optional[str] = None) -> List[Dict]:
        """获取DNS记录"""
        records = []
        page = 1
        
        while True:
            params = {
                "page": page,
                "per_page": 100
            }
            
            if record_type:
                params["type"] = record_type
            
            data = await self._make_request(f"/zones/{zone_id}/dns_records", params)
            result = data.get("result", [])
            records.extend(result)
            
            result_info = data.get("result_info", {})
            total_pages = result_info.get("total_pages", 1)
            
            if page >= total_pages:
                break
            
            page += 1
        
        return records
    
    async def export_all_domains(self, output_format: str = "txt", record_types: Optional[List[str]] = None) -> Dict:
        """
        导出所有域名
        
        Args:
            output_format: 输出格式 (txt, json, csv)
            record_types: 记录类型筛选
            
        Returns:
            导出结果
        """
        try:
            # 获取所有zones
            zones = await self.get_zones()
            if not zones:
                return {"success": False, "error": "未找到任何域名", "domains": []}
            
            all_domains = set()
            zone_info = []
            
            # 处理每个zone
            for zone in zones:
                zone_id = zone.get("id")
                zone_name = zone.get("name")
                
                if not zone_id or not zone_name:
                    continue
                
                # 获取DNS记录
                dns_records = await self.get_dns_records(zone_id)
                
                zone_domains = set()
                for record in dns_records:
                    record_name = record.get("name", "")
                    record_type = record.get("type", "")
                    
                    if record_name and (not record_types or record_type in record_types):
                        # 排除通配符记录
                        if "*" not in record_name:
                            all_domains.add(record_name)
                            zone_domains.add(record_name)
                
                zone_info.append({
                    "zone_name": zone_name,
                    "zone_id": zone_id,
                    "domain_count": len(zone_domains),
                    "domains": sorted(list(zone_domains))
                })
            
            # 转换为列表并排序
            domain_list = sorted(list(all_domains))
            
            return {
                "success": True,
                "total_zones": len(zones),
                "total_domains": len(domain_list),
                "domains": domain_list,
                "zone_info": zone_info,
                "export_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "domains": []}


class CloudflareManager:
    """Cloudflare管理器主类"""
    
    def __init__(self, tokens_file: str = "cloudflare_tokens.json", config_manager=None):
        """
        初始化Cloudflare管理器
        
        Args:
            tokens_file: Token存储文件
            config_manager: 配置管理器实例
        """
        self.token_manager = CloudflareTokenManager(tokens_file)
        self.config_manager = config_manager
        self.logger = logging.getLogger(__name__)
    
    async def verify_user_token(self, user_id: str, token_name: str) -> Dict:
        """验证用户Token"""
        token = self.token_manager.get_user_token(user_id, token_name)
        if not token:
            return {"valid": False, "error": f"未找到Token '{token_name}'"}
        
        client = CloudflareAPIClient(token)
        return await client.verify_token()
    
    async def get_user_zones(self, user_id: str, token_name: str) -> Dict:
        """获取用户的域名zones"""
        token = self.token_manager.get_user_token(user_id, token_name)
        if not token:
            return {"success": False, "error": f"未找到Token '{token_name}'"}
        
        try:
            client = CloudflareAPIClient(token)
            zones = await client.get_zones()
            return {
                "success": True,
                "zones": zones,
                "total": len(zones)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def export_user_domains(self, user_id: str, token_name: str, output_format: str = "txt", record_types: Optional[List[str]] = None) -> Dict:
        """导出用户的所有域名"""
        token = self.token_manager.get_user_token(user_id, token_name)
        if not token:
            return {"success": False, "error": f"未找到Token '{token_name}'"}
        
        try:
            client = CloudflareAPIClient(token)
            return await client.export_all_domains(output_format, record_types)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def save_domains_to_file(self, domains: List[str], filename: str, format_type: str = "txt") -> bool:
        """保存域名列表到文件"""
        try:
            if format_type == "txt":
                with open(filename, "w", encoding="utf-8") as f:
                    for domain in domains:
                        f.write(f"{domain}\n")
            
            elif format_type == "json":
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(domains, f, indent=2, ensure_ascii=False)
            
            elif format_type == "csv":
                with open(filename, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["domain"])
                    for domain in domains:
                        writer.writerow([domain])
            
            else:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")
            return False
    
    def _get_export_config(self) -> Dict:
        """获取导出配置"""
        default_config = {
            "output_dir": "exports",
            "default_format": "json",
            "include_timestamp": False,
            "single_file_name": "cf_domains_{token_name}.{format}",
            "merged_file_name": "cf_all_domains.{format}",
            "auto_create_dir": True,
            "sync_delete": True
        }
        
        if self.config_manager:
            try:
                cf_config = self.config_manager.config.get("cloudflare", {}).get("export", {})
                default_config.update(cf_config)
            except Exception as e:
                self.logger.warning(f"读取导出配置失败，使用默认配置: {e}")
        
        return default_config
    
    def _get_merge_config(self) -> Dict:
        """获取合并配置"""
        default_config = {
            "default_mode": "replace",
            "auto_format_domains": True,
            "confirm_replace": False
        }
        
        if self.config_manager:
            try:
                merge_config = self.config_manager.config.get("cloudflare", {}).get("merge", {})
                default_config.update(merge_config)
            except Exception as e:
                self.logger.warning(f"读取合并配置失败，使用默认配置: {e}")
        
        return default_config
    
    def _prepare_export_path(self, filename: str) -> str:
        """准备导出路径"""
        config = self._get_export_config()
        output_dir = config["output_dir"]
        
        if config["auto_create_dir"] and output_dir:
            import os
            os.makedirs(output_dir, exist_ok=True)
            return os.path.join(output_dir, filename)
        
        return filename
    
    def _generate_filename(self, template: str, token_name: str = None, format_type: str = "json") -> str:
        """生成文件名"""
        config = self._get_export_config()
        
        # 替换模板变量
        filename = template.format(
            token_name=token_name or "unknown",
            format=format_type
        )
        
        # 添加时间戳
        if config["include_timestamp"]:
            timestamp = datetime.now().strftime("_%Y%m%d_%H%M%S")
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            filename = f"{name}{timestamp}.{ext}" if ext else f"{filename}{timestamp}"
        
        return filename
    
    async def export_single_token_domains(self, user_id: str, token_name: str, format_type: str = None, sync_delete: bool = None) -> Dict:
        """
        导出单个Token的域名
        
        Args:
            user_id: 用户ID
            token_name: Token名称
            format_type: 导出格式，None时使用配置默认值
            sync_delete: 是否同步删除，None时使用配置默认值
            
        Returns:
            导出结果
        """
        try:
            config = self._get_export_config()
            format_type = format_type or config["default_format"]
            sync_delete = sync_delete if sync_delete is not None else config["sync_delete"]
            
            # 导出域名
            result = await self.export_user_domains(user_id, token_name, format_type)
            if not result["success"]:
                return result
            
            domains = result["domains"]
            
            # 生成文件名和路径
            filename = self._generate_filename(
                config["single_file_name"], 
                token_name, 
                format_type
            )
            filepath = self._prepare_export_path(filename)
            
            # 保存文件
            if self.save_domains_to_file(domains, filepath, format_type):
                result["export_file"] = filepath
                result["export_filename"] = filename
                
                # 同步删除功能
                if sync_delete and self.config_manager:
                    deleted_count = await self._sync_delete_domains(domains)
                    result["sync_delete_count"] = deleted_count
                
                return result
            else:
                return {"success": False, "error": "保存文件失败"}
                
        except Exception as e:
            self.logger.error(f"导出单个Token域名失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def export_all_user_tokens_domains(self, user_id: str, format_type: str = None, sync_delete: bool = None) -> Dict:
        """
        导出用户所有Token的域名（合并）
        
        Args:
            user_id: 用户ID
            format_type: 导出格式
            sync_delete: 是否同步删除
            
        Returns:
            导出结果
        """
        try:
            config = self._get_export_config()
            format_type = format_type or config["default_format"]
            sync_delete = sync_delete if sync_delete is not None else config["sync_delete"]
            
            # 获取用户所有Token
            user_tokens = self.token_manager.get_user_tokens(user_id)
            if not user_tokens:
                return {"success": False, "error": "用户没有可用的Token"}
            
            all_domains = set()
            token_results = {}
            total_zones = 0
            
            # 逐个导出所有Token的域名
            for token_info in user_tokens:
                token_name = token_info["name"]
                
                result = await self.export_user_domains(user_id, token_name, format_type)
                if result["success"]:
                    domains = set(result["domains"])
                    all_domains.update(domains)
                    total_zones += result.get("total_zones", 0)
                    
                    token_results[token_name] = {
                        "success": True,
                        "domains": list(domains),
                        "count": len(domains),
                        "zones": result.get("total_zones", 0)
                    }
                else:
                    token_results[token_name] = {
                        "success": False,
                        "error": result["error"]
                    }
            
            if not all_domains:
                return {"success": False, "error": "未获取到任何域名"}
            
            # 转换为排序列表
            domain_list = sorted(list(all_domains))
            
            # 生成合并文件名和路径
            filename = self._generate_filename(
                config["merged_file_name"], 
                format_type=format_type
            )
            filepath = self._prepare_export_path(filename)
            
            # 保存合并文件
            if self.save_domains_to_file(domain_list, filepath, format_type):
                result = {
                    "success": True,
                    "total_domains": len(domain_list),
                    "total_zones": total_zones,
                    "total_tokens": len(user_tokens),
                    "domains": domain_list,
                    "export_file": filepath,
                    "export_filename": filename,
                    "token_results": token_results,
                    "export_time": datetime.now().isoformat()
                }
                
                # 同步删除功能
                if sync_delete and self.config_manager:
                    deleted_count = await self._sync_delete_domains(domain_list)
                    result["sync_delete_count"] = deleted_count
                
                return result
            else:
                return {"success": False, "error": "保存合并文件失败"}
                
        except Exception as e:
            self.logger.error(f"导出所有Token域名失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _sync_delete_domains(self, cf_domains: List[str]) -> int:
        """
        同步删除功能：删除监控列表中CF已不存在的域名
        
        Args:
            cf_domains: CF中的域名列表
            
        Returns:
            删除的域名数量
        """
        if not self.config_manager:
            return 0
        
        try:
            # 获取当前监控的域名
            current_domains = set(self.config_manager.get_domains())
            cf_domains_set = set(cf_domains)
            
            # 找出需要删除的域名（在监控列表中但不在CF中）
            domains_to_delete = current_domains - cf_domains_set
            
            if not domains_to_delete:
                return 0
            
            # 执行删除
            deleted_count = 0
            for domain in domains_to_delete:
                if self.config_manager.remove_domain(domain):
                    deleted_count += 1
                    self.logger.info(f"同步删除域名: {domain}")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"同步删除域名失败: {e}")
            return 0
    
    async def export_and_merge_domains(self, user_id: str, token_name: str = None, merge_mode: str = None) -> Dict:
        """
        导出CF域名并直接合并到domains配置
        
        Args:
            user_id: 用户ID
            token_name: Token名称，None时导出所有Token
            merge_mode: 合并模式，None时使用配置默认值
            
        Returns:
            操作结果
        """
        if not self.config_manager:
            return {"success": False, "error": "配置管理器未初始化"}
        
        try:
            # 获取合并配置
            merge_config = self._get_merge_config()
            merge_mode = merge_mode or merge_config["default_mode"]
            # 导出域名
            if token_name:
                result = await self.export_user_domains(user_id, token_name)
            else:
                result = await self.export_all_user_tokens_domains(user_id)
            
            if not result["success"]:
                return result
            
            cf_domains = result["domains"]
            if not cf_domains:
                return {"success": False, "error": "未获取到任何域名"}
            
            # 确保域名格式正确（添加协议）
            formatted_domains = []
            if merge_config["auto_format_domains"]:
                for domain in cf_domains:
                    if not domain.startswith(('http://', 'https://')):
                        formatted_domains.append(f"https://{domain}")
                    else:
                        formatted_domains.append(domain)
            else:
                formatted_domains = cf_domains
            
            # 获取当前domains配置
            current_domains = set(self.config_manager.get_domains())
            cf_domains_set = set(formatted_domains)
            
            # 根据合并模式处理
            if merge_mode == "replace":
                # 替换模式：完全替换为CF域名
                final_domains = list(cf_domains_set)
                operation_desc = "替换"
                
            elif merge_mode == "merge":
                # 合并模式：合并现有域名和CF域名
                final_domains = list(current_domains | cf_domains_set)
                operation_desc = "合并"
                
            elif merge_mode == "add":
                # 添加模式：只添加新的CF域名
                new_domains = cf_domains_set - current_domains
                final_domains = list(current_domains | new_domains)
                operation_desc = "添加新域名"
                
            else:
                return {"success": False, "error": f"不支持的合并模式: {merge_mode}"}
            
            # 更新domains配置
            success = self.config_manager.update_domains(final_domains)
            if not success:
                return {"success": False, "error": "更新domains配置失败"}
            
            # 统计信息
            before_count = len(current_domains)
            after_count = len(final_domains)
            added_count = len(cf_domains_set - current_domains)
            removed_count = len(current_domains - set(final_domains))
            
            return {
                "success": True,
                "operation": operation_desc,
                "merge_mode": merge_mode,
                "cf_domains_count": len(cf_domains),
                "before_count": before_count,
                "after_count": after_count,
                "added_count": added_count,
                "removed_count": removed_count,
                "cf_domains": cf_domains,
                "token_name": token_name or "所有Token",
                "export_time": result.get("export_time")
            }
            
        except Exception as e:
            self.logger.error(f"导出并合并域名失败: {e}")
            return {"success": False, "error": str(e)}


# 使用示例
async def main():
    """测试示例"""
    manager = CloudflareManager()
    
    # 添加用户Token
    user_id = "123456789"
    success, msg = manager.token_manager.add_user_token(
        user_id=user_id,
        token_name="主账号",
        api_token="your_api_token_here",
        permissions=["Zone:Read", "DNS:Read"]
    )
    print(f"添加Token: {msg}")
    
    # 验证Token
    result = await manager.verify_user_token(user_id, "主账号")
    print(f"Token验证: {result}")
    
    # 导出域名
    if result.get("valid"):
        export_result = await manager.export_user_domains(user_id, "主账号")
        if export_result["success"]:
            print(f"导出成功，共 {export_result['total_domains']} 个域名")
            # 保存到文件
            manager.save_domains_to_file(
                export_result["domains"],
                "exported_domains.txt",
                "txt"
            )
        else:
            print(f"导出失败: {export_result['error']}")


if __name__ == "__main__":
    asyncio.run(main())