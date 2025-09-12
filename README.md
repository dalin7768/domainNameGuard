# 域名监控服务 (Domain Monitor)

一个功能强大的异步域名监控服务，集成Cloudflare API管理，支持批量检查域名可用性并通过Telegram Bot进行实时通知和远程控制。

## ✨ 核心功能

### 🔍 域名监控
- **批量域名监控** - 支持同时监控数百个域名
- **高性能异步检查** - 使用 asyncio 和连接池技术  
- **智能重试机制** - 仅对超时和连接错误进行重试
- **自适应并发控制** - 根据系统资源自动调整并发数
- **实时进度显示** - 显示检查进度和预计完成时间

### 🌐 Cloudflare 集成
- **多用户API Token管理** - 每个用户可管理多个Cloudflare账号
- **域名批量操作** - 获取、导出和同步域名到监控系统
- **权限验证** - Token有效性检查和权限验证
- **多格式导出** - 支持txt、json、csv格式域名导出

### 📱 Telegram Bot
- **实时通知** - 域名状态变化即时通知
- **远程控制** - 通过Telegram命令管理整个监控系统
- **热配置更新** - 大部分配置支持在线修改，无需重启
- **智能通知模式** - 支持完整模式和智能模式通知

### 🛡️ 生产特性
- **多种部署方式** - 支持systemd/Docker/PM2部署
- **配置热重载** - 支持配置文件动态更新
- **日志管理** - 轮转日志和可配置日志级别
- **错误追踪** - 详细的错误分类和统计

## 🚀 快速开始

### 环境要求
- Python 3.8+
- pip 和 venv（推荐）

