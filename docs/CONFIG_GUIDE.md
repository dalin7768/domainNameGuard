# 配置指南

## 快速配置

1. 复制示例配置：
```bash
cp config_example.json config.json
```

2. 编辑配置文件：
```bash
nano config.json
```

## 必要配置项

### Telegram配置
```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",  // 必填：Bot Token
    "chat_id": "-1234567890",       // 必填：群组ID（负数）
    "admin_users": ["@username"]    // 可选：管理员用户名
  }
}
```

**获取Bot Token：**
1. Telegram搜索 @BotFather
2. 发送 `/newbot` 创建机器人
3. 获得Token

**获取Chat ID：**
1. 把机器人加入群组
2. 在群组发送消息
3. 访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. 找到chat id（负数）

### 域名列表
```json
{
  "domains": [
    "example.com",
    "test.com"
  ]
}
```
- 不需要加 http:// 或 https://
- 程序会自动使用HTTPS

### 检查配置（可选）
```json
{
  "check": {
    "interval_minutes": 30,    // 检查间隔（分钟）
    "max_concurrent": 10,       // 最大并发数
    "timeout_seconds": 10,      // 超时时间（秒）
    "retry_count": 2           // 重试次数
  }
}
```

### 通知配置（可选）
```json
{
  "notification": {
    "notify_on_recovery": true,  // 恢复时通知
    "failure_threshold": 1,      // 失败几次才告警
    "cooldown_minutes": 20       // 告警冷却时间
  }
}
```

## 完整示例

```json
{
  "telegram": {
    "bot_token": "1234567890:ABCdefGHI...",
    "chat_id": "-1001234567890",
    "admin_users": ["@admin"]
  },
  "check": {
    "interval_minutes": 30,
    "max_concurrent": 10,
    "timeout_seconds": 10,
    "retry_count": 2
  },
  "domains": [
    "example.com",
    "api.example.com",
    "test.com"
  ],
  "notification": {
    "notify_on_recovery": true,
    "failure_threshold": 1,
    "cooldown_minutes": 20
  },
  "logging": {
    "level": "INFO"
  }
}
```

## 通过Telegram修改配置

大部分配置可通过命令实时修改：

- `/interval 10` - 设置检查间隔
- `/timeout 15` - 设置超时时间
- `/retry 3` - 设置重试次数
- `/add example.com` - 添加域名
- `/remove example.com` - 删除域名
- `/reload` - 重新加载配置