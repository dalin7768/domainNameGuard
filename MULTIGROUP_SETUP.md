# 多群组域名监控设置指南

## 🎯 功能说明

支持一个Telegram机器人同时在多个群组工作，每个群组独立管理自己的域名列表和管理员权限，彻底解决Bot轮询冲突问题。

## 🚀 核心优势

- ✅ **解决轮询冲突**：一个Bot实例管理所有群组，避免多实例争抢
- 🏠 **群组隔离**：每个群组独立管理域名，互不影响
- 👥 **权限分离**：每个群组可设置独立的管理员
- 📊 **智能通知**：检查结果按群组分别发送，只通知相关域名

## 📋 配置步骤

### 1. 创建多群组配置文件

复制并修改 `config-multigroup-example.json`：

```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "groups": {
      "-1001234567890": {
        "name": "项目A监控群",
        "domains": [
          "projecta-site1.com",
          "projecta-site2.com",
          "projecta-api.com"
        ],
        "admins": ["admin_userA", "manager_user1"]
      },
      "-1001234567891": {
        "name": "项目B监控群",
        "domains": [
          "projectb-main.com",
          "projectb-api.com"
        ],
        "admins": ["admin_userB", "manager_user2"]
      }
    }
  }
}
```

### 2. 获取群组ID

在需要监控的Telegram群组中发送以下命令：

```bash
# 方法1：使用@userinfobot
# 将bot添加到群组，然后发送任意消息，bot会返回群组信息

# 方法2：查看日志
# 启动程序后，在群组中发送任意消息，日志中会显示chat_id
```

### 3. 设置管理员权限

在配置文件中为每个群组设置管理员：

```json
"admins": ["username1", "username2"]  // 不带@符号的用户名
```

### 4. 启动服务

```bash
# 使用多群组配置启动
python src/main.py --config config-multigroup.json

# 或使用部署脚本
./deploy.sh deploy multigroup
```

## 🎮 使用方法

### 群组独立操作

每个群组中的命令只影响当前群组：

```bash
# 在群组A中
/add projecta-new.com     # 只添加到群组A
/list                     # 只显示群组A的域名
/check                    # 检查所有群组域名，但结果只发到相关群组

# 在群组B中
/add projectb-new.com     # 只添加到群组B
/list                     # 只显示群组B的域名
```

### 权限管理

```bash
# 群组管理员命令（需要在对应群组执行）
/admin add @newuser       # 添加群组管理员
/admin remove @olduser    # 移除群组管理员
/admin list               # 查看当前群组管理员
```

## 🔄 从单群组迁移

### 方法1：自动转换

如果现有配置只有单个 `chat_id`，程序会自动转换：

```json
// 旧配置
{
  "telegram": {
    "chat_id": "-1001234567890"
  },
  "domains": ["site1.com", "site2.com"]
}

// 自动转换为
{
  "telegram": {
    "groups": {
      "-1001234567890": {
        "domains": ["site1.com", "site2.com"],
        "admins": []
      }
    }
  }
}
```

### 方法2：手动配置

1. 备份现有配置
2. 按新格式重新配置
3. 将域名分配到对应群组

## 🛠️ 部署脚本适配

修改 `deploy.sh` 支持多群组：

```bash
# 创建多群组实例
./deploy.sh deploy multigroup

# 配置文件将使用 config-multigroup.json
```

## 🧪 测试验证

### 1. 基本功能测试

```bash
# 在群组A中
/help                     # 应显示群组A的配置信息
/add test-a.com          # 添加测试域名
/list                     # 确认只显示群组A的域名

# 在群组B中
/help                     # 应显示群组B的配置信息
/add test-b.com          # 添加测试域名
/list                     # 确认只显示群组B的域名
```

### 2. 权限测试

```bash
# 用非管理员账户在群组中
/add test.com            # 应提示无权限

# 用管理员账户
/add test.com            # 应成功添加
```

### 3. 通知测试

```bash
# 手动检查
/check                   # 所有群组域名都会检查，但结果分别发送到对应群组
```

## 🚨 常见问题

### Q: 群组ID如何获取？
A: 使用 @userinfobot 或查看程序日志中的 chat_id

### Q: 可以跨群组管理域名吗？
A: 不可以，每个群组只能管理自己的域名，这是设计目标

### Q: 全局管理员是什么？
A: 在旧版 `telegram.admin_users` 中配置的管理员，在所有群组都有权限

### Q: 如何添加新群组？
A: 在配置文件的 `groups` 中添加新的群组配置，然后重启服务

## 📊 监控效果

- **合并检查**：所有群组域名在一次检查中完成，提高效率
- **分组通知**：每个群组只接收自己域名的监控结果
- **独立管理**：群组间域名和权限完全隔离
- **统一日志**：所有操作记录在同一日志文件中

## 🔧 故障排除

### 日志检查

```bash
# 查看多群组相关日志
grep -E "(群组|group|chat_id)" /var/log/domain-monitor-*.log

# 查看权限相关日志
grep -E "(权限|authorized|admin)" /var/log/domain-monitor-*.log
```

### 配置验证

```bash
# 检查配置文件格式
python -m json.tool config-multigroup.json

# 启动时查看群组加载信息
tail -f /var/log/domain-monitor-*.log | grep -E "(群组|group)"
```

这样设置后，你就可以用一个机器人在多个群组中独立管理不同项目的域名监控了！