### 1. 项目初始化
```bash
# 克隆项目
git clone <repository_url>
cd domain-monitor

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置设置
```bash
# 复制配置模板
cp config_example.json config.json
cp cloudflare_tokens.example.json cloudflare_tokens.json  # 可选，系统会自动创建
```

### 3. 基础配置
编辑 `config.json` 文件：
```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",      // 从 @BotFather 获取
    "chat_id": "-1001234567890",        // 群组ID（负数）
    "admin_users": ["@your_username"]   // 管理员用户名列表
  },
  "domains": [
    "https://example.com",
    "https://test.com"
  ],
  "check": {
    "interval_minutes": 30,
    "max_concurrent": 10,
    "timeout_seconds": 14
  }
}
```

### 4. 运行服务

#### 开发环境
```bash
python src/main.py
```

#### 生产环境部署

**Linux 一键部署：**
```bash
chmod +x deploy.sh
./deploy.sh
```

**Windows 一键部署：**
```batch
deploy.bat
```

## 📁 项目结构

```
domain-monitor/
├── src/                           # 源代码目录
│   ├── main.py                   # 主程序入口
│   ├── domain_checker.py         # 域名检查核心引擎
│   ├── telegram_bot.py           # Telegram机器人控制器
│   ├── telegram_notifier.py      # 通知发送器
│   ├── config_manager.py         # 配置管理器（支持热重载）
│   ├── cloudflare_manager.py     # Cloudflare API管理器
│   └── error_tracker.py          # 错误统计和追踪
├── config.json                   # 主配置文件
├── config_example.json           # 配置模板
├── domains.json                  # 外部域名列表文件（可选）
├── cloudflare_tokens.json        # Cloudflare Token存储
├── cloudflare_tokens.example.json # Token配置示例
├── deploy.sh                     # Linux部署脚本
├── deploy.bat                    # Windows部署脚本
├── requirements.txt              # Python依赖
└── README.md                     # 项目文档
```

## 🤖 Telegram Bot 命令参考

### 基础监控命令
- `/help` - 显示帮助信息
- `/start` - 启动消息和基本信息
- `/status` - 查看当前监控状态
- `/list` - 查看所有监控域名
- `/check` - 立即执行一次检查（防重复执行保护）
- `/stopcheck` - 停止当前正在进行的检查
- `/errors` - 查看当前错误状态
- `/history` - 查看历史记录
- `/ack [domain]` - 确认处理错误

### 域名管理（支持热更新）
- `/add example.com` - 添加域名到监控列表
- `/remove example.com` - 从监控列表删除域名
- `/clear` - 清空所有监控域名

### 配置管理（支持热更新）
- `/config` - 显示当前配置
- `/interval 30` - 设置检查间隔（分钟，1-1440）
- `/timeout 15` - 设置超时时间（秒，1-300）
- `/retry 3` - 设置重试次数（0-10）
- `/concurrent 20` - 设置并发数（1-100）
- `/autoadjust on` - 开启自适应并发
- `/reload` - 重新加载配置文件

### Cloudflare 集成命令
- `/cfhelp` - 查看Cloudflare功能帮助
- `/cftoken add 名称 TOKEN` - 添加API Token
- `/cftoken remove 名称` - 删除API Token
- `/cflist` - 查看我的Token列表
- `/cfverify 名称` - 验证Token有效性
- `/cfzones 名称` - 获取Token下的所有域名
- `/cfexport 名称 [格式] [sync]` - 导出单个Token域名
- `/cfexportall [格式] [sync]` - 导出所有Token域名到文件
- `/cfexportall merge|replace|add` - 导出所有Token域名并实时合并到配置
- `/cfsync [名称] [模式]` - 同步CF域名到监控配置（实时写入，低噪音通知）

### 系统管理命令
- `/admin list` - 查看管理员列表  
- `/admin add @username` - 添加管理员
- `/admin remove @username` - 移除管理员
- `/stop` - 停止监控服务
- `/restart` - 重启监控服务
- `/dailyreport` - 生成每日报告
- `/apikey` - 更新HTTP API密钥

## ⚙️ 详细配置说明

### 主配置文件 (config.json)

```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",       // 必填：Telegram Bot Token
    "chat_id": "-1001234567890",         // 必填：群组或用户ID
    "admin_users": ["@admin1"]           // 管理员列表，空则所有人可用
  },
  
  "check": {
    "interval_minutes": 30,              // 检查间隔（1-1440分钟）
    "max_concurrent": 10,                // 最大并发数（1-200）
    "auto_adjust_concurrent": true,      // 自适应并发控制
    "timeout_seconds": 14,               // 请求超时（1-300秒）
    "retry_count": 2,                    // 重试次数（0-10）
    "retry_delay_seconds": 5,            // 重试延迟
    "batch_notify": false,               // 分批通知
    "show_eta": true                     // 显示预计完成时间
  },
  
  "domains": [                           // 域名列表（或文件路径）
    "https://example.com",
    "https://test.com"
  ],
  // 或使用外部文件：
  // "domains": "domains.json",
  
  "notification": {
    "level": "smart",                    // 通知模式：smart/full
    "notify_on_recovery": true,          // 恢复时通知
    "failure_threshold": 2,              // 失败阈值
    "cooldown_minutes": 60,              // 冷却时间
    "quiet_on_success": false            // 成功时静默
  },
  
  "logging": {
    "level": "INFO",                     // 日志级别
    "file": "domain_monitor.log",        // 日志文件
    "max_size_mb": 10,                   // 最大文件大小
    "backup_count": 5                    // 备份文件数
  },
  
  "history": {
    "enabled": true,                     // 历史记录
    "retention_days": 30,                // 保留天数
    "max_records": 10000                 // 最大记录数
  },
  
  "daily_report": {
    "enabled": false,                    // 每日报告
    "time": "09:00"                      // 发送时间
  },
  
  "cloudflare": {
    "export": {
      "output_dir": "exports",           // 导出文件目录
      "default_format": "json",          // 默认导出格式：txt, json, csv
      "include_timestamp": false,        // 文件名是否包含时间戳
      "single_file_name": "cf_domains_{token_name}.{format}",  // 单个账号导出文件名模板
      "merged_file_name": "cf_all_domains.{format}",           // 合并导出文件名模板
      "auto_create_dir": true,           // 自动创建导出目录
      "sync_delete": true                // 同步删除：导出时删除CF中已不存在的域名
    }
  }
}
```

### 外部域名文件 (domains.json)
```json
[
  "https://example1.com",
  "https://example2.com",  
  "https://api.example.com"
]
```

### Cloudflare Token配置
```json
{
  "users": {
    "123456789": {                       // Telegram用户ID
      "tokens": [
        {
          "name": "主账号",              // 自定义名称
          "token": "your_token_here",    // API Token
          "permissions": ["Zone:Read", "DNS:Read"],
          "created_at": "2024-01-01T00:00:00",
          "status": "active"
        }
      ]
    }
  },
  "global_tokens": []                    // 全局Token（管理员）
}
```

## 🌐 Cloudflare 集成使用指南

### API Token 获取方法
1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 "My Profile" → "API Tokens"
3. 点击 "Create Token"
4. 选择 "Custom token" 模板
5. 设置权限：
   - **Account**: Zone:Read
   - **Zone**: Zone:Read, DNS:Read
6. 可选择特定域名或所有域名
7. 创建并复制Token

### 使用流程

#### 1. 添加Token
```
/cftoken add 主账号 your_cloudflare_api_token_here
```

#### 2. 验证Token
```
/cfverify 主账号
```

#### 3. 查看域名
```
/cfzones 主账号
```

#### 4. 导出域名
```
# 导出单个Token域名（使用配置默认格式）
/cfexport 主账号

