# QQ账号离线通知

![:name](https://count.getloli.com/@astrbot_plugin_offline_notice?name=astrbot_plugin_offline_notice&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

一个专门为 QQ 个人号平台打造的掉线检测插件，定时检测 QQ 账号的在线状态，离线时第一时间通过邮件通知用户，并且支持SnowLuma Webhook 通知。仅支持 aiocqhttp（OneBot v11）。


<p align="center">
  <img src="https://img.dkdun.cn/v1/2026/17/08f0226a817892df.png" alt="圣娅怪叫.png（太臭了哼哼啊啊啊啊啊啊啊啊啊啊啊！）">
</p>

<div align="center">

  [![GitHub license](https://img.shields.io/github/license/VanillaNahida/astrbot_plugin_offline_notice?style=flat-square)](https://github.com/VanillaNahida/astrbot_plugin_offline_notice/blob/main/LICENSE)
  [![GitHub stars](https://img.shields.io/github/stars/VanillaNahida/astrbot_plugin_offline_notice?style=flat-square)](https://github.com/VanillaNahida/astrbot_plugin_offline_notice/stargazers)
  [![GitHub forks](https://img.shields.io/github/forks/VanillaNahida/astrbot_plugin_offline_notice?style=flat-square)](https://github.com/VanillaNahida/astrbot_plugin_offline_notice/network)
  [![GitHub issues](https://img.shields.io/github/issues/VanillaNahida/astrbot_plugin_offline_notice?style=flat-square)](https://github.com/VanillaNahida/astrbot_plugin_offline_notice/issues)
  [![python3](https://img.shields.io/badge/Python-3.10+-blue.svg?style=flat-square)](https://www.python.org/)
  [![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-brightgreen.svg?style=flat-square)]()
  [![Author](https://img.shields.io/badge/%E4%BD%9C%E8%80%85-VanillaNahida-green)](https://github.com/VanillaNahida )



</div>

# 功能特性

- **定时心跳检测**：通过 OneBot v11 的 `get_status` API 定时检测账号在线状态
- **邮件离线通知**：账号离线时自动发送 HTML 富文本邮件到指定邮箱
- **离线原因追踪**：自动捕获 OneBot v11 下发的 `bot_offline` 通知事件，汇总下线原因并包含在邮件中
- **SnowLuma Webhook 通知**：接收 SnowLuma 推送的账号上下线状态通知，自动转为邮件发送
- **自定义邮件模板**：支持魔法变量，可自定义邮件主题和正文（HTML 格式），心跳检测和 SnowLuma 各有独立模板
- **多种加密方式**：SMTP 发送支持 SSL / TLS / 不加密
- **测试邮件命令**：配置完成后可通过管理员命令发送测试邮件验证配置
- **QQ 号主动提醒**：掉线时可由「另一个机器人实例」向指定 QQ 号私聊推送提醒，接收人 QQ、提醒内容均可自定义

# 原理

本插件通过 OneBot v11 API 定时调用 `get_status` 接口，检查返回数据中的 `online` 字段。当 `online` 为 `false` 时，判定账号已离线，随即调用 `get_login_info` 获取账号信息，连同捕获到的 `bot_offline` 下线原因一并发送邮件通知。

同时插件会启动一个 HTTP Webhook 服务器，接收 SnowLuma 推送的账号上下线状态通知，解析后通过独立模板发送邮件通知。

```
心跳检测流程:
get_status → online: false
    ↓
get_login_info → {user_id, nickname}
    ↓
bot_offline 通知缓存 → {时间, 类型, 详情}
    ↓
渲染邮件模板 → SMTP 发送

SnowLuma Webhook 流程:
SnowLuma POST /notice/send?token=xxx
    ↓
解析 JSON → {title, desp}
    ↓
提取 event, uin, nickname, time 并格式化为 GMT+8
    ↓
QQ号-昵称缓存匹配 / 更新
    ↓
渲染 SnowLuma 邮件模板 → SMTP 发送
```

# 使用方法

> [!TIP]
>
> 支持 SnowLuma Webhook 通知。配置插件后，Webhook URL 和 Body 模板会自动生成在配置页面中，将其填入 SnowLuma 的 WebUI 即可接收账号状态变更通知。

## 安装

1. 在 AstrBot WebUI 插件市场搜索 `astrbot_plugin_offline_notice` 或 `QQ账号离线通知`
2. 点击安装插件
3. 或者通过仓库地址安装：复制 `https://github.com/VanillaNahida/astrbot_plugin_offline_notice` 粘贴到 WebUI 安装

## 配置

### 基础配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `heartbeat_interval` | int | 180 | 心跳检测间隔（秒） |

### 邮件发送配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `username` | string | SMTP 登录用户名，通常与发信地址相同 |
| `sender` | string | 邮件显示的发件人地址 |
| `password` | string | SMTP 登录密码或授权码（QQ 邮箱需使用授权码） |
| `display_name` | string | 收件人看到的发件人名称 |
| `smtp_server` | string | SMTP 服务器地址，例如 `smtp.qq.com` |
| `smtp_port` | int | SMTP 端口，SSL 通常为 465，TLS 通常为 587 |
| `encryption` | string | 加密类型，可选 `SSL` / `TLS` / `不启用` |
| `recipients` | list | 通知收件人邮箱列表 |

### 邮件模板

支持以下魔法变量，可在主题和正文中使用：

| 变量 | 说明 |
|------|------|
| `{{user_id}}` | QQ 账号 ID |
| `{{nickname}}` | QQ 昵称 |
| `{{timestamp}}` | 检测时间 |
| `{{platform}}` | 平台名称 |
| `{{offline_reason}}` | 离线原因详情（bot_offline 通知汇总） |

正文支持 HTML 格式，默认提供一套美观的富文本邮件模板。

### SnowLuma Webhook 配置

插件启动后会在配置中自动生成 Webhook 地址和 Body 模板，无需手动填写。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `host` | string | 127.0.0.1 | Webhook 服务器监听地址 |
| `port` | int | 3051 | Webhook 服务器监听端口 |
| `access_token` | string | （空） | 访问令牌，用于验证请求（可留空） |
| `webhook_url` | string | 自动生成 | 完整的 Webhook 地址，填入 SnowLuma |
| `webhook_body_template` | json | 自动生成 | Body JSON 模板，填入 SnowLuma （这里使用的是SnowLuma的默认值）|

Webhook 地址格式：`http://{host}:{port}/notice/send?token={access_token}`

### SnowLuma 通知邮件模板

独立于心跳检测的邮件模板，支持以下模板变量：

| 变量 | 说明 |
|------|------|
| `{{title}}` | SnowLuma 推送的完整标题 |
| `{{uin}}` | QQ 号 |
| `{{nickname}}` | QQ 昵称 |
| `{{event}}` | 事件类型（上线/离线） |
| `{{time}}` | 时间（格式：YYYY-MM-DD HH:MM:SS） |
| `{{desp}}` | 原始描述文本 |
| `{{desp_html}}` | 自动转换为 HTML 后的描述 |

QQ号-昵称映射会存储在插件数据目录的 `uin_nickname.json` 中，上限 10 条，超过时自动移除最久未访的记录。

### QQ 号主动提醒配置

除邮件外，插件还可以通过**另一个在线的机器人**，向指定 QQ 号私聊推送掉线提醒。适合不方便收邮件、只想在 QQ 里第一时间知道的场景。

| 配置项 | 说明 |
|------|------|
| 启用 QQ 号提醒 | 勾选后开启本功能，默认关闭 |
| 提醒接收人 QQ 号 | 要接收提醒的 QQ 号，支持多个。可直接填写，也可点击选择器从聊天中挑选 |
| 发送提醒的机器人实例 ID | OneBot v11 直发时使用。留空则自动选择第一个可用的 OneBot v11 实例。使用 QQ 官方机器人提醒时无需填写 |
| 提醒内容模板 | 自定义提醒正文，支持变量 |
| 消息前缀 | 可选，在正文前加一句前缀 |
| 自动记录会话 UMO | 默认开启。机器人收到私聊消息时自动保存会话 UMO，供主动推送复用（QQ 官方机器人必需） |
| 会话 UMO | 一般无需填写，自动记录失败时可手动填入，多个用逗号分隔 |

提醒内容模板支持以下变量：

| 变量 | 说明 |
|------|------|
| `{nickname}` | 掉线账号的昵称 |
| `{uin}` | 掉线账号的 QQ 号 |
| `{platform}` | 平台实例名称 |
| `{time}` | 触发时间（YYYY-MM-DD HH:MM:SS） |
| `{event}` | 事件状态，如「🔴 已离线」 |
| `{extra}` | 离线原因详情（纯文本） |

默认模板：

```
🔔 账号掉线提醒
账号：{nickname}（{uin}）
平台：{platform}
时间：{time}
状态：{event}
{extra}
```

> ⚠️ **重要**：「发送提醒的机器人实例 ID」请填写**另一个**在线机器人的实例，不要填被监控的那个账号。被监控账号掉线后自身已离线，无法发出消息。

配置完成后可用管理员命令验证：

```
/发送测试提醒
```

### 使用 QQ 官方机器人（qq_official）提醒

如果你的提醒机器人是 **QQ 官方机器人**（WebUI 平台列表中适配器为 `qq_official`），按下面步骤操作：

**1. 私聊机器人建立会话**  
QQ 官方机器人的主动消息要求用户先有会话窗口。用你的 QQ 主动私聊该官方机器人**任意一句话**，插件会自动捕获并保存该会话 UMO 到数据目录的 `qq_notifier_umo.json`。

**2. 打开配置**  
在插件配置里勾选「启用 QQ 号提醒」，填写「提醒接收人 QQ 号」。「发送提醒的机器人实例 ID」留空即可（官方机器人不走 OneBot 直发）。确认「自动记录会话 UMO」为开启状态。

**3. 发送测试**  
在任意会话中执行 `/发送测试提醒`，若收到消息即配置成功。

**4. 排查问题**  
执行 `/提醒通道` 可查看当前识别到的平台实例类型和已记录的会话 UMO 列表。

> ⚠️ 注意：被监控的账号如果是 `napcat` 本身，掉线后它自己无法发消息，必须由另一个机器人（如 QQ 官方机器人）来提醒——这正是本功能的用途。

## 验证配置

配置完成后，在 AstrBot 中使用管理员命令发送测试邮件：

```
/发送测试邮件 test@example.com
```

收到测试邮件即代表一切配置正确。

# 命令总览

| 命令 | 示例用法 | 权限要求 | 说明 |
|------|------|----------|------|
| `/发送测试邮件` | `/发送测试邮件 test@example.com` | Bot 管理员 | 发送测试邮件到指定地址，验证邮件配置是否正确 |

# 常见邮箱 SMTP 配置

| 邮箱 | SMTP 服务器 | 端口 | 加密 |
|------|------------|------|------|
| QQ 邮箱 | `smtp.qq.com` | 465 | SSL |
| 163 邮箱 | `smtp.163.com` | 465 | SSL |
| Gmail | `smtp.gmail.com` | 587 | TLS |
| Outlook | `smtp-mail.outlook.com` | 587 | TLS |

# Bug 反馈

如果在使用过程中遇到任何问题，请通过以下方式反馈：

- [GitHub Issues](https://github.com/VanillaNahida/astrbot_plugin_offline_notice/issues)
- QQ群：
  - 三群：195260107（推荐）
  - 四群：1074471035（闲聊群）

# QQ 群

- 一群：621457510
- 二群：1031065631
- 三群：195260107（推荐）
- 四群：1074471035

# Star History

[![Star History Chart](https://api.star-history.com/svg?repos=VanillaNahida/astrbot_plugin_offline_notice&type=Date)](https://star-history.com/#VanillaNahida/astrbot_plugin_offline_notice&Date)
