# 域名监控服务 (Domain Monitor)

一个基于 Python 的异步域名监控服务，支持批量检查域名可用性并通过 Telegram Bot 发送通知。

## ✨ 功能特性

- 🔍 **批量域名监控** - 支持同时监控数百个域名
- ⚡ **高性能异步检查** - 使用 asyncio 和连接池技术
- 📱 **Telegram 机器人** - 实时通知和远程控制
- 🔄 **自适应并发** - 根据系统资源自动调整并发数
- 📊 **智能重试** - 仅对超时和连接错误进行重试
- 🎯 **灵活配置** - 支持热重载，无需重启服务
- 📈 **进度显示** - 实时显示检查进度和预计完成时间
- 🛡️ **生产就绪** - 支持多种部署方式（systemd/Docker/PM2）

## 🚀 快速开始

### 1. 克隆项目
```bash
git clone <repository_url>
cd domain-monitor
```

### 2. 安装依赖
```bash
# Windows
scripts\install_deps.bat

# Linux/Mac
pip install -r requirements.txt
```

### 3. 配置服务
复制配置示例并编辑：
```bash
cp config_example.json config.json
```

编辑 `config.json`，填入你的 Telegram Bot Token 和 Chat ID：
```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  }
}
```

### 4. 运行服务

#### 开发环境
```bash
python src/main.py
```

#### 生产环境

**Linux一键部署：**
```bash
chmod +x deploy.sh
./deploy.sh
```

**Windows一键部署：**
```batch
deploy.bat
```

## 📁 项目结构

```
domain-monitor/
├── src/                    # 源代码目录
│   ├── main.py            # 主程序入口
│   ├── domain_checker.py  # 域名检查核心模块
│   ├── telegram_bot.py    # Telegram机器人模块
│   ├── telegram_notifier.py # 通知发送模块
│   └── config_manager.py  # 配置管理模块
├── docs/                   # 文档
│   ├── CONFIG_GUIDE.md    # 配置指南
│   └── OPTIMIZATION.md    # 优化说明
├── scripts/                # 工具脚本
│   ├── install_deps.bat   # Windows依赖安装
│   └── clean_logs.bat     # Windows日志清理
├── deploy.sh              # Linux一键部署脚本
├── deploy.bat             # Windows一键部署脚本
├── config.json            # 配置文件（需创建）
├── config_example.json    # 配置示例
├── requirements.txt       # Python依赖
└── README.md             # 本文档
```

## 🤖 Telegram 机器人命令

### 基础命令
- `/help` - 显示帮助信息
- `/status` - 查看监控状态
- `/list` - 查看所有监控域名

### 域名管理
- `/add example.com` - 添加域名（支持批量）
- `/remove example.com` - 删除域名（支持批量）
- `/clear` - 清空所有域名
- `/check` - 立即执行检查

### 配置管理
- `/config` - 显示当前配置
- `/interval 10` - 设置检查间隔（分钟）
- `/timeout 15` - 设置超时时间（秒）
- `/retry 2` - 设置重试次数
- `/reload` - 重新加载配置

### 管理员命令
- `/admin add @username` - 添加管理员
- `/admin remove @username` - 移除管理员
- `/stop` - 停止监控服务

## ⚙️ 配置说明

### 核心配置
```json
{
  "telegram": {
    "bot_token": "Bot Token",
    "chat_id": "群组ID",
    "admin_users": ["@admin1", "@admin2"]
  },
  "check": {
    "interval_minutes": 30,        // 检查间隔
    "max_concurrent": 10,           // 最大并发数
    "timeout_seconds": 14,          // 超时时间
    "retry_count": 2,               // 重试次数
    "auto_adjust_concurrent": true  // 自适应并发
  },
  "domains": [
    "example.com",
    "test.com"
  ],
  "notification": {
    "notify_on_recovery": true,    // 恢复时通知
    "failure_threshold": 1,        // 失败阈值
    "cooldown_minutes": 20         // 冷却时间
  }
}
```

详细配置说明请参见 [配置指南](docs/CONFIG_GUIDE.md)

## 📊 性能优化

- **连接池复用** - 减少连接建立开销
- **HTTP/2支持** - 提升传输效率（需安装h2）
- **智能重试** - 仅重试可恢复的错误
- **批量处理** - 分批检查避免资源耗尽
- **自适应并发** - 根据CPU和内存动态调整

### 推荐配置
- **小型部署** (<100域名): 1核1G内存
- **中型部署** (100-500域名): 2核2G内存
- **大型部署** (>500域名): 4核4G内存

## 🔧 故障排查

### 常见问题

1. **Telegram消息发送失败**
   - 检查 Bot Token 是否正确
   - 确认 Chat ID 格式正确（群组ID应为负数）
   - 验证机器人已加入群组并有发送权限

2. **域名检查超时**
   - 增加 timeout_seconds 配置
   - 减少 max_concurrent 并发数
   - 检查网络连接

3. **内存占用过高**
   - 启用 auto_adjust_concurrent
   - 减少 max_concurrent 值
   - 检查域名列表是否过大

## 📈 监控消息示例

### 检查完成通知
```
⚠️ 域名检查完成

📊 统计信息
🔍 检查总数: 68 个
✅ 正常: 65 个
❌ 异常: 3 个

⏱️ 请求超时 (2个):
  • example1.com (请求超时（14秒，已重试2次）)
  • example2.com (连接建立超时（14秒，已重试1次）)

❌ HTTP错误 (1个):
  • example3.com [526]

⏰ 2024-01-01 12:00:00
```

## 📝 开发说明

### 环境要求
- Python 3.8+
- pip
- venv（推荐）

### 核心模块
- `DomainMonitor` - 主程序协调器
- `DomainChecker` - 域名检测引擎
- `TelegramBot` - 机器人命令处理
- `TelegramNotifier` - 通知发送器
- `ConfigManager` - 配置管理器

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 支持

如有问题或建议，请提交 Issue。