# 导出为JSON格式并启用同步删除
/cfexport 主账号 json sync

# 导出所有Token域名到合并文件
/cfexportall json sync
```

#### 5. 同步到监控配置
```
# 指定Token的替换模式
/cfsync 主账号 replace

# 所有Token的替换模式（不填Token名称）
/cfsync replace

# 指定Token的合并模式
/cfsync 主账号 merge

# 所有Token的合并模式（不填Token名称）
/cfsync merge

# 指定Token的添加模式
/cfsync 主账号 add

# 所有Token的添加模式（不填Token名称）
/cfsync add
```

**cfsync 同步模式详解**：
- **`replace`** - 完全替换现有监控域名
  - 指定Token：用该Token域名替换所有现有域名
  - 不指定Token：用所有Token域名替换所有现有域名
- **`merge`** - 合并域名（保留现有 + 添加CF域名，去重）
  - 指定Token：保留现有域名，添加该Token的新域名
  - 不指定Token：保留现有域名，添加所有Token的新域名
- **`add`** - 仅添加新域名（只添加监控中不存在的CF域名）
  - 指定Token：只添加该Token中监控不存在的域名
  - 不指定Token：只添加所有Token中监控不存在的域名

**Token选择规则**：
- 指定Token名称：只处理该Token的域名
- 不指定Token名称：处理所有Token的域名

**注意**：cfsync 操作过程中采用低噪音通知策略，不会频繁发送进度通知，只在完成或出错时通知

### 导出功能详解

#### 单个Token导出 (`/cfexport`)
- **基本用法**: `/cfexport 主账号`
- **指定格式**: `/cfexport 主账号 json`
- **启用同步删除**: `/cfexport 主账号 json sync`
- **支持格式**: txt, json, csv
- **文件路径**: `exports/cf_domains_主账号.json`

#### 合并导出 (`/cfexportall`)
- **基本用法**: `/cfexportall`
- **指定格式**: `/cfexportall txt`
- **启用同步删除**: `/cfexportall json sync`
- **功能**: 合并所有Token的域名到一个文件
- **文件路径**: `exports/cf_all_domains.json`

#### 同步删除功能
- **作用**: 自动删除监控列表中CF已不存在的域名
- **触发**: 添加 `sync` 参数到导出命令
- **安全**: 只删除不在CF中但在监控列表中的域名

### 多账号管理示例
```bash
# 添加多个账号
/cftoken add 账号A token_a_here
/cftoken add 账号B token_b_here

# 查看所有Token
/cflist

# 分别导出域名
/cfexport 账号A json
/cfexport 账号B csv

# 合并导出所有账号域名
/cfexportall json sync

# 选择主要账号同步到监控配置
/cfsync 账号A replace
```

## 🌍 HTTP API 接口说明

### 接口配置
通过 `config.json` 中的 `http_api` 部分配置HTTP接口：

```json
{
  "http_api": {
    "enabled": true,                    // 启用HTTP API
    "host": "0.0.0.0",                 // 监听地址
    "port": 8080,                      // 监听端口
    "cors_enabled": true,              // 启用CORS
    "allowed_ips": [],                 // IP白名单，空则允许所有
    "rate_limit": {
      "enabled": true,
      "requests_per_minute": 60        // 频率限制
    },
    "auth": {
      "enabled": true,
      "api_key": "your-api-key-here"   // API密钥
    }
  }
}
```

### 可用接口

#### 1. 发送消息
- **URL**: `POST /sendMsg`
- **功能**: 通过Telegram Bot发送消息
- **认证**: 需要API密钥

**请求参数**：
```json
{
  "msg": "消息内容",                    // 必需：消息文本
  "parse_mode": "Markdown",           // 可选：解析模式，默认Markdown
  "disable_preview": true             // 可选：禁用链接预览，默认true
}
```

**响应示例**：
```json
{
  "success": true,
  "message": "消息发送成功",
  "msg_length": 12,
  "timestamp": "2024-01-01T12:00:00"
}
```

#### 2. 健康检查
- **URL**: `GET /health`
- **功能**: 检查服务状态
- **认证**: 不需要

#### 3. 状态查询
- **URL**: `GET /status`
- **功能**: 获取详细状态信息
- **认证**: 需要API密钥

### API密钥管理
使用Telegram命令 `/apikey` 可以快速更新API密钥：
- 自动生成安全的随机密钥
- 立即更新到配置文件
- 旧密钥立即失效
- 支持掩码显示保护安全

### 使用示例
```bash
# 使用Bearer Token认证发送消息
curl -X POST "http://botsite.thai2570.com:8080/sendMsg" \
     -H "Authorization: Bearer your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"msg": "Hello from API!"}'

