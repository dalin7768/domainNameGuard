# 域名监控程序

一个用于监控多个域名可用性并通过 Telegram 发送告警的 Python 程序。

## 功能特性

- ✅ 批量域名可用性检测
- ✅ 支持 HTTP/HTTPS 协议
- ✅ 自动重试机制
- ✅ Telegram 群组告警通知
- ✅ 域名恢复通知
- ✅ 告警冷却期控制（避免频繁告警）
- ✅ 详细的错误分类（DNS错误、连接错误、超时、SSL错误等）
- ✅ 配置文件管理
- ✅ 日志记录与轮转
- ✅ 并发检测提高效率

## 安装步骤

### 1. 环境要求

- Python 3.7 或更高版本
- pip 包管理器

### 2. 安装依赖

```bash
cd D:\pythonWorkSpace\domain
pip install -r requirements.txt
```

### 3. 配置 Telegram Bot

1. 在 Telegram 中找到 @BotFather
2. 发送 `/newbot` 创建新的 Bot
3. 设置 Bot 名称和用户名
4. 获取 Bot Token（格式如：`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`）

### 4. 获取 Telegram 群组 ID

1. 将 Bot 添加到目标群组
2. 在群组中发送一条消息
3. 访问 `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. 找到 `"chat":{"id":-1001234567890}`，这个负数就是群组 ID

### 5. 配置文件设置

编辑 `config.yaml` 文件：

```yaml
telegram:
  bot_token: "YOUR_BOT_TOKEN_HERE"  # 替换为你的 Bot Token
  chat_id: "-1001234567890"  # 替换为你的群组 ID

check:
  interval_minutes: 30  # 检查间隔
  timeout_seconds: 10   # 请求超时时间
  retry_count: 2        # 重试次数

domains:
  - name: "网站名称"
    url: "https://example.com"
    expected_status_codes: [200, 301]  # 期望的状态码
```

## 使用方法

### 启动监控

```bash
python main.py
```

程序会：
1. 加载配置文件
2. 测试 Telegram 连接
3. 执行首次域名检查
4. 按照设定的时间间隔定期检查

### 停止监控

按 `Ctrl+C` 即可优雅停止程序。

## 配置说明

### 主要配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `telegram.bot_token` | Telegram Bot Token | 必填 |
| `telegram.chat_id` | 群组或频道 ID | 必填 |
| `check.interval_minutes` | 检查间隔（分钟） | 30 |
| `check.timeout_seconds` | 请求超时（秒） | 10 |
| `check.retry_count` | 失败重试次数 | 2 |
| `notification.failure_threshold` | 连续失败多少次后告警 | 2 |
| `notification.cooldown_minutes` | 告警冷却时间（分钟） | 60 |
| `notification.notify_on_recovery` | 是否发送恢复通知 | true |

### 域名配置

每个域名可以配置：
- `name`: 域名的显示名称
- `url`: 要检查的完整 URL
- `expected_status_codes`: 正常的 HTTP 状态码列表

## 告警消息示例

### 域名异常告警

```
🔌 域名监控告警

📛 域名: Example Site
🔗 URL: https://example.com
⚠️ 错误类型: connection_error
📝 错误描述: 
连接错误：无法建立与服务器的连接
详细信息：Connection refused
🕐 检测时间: 2024-01-01 12:00:00

💡 建议: 请检查服务器是否在线，防火墙设置是否正确
```

### 域名恢复通知

```
✅ 域名恢复正常

📛 域名: Example Site
🔗 URL: https://example.com
📊 状态码: 200
⚡ 响应时间: 0.45 秒
🕐 恢复时间: 2024-01-01 12:30:00
```

## 日志文件

程序会生成日志文件 `domain_monitor.log`，包含：
- 每次检查的结果
- 错误详情
- 告警发送记录

日志文件会自动轮转，默认保留 5 个备份文件，每个最大 10MB。

## 错误类型说明

| 错误类型 | 说明 | 可能原因 |
|----------|------|----------|
| `dns_error` | DNS 解析失败 | 域名不存在或 DNS 服务器问题 |
| `connection_error` | 连接错误 | 服务器离线或网络问题 |
| `timeout` | 请求超时 | 服务器响应慢或网络延迟 |
| `http_error` | HTTP 状态码异常 | 网站返回错误状态码 |
| `ssl_error` | SSL 证书错误 | 证书过期或配置错误 |

## 高级功能

### 1. 批量域名管理

可以在 `config.yaml` 中添加任意数量的域名：

```yaml
domains:
  - name: "主站"
    url: "https://www.example.com"
    expected_status_codes: [200]
  
  - name: "API 服务"
    url: "https://api.example.com/health"
    expected_status_codes: [200, 204]
  
  - name: "CDN 节点"
    url: "https://cdn.example.com"
    expected_status_codes: [200, 301, 302]
```

### 2. 告警策略

- **失败阈值**：连续失败 N 次才发送告警，避免偶发问题
- **冷却期**：同一域名在冷却期内不会重复告警
- **恢复通知**：域名恢复正常时发送通知

### 3. 性能优化

- 使用异步并发检测，支持大量域名
- 智能重试机制，临时问题自动恢复
- 连接池复用，减少资源消耗

## 故障排查

### Telegram 无法发送消息

1. 检查 Bot Token 是否正确
2. 确认 Bot 已加入群组
3. 验证群组 ID 格式（应为负数）
4. 检查网络是否能访问 Telegram API

### 域名检测总是失败

1. 使用浏览器访问域名确认是否正常
2. 检查 `expected_status_codes` 配置
3. 查看日志文件了解具体错误
4. 适当增加 `timeout_seconds` 值

### 程序无法启动

1. 确认 Python 版本 >= 3.7
2. 检查所有依赖是否已安装
3. 验证 `config.yaml` 格式是否正确
4. 查看控制台错误信息

## 项目结构

```
domain/
├── config.yaml           # 配置文件
├── main.py              # 主程序入口
├── domain_checker.py    # 域名检测模块
├── telegram_notifier.py # Telegram 通知模块
├── requirements.txt     # 依赖包列表
├── README.md           # 使用说明
└── domain_monitor.log  # 运行日志（自动生成）
```

## 开发说明

### 扩展功能建议

1. **多通知渠道**：支持邮件、钉钉、企业微信等
2. **Web 界面**：添加可视化监控面板
3. **数据持久化**：保存历史检测数据到数据库
4. **性能指标**：记录响应时间趋势
5. **自定义检查**：支持 POST 请求、Header 验证等

### 代码结构

- `DomainChecker`: 负责域名检测逻辑
- `TelegramNotifier`: 负责消息通知
- `DomainMonitor`: 主程序协调器

## 许可证

MIT License

## 支持

如有问题或建议，请提交 Issue 或 Pull Request。