# 性能优化指南

## 🚀 优化特性

### 1. 连接池复用
- 使用 `httpx.AsyncClient` 维持长连接
- 减少 TCP 握手开销
- 支持 HTTP/2 多路复用

### 2. 批量并发处理
- 分批执行避免资源耗尽
- 可配置最大并发数
- 智能任务调度

### 3. 自适应并发控制
- 根据 CPU 使用率动态调整
- 根据内存使用率自动限制
- 防止系统过载

### 4. 智能重试机制
- 仅重试可恢复错误（超时、连接错误）
- 不重试永久性错误（DNS、HTTP错误、SSL错误）
- 节省检查时间

## ⚙️ 配置优化

### 小规模部署（<100 域名）
```json
{
  "check": {
    "interval_minutes": 30,
    "max_concurrent": 10,
    "timeout_seconds": 10,
    "retry_count": 2,
    "auto_adjust_concurrent": false
  }
}
```
- 资源需求：1核 1G内存
- 检查耗时：约1-2分钟

### 中等规模（100-500 域名）
```json
{
  "check": {
    "interval_minutes": 20,
    "max_concurrent": 30,
    "timeout_seconds": 8,
    "retry_count": 1,
    "auto_adjust_concurrent": true
  }
}
```
- 资源需求：2核 2G内存
- 检查耗时：约3-5分钟

### 大规模部署（>500 域名）
```json
{
  "check": {
    "interval_minutes": 10,
    "max_concurrent": 50,
    "timeout_seconds": 5,
    "retry_count": 1,
    "auto_adjust_concurrent": true,
    "batch_notify": false
  }
}
```
- 资源需求：4核 4G内存
- 检查耗时：约5-10分钟

## 📊 性能指标

### 并发数影响
| 并发数 | 100域名耗时 | 500域名耗时 | CPU使用率 | 内存使用 |
|--------|-------------|-------------|-----------|----------|
| 10 | 60秒 | 300秒 | 20% | 100MB |
| 20 | 30秒 | 150秒 | 40% | 150MB |
| 50 | 15秒 | 60秒 | 70% | 250MB |
| 100 | 10秒 | 30秒 | 90% | 400MB |

### 超时设置影响
- 5秒：快速失败，可能误报
- 10秒：平衡选择（推荐）
- 15秒：宽松，减少误报
- 30秒：非常宽松，适合网络差环境

## 🔧 优化技巧

### 1. HTTP/2 优化
安装 h2 包启用 HTTP/2：
```bash
pip install h2
```
优势：
- 多路复用减少连接数
- 头部压缩减少传输量
- 服务器推送（如支持）

### 2. 系统优化

#### Linux 内核参数
```bash
# 增加文件描述符限制
ulimit -n 65535

# 优化 TCP 参数
sysctl -w net.ipv4.tcp_fin_timeout=30
sysctl -w net.ipv4.tcp_keepalive_time=1200
sysctl -w net.core.somaxconn=1024
```

#### Windows 优化
- 增加线程池大小
- 调整 TCP 动态端口范围
- 禁用不必要的网络协议

### 3. 代码级优化

#### 批处理优化
```python
# 当前实现
batch_size = max_concurrent
batches = (total_domains + batch_size - 1) // batch_size
```

#### 缓存优化
- LRU 缓存最近1000个域名状态
- 避免内存无限增长
- 自动清理旧数据

### 4. 网络优化

#### DNS 优化
- 使用本地 DNS 缓存
- 配置多个 DNS 服务器
- 考虑使用 DoH/DoT

#### 代理设置
```python
# 如需代理
client = httpx.AsyncClient(
    proxy="http://proxy.example.com:8080"
)
```

## 📈 监控建议

### 关键指标
1. **检查耗时**：每轮检查总时间
2. **成功率**：正常域名百分比
3. **响应时间**：平均响应时间
4. **资源使用**：CPU/内存占用

### 告警阈值
- 检查耗时 > interval_minutes * 0.8
- CPU 使用率 > 80%
- 内存使用 > 1GB
- 失败率 > 10%

## 🎯 最佳实践

### DO ✅
1. 根据域名数量调整并发数
2. 启用自适应并发控制
3. 合理设置超时时间
4. 定期清理日志文件
5. 监控系统资源使用

### DON'T ❌
1. 并发数设置过高（>100）
2. 超时时间过短（<3秒）
3. 重试次数过多（>5）
4. 忽略系统资源限制
5. 不设置告警冷却时间

## 🔬 性能测试

### 测试脚本
```python
# 测试不同并发数的性能
import time
import asyncio
from domain_checker import DomainChecker

async def test_performance():
    checker = DomainChecker()
    domains = ["example.com"] * 100  # 100个域名
    
    for concurrent in [10, 20, 50]:
        checker.max_concurrent = concurrent
        start = time.time()
        await checker.check_domains_batch(domains)
        elapsed = time.time() - start
        print(f"并发{concurrent}: {elapsed:.2f}秒")

asyncio.run(test_performance())
```

### 压力测试
```bash
# 模拟大量域名
python -c "
domains = ['test{}.com'.format(i) for i in range(1000)]
import json
with open('test_domains.json', 'w') as f:
    json.dump({'domains': domains}, f)
"
```

## 🆘 常见性能问题

### 问题1：检查时间过长
**症状**：检查耗时超过间隔时间
**解决**：
1. 增加 max_concurrent
2. 减少 timeout_seconds
3. 减少 retry_count
4. 启用 auto_adjust_concurrent

### 问题2：内存占用过高
**症状**：内存使用持续增长
**解决**：
1. 减少 max_concurrent
2. 检查是否有内存泄漏
3. 定期重启服务
4. 使用更大内存服务器

### 问题3：CPU 使用率过高
**症状**：CPU 持续 90%+
**解决**：
1. 减少 max_concurrent
2. 增加检查间隔
3. 优化代码逻辑
4. 升级服务器配置

### 问题4：网络错误频繁
**症状**：大量超时或连接错误
**解决**：
1. 检查网络带宽
2. 增加 timeout_seconds
3. 减少 max_concurrent
4. 使用更稳定的网络

## 📚 延伸阅读

- [Python asyncio 最佳实践](https://docs.python.org/3/library/asyncio.html)
- [HTTP/2 性能优化](https://http2.github.io/)
- [Linux 网络调优](https://www.kernel.org/doc/Documentation/networking/)
- [系统性能监控工具](https://github.com/giampaolo/psutil)