# 使用X-API-Key认证
curl -X POST "http://botsite.thai2570.com:8080/sendMsg" \
     -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"msg": "Test message"}'

# 健康检查
curl "http://botsite.thai2570.com:8080/health"
```

## 📊 通知系统说明

### Smart模式（智能通知）- 推荐
- **只通知变化**：仅在有新错误或恢复时发送通知
- **简洁明了**：重点关注状态变化，减少信息噪音
- **适合场景**：长期稳定监控，关注问题变化

#### 示例通知
```
🔔 状态变化通知

🆕 新出现问题 (2个):
• example1.com - Cloudflare错误 (522连接超时)  
• example2.com - 网关错误 (502坏网关)

✅ 已恢复正常 (1个):
• example3.com

📊 当前总体:
• 监控总数: 68 • 在线正常: 66 • 异常域名: 2

⏰ 2024-01-01 12:00:00
```

### Full模式（完整通知）
- **每次都通知**：每次检查完成后都发送详细结果
- **完整信息**：显示所有错误的详细分类
- **适合场景**：调试阶段，需要详细了解每次检查结果

#### 示例通知
```
⚠️ 检查结果

📊 整体状态
🔍 检查域名: 68 个
✅ 正常在线: 65 个  
❌ 异常域名: 3 个

**⚠️ Cloudflare错误 (522连接超时) (1个):**
  • example1.com

**⚠️ Cloudflare错误 (526SSL证书无效) (1个):**
  • example2.com

**🚪 网关错误 (502坏网关) (1个):**
  • example3.com

