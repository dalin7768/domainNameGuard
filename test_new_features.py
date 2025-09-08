import asyncio
import sys
sys.path.insert(0, 'src')

from domain_checker import DomainChecker, CheckStatus

async def test_features():
    """测试新功能"""
    checker = DomainChecker(timeout=10, retry_count=1)
    
    # 测试域名列表
    test_domains = [
        "https://www.google.com",  # 正常网站
        "wss://echo.websocket.org",  # WebSocket测试服务器
        "https://httpstat.us/522",  # 模拟522错误
        "https://httpstat.us/403",  # 模拟403错误
        "https://httpstat.us/500",  # 模拟500错误
    ]
    
    print("=" * 60)
    print("域名检测新功能测试")
    print("=" * 60)
    
    for domain in test_domains:
        print(f"\n测试域名: {domain}")
        result = await checker.check_single_domain(domain)
        
        print(f"状态: {result.status.value}")
        if result.status_code:
            print(f"HTTP状态码: {result.status_code}")
        
        # 显示详细错误描述
        if result.status != CheckStatus.SUCCESS:
            print(f"错误描述: {result.get_error_description()}")
        
        if result.response_time:
            print(f"响应时间: {result.response_time:.2f}秒")
        
        print("-" * 40)
    
    # 关闭连接池
    await checker.close_client()
    
    print("\n测试完成！")
    print("\n新功能说明：")
    print("1. WebSocket支持：可以检测wss://协议的域名")
    print("2. 详细HTTP错误：不同状态码有具体的中文描述")
    print("3. 安全检测：可识别钓鱼网站和浏览器安全警告")

if __name__ == "__main__":
    asyncio.run(test_features())