⏰ 2024-01-01 12:00:00
```

## 🚀 性能优化建议

### 系统资源配置
- **小型部署** (<100域名): 1核1G内存，并发数10-20
- **中型部署** (100-500域名): 2核2G内存，并发数30-50  
- **大型部署** (>500域名): 4核4G内存，并发数50-100

### 优化特性
- **连接池复用** - 减少连接建立开销
- **HTTP/2支持** - 提升传输效率（安装h2包）
- **智能重试** - 仅重试可恢复的错误
- **批量处理** - 分批检查避免资源耗尽
- **自适应并发** - 根据CPU和内存动态调整

### 配置建议
```json
{
  "check": {
    "max_concurrent": 20,              // 根据服务器性能调整
    "auto_adjust_concurrent": true,    // 启用自适应
    "timeout_seconds": 15,             // 适中的超时时间
    "retry_count": 2,                  // 适度重试
    "batch_notify": false              // 减少通知频率
  },
  "notification": {
    "level": "smart",                  // 使用智能模式
    "failure_threshold": 2,            // 避免误报
    "cooldown_minutes": 60             // 合理冷却时间
  }
}
```

## 🔧 故障排查指南

### Telegram相关问题

**1. 消息发送失败**
- 检查Bot Token是否正确（从@BotFather获取）
- 确认Chat ID格式正确（群组ID为负数）
- 验证机器人已加入群组并具有发送权限

**2. 命令无响应**  
- 检查机器人是否在线
- 确认用户在admin_users列表中（如果设置了）
- 查看日志文件检查错误信息

**3. 停止命令后自动重启**
- 检查systemd服务配置中的Restart策略
- 确认deploy.sh使用正确的重启策略（on-failure而非always）
- 停止命令会设置正确的退出码避免自动重启

### 域名检查问题

**1. 检查超时频繁**
- 增加`timeout_seconds`配置（建议15-30秒）
- 减少`max_concurrent`并发数
- 检查网络连接稳定性
- 启用`auto_adjust_concurrent`自适应功能

**2. 内存占用过高**
- 启用`auto_adjust_concurrent`自适应并发
- 减少`max_concurrent`值
- 检查域名列表是否过大（建议<1000个）
- 定期清理日志文件

### Cloudflare集成问题

**1. Token验证失败**
- 检查Token是否正确复制（不含空格）
- 确认Token权限设置（Zone:Read, DNS:Read）
- 验证Token是否过期或被撤销

**2. 域名获取失败**
- 检查网络连接到Cloudflare API
- 确认Token有对应域名的访问权限
- 检查Cloudflare API服务状态

### 系统运行问题

**1. 服务启动失败**
- 检查Python版本（需要3.8+）
- 确认所有依赖已正确安装
- 检查配置文件格式（JSON语法）
- 查看详细错误日志

**2. 配置热重载失败**
- 检查配置文件JSON格式
- 确认文件权限可读写
- 重启服务以应用所有更改

**3. 命令重复执行问题**
- `/check` 命令具有重复执行保护机制
- 如需停止正在进行的检查，使用 `/stopcheck` 命令
- 查看执行状态可使用 `/status` 命令

## 📚 学习路径

### 新手入门
1. **环境准备** - 安装Python和依赖包
2. **基础配置** - 设置Telegram Bot和基本监控
3. **运行测试** - 添加少量域名进行测试
4. **熟悉命令** - 学习基本的Telegram命令操作

### 进阶使用  
1. **性能优化** - 调整并发数和超时配置
2. **通知优化** - 配置智能通知和冷却时间
3. **Cloudflare集成** - 连接CF账号批量管理域名
4. **生产部署** - 使用systemd或Docker部署

### 专家级配置
1. **大规模监控** - 优化大量域名的监控性能
2. **多账号管理** - 管理多个CF账号和Token
3. **自定义开发** - 基于API进行二次开发
4. **监控报警** - 集成其他监控系统

## 💡 最佳实践

### 监控配置
- 使用合理的检查间隔（推荐30分钟）
- 启用自适应并发控制
- 设置适当的失败阈值避免误报
- 使用智能通知模式减少噪音

### 安全建议
- 定期轮换Cloudflare API Token
- 限制Telegram管理员用户
- 使用最小权限原则配置Token
- 定期检查和清理不用的配置

### 运维建议  
- 定期检查日志文件大小
- 监控系统资源使用情况
- 备份重要配置文件
- 测试灾难恢复流程

## 📄 技术架构

### 核心模块
- **DomainMonitor** - 主程序协调器，管理整个监控流程
- **DomainChecker** - 异步域名检测引擎，负责并发检查
- **TelegramBot** - 机器人命令处理器，处理用户交互
- **TelegramNotifier** - 通知发送器，智能通知管理
- **ConfigManager** - 配置管理器，支持热重载功能
- **CloudflareManager** - CF API管理器，Token和域名管理
- **ErrorTracker** - 错误统计追踪器，分析失败模式

### 技术特点
- **异步架构** - 基于asyncio的高性能异步处理
- **连接池管理** - HTTP连接复用提升效率  
- **智能重试** - 区分错误类型进行有选择重试
- **自适应控制** - 根据系统负载动态调整并发
- **热配置更新** - 无需重启即可更新大部分配置
- **模块化设计** - 松耦合的模块化架构便于扩展

## 📝 更新日志

### v1.1.0 - Cloudflare集成版本
- ✅ 集成Cloudflare API功能
- ✅ 多用户Token管理系统
- ✅ 域名批量操作（获取/导出/同步）
- ✅ 外部域名文件支持
- ✅ 扩展Telegram命令集

### v1.0.0 - 基础监控版本
- ✅ 异步域名批量监控
- ✅ Telegram Bot控制
- ✅ 智能通知系统
- ✅ 配置热重载
- ✅ 生产部署支持

## 📄 许可证

MIT License - 详见 LICENSE 文件

## 🤝 贡献指南

欢迎贡献代码！提交PR前请确保：
- 代码符合项目风格
- 添加必要的测试
- 更新相关文档
- 通过所有检查

## 📧 支持与反馈

- **Issues**: 使用GitHub Issues报告问题
- **讨论**: GitHub Discussions进行技术讨论  
- **文档**: 查看本README获取详细信息

---

**快速开始**：复制`config_example.json`到`config.json`，填入Bot Token和Chat ID，运行`python src/main.py`开始使用！