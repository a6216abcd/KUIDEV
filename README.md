## 🌟 项目赞助商 (Sponsor)

<p align="center">
  <a href="https://derouter.ai?ref=0oZZ1HVc" target="_blank">
    <b>DeRouter</b> — 基于区块链的纯正透明大模型 API 网关
  </a>
</p>

**DeRouter** 通过区块链技术保证 Claude、GPT 官方 API 的**纯正与透明**，杜绝掺水降智问题。目前 Claude、GPT 在能力上仍领先国内大模型。

- 🔗 官网：https://derouter.ai?ref=0oZZ1HVc
- 🐦 Twitter：https://x.com/derouter_net
- 💰 **有多余的 Claude 账号**：可托管到平台赚取收益
- ⚡ **有 API 需求**：可使用其平台，价格为官方 API 的 **1-2 折**

<br>

<p align="center">
  <a href="https://bytevirt.com/aff.php?aff=209" target="_blank">
    <b>ByteVirt</b> — 始于方寸字节，成就无限云端
  </a>
</p>

**ByteVirt** 是一家专注于高性价比云服务器的 VPS 厂商，提供稳定可靠的虚拟化云端主机，适合部署 KUI 节点、探针 bash 及各类自建服务。

- 🔗 官网：https://bytevirt.com/aff.php?aff=209
- 🖥️ **多地域机房**：可按需选择节点位置，满足代理与监控部署需求
- ⚡ **稳定高速**：优质网络与虚拟化性能，保障服务长期在线

---

DEV 修复情况

- 2026/07/12：完成独立 Agent Token、统一 Agent/住宅代理组件热更新、住宅代理双隧道恢复及安装链路加固
- 2026/07/10：修复手机端网页显示异常
- 2026/07/09：修复 Clash 订阅和 SOCKS5 输入回退

# ⚡ KUI x Server Monitor Pro - 无服务器集群网关

![Vue 3](https://img.shields.io/badge/Frontend-Vue%203-4FC08D?logo=vuedotjs)
![Cloudflare Pages](https://img.shields.io/badge/Deploy-Cloudflare%20Pages-F38020?logo=cloudflare)
![Python Agent](https://img.shields.io/badge/Agent-Python%203-3776AB?logo=python)
![D1 Database](https://img.shields.io/badge/Database-Cloudflare%20D1-4285F4?logo=cloudflare)
![License](https://img.shields.io/badge/License-MIT-blue)

这是 **KUI 代理聚合面板**、**Server Monitor Pro 全景探针系统** 与**住宅 IP 双隧道代理**的一体化无服务器方案。

仅需一次 Cloudflare Pages 部署，即可获得一个高可用、零服务器成本的集群管理中心。您只需在 VPS 上执行**一条 Full Deploy Command**，即可同时完成 **8合1代理矩阵、深度系统探针、住宅 IP ACTIVE/STANDBY 双隧道**的安装与守护。

> 本项目基于 [CF-Server-Monitor-Pro](https://github.com/a63414262/CF-Server-Monitor-Pro) 及 [sing-box](https://github.com/SagerNet/sing-box) 加速实现，感谢开源社区的贡献。

---

## ✨ 核心特性

### 🚀 KUI 极速节点网关

- **一键 8合1 协议全家桶**：XTLS-Reality、Hysteria2、TUIC v5、Trojan、H2-Reality、gRPC-Reality、AnyTLS、Naive 防封锁协议极速下发
- **Argo 隧道守护**：当 IP 被封时，可启用 Cloudflared 守护进程，支持 VLESS-Argo 全自动穿透恢复
- **多用户体系**：完善的用户配额、到期时间管理，专属独立订阅链接，防泄漏重置机制
- **流量结算**：自动统计用户/节点流量，精确到字节，支持重置与图表回溯
- **第三方订阅**：支持导入外部订阅源，自动解析并混入本地节点池

### 📊 Server Monitor Pro 探针大盘

- **深度数据抓取**：实时 CPU、内存、磁盘、负载，精准统计出入网实时网速与月度总流量
- **国内四网延迟监控**：持续追踪服务器到 电信、联通、移动、字节跳动 的 24 小时 Ping 值趋势
- **6 大沉浸式主题**：默认白、暗黑极客、新粗野主义、毛玻璃、赛博朋克，以及**完全自定义模式**
- **地理拓扑**：自动识别机器归属地并在首页渲染高颜值全球 Leaflet 世界地图
- **多视图切换**：支持卡片视图、表格视图、地图视图三种展示模式

### 🌐 住宅 IP 代理控制器（双活引擎）

- **主备双活调度**：内置主备双路隧道（`tun_main` / `tun_backup`），通道故障软开关秒切
- **全量国家代码库**：预设 + 实时网络探测，提供最全面的目标锁定选择
- **鉴权代理提取**：管理员或对应 VPS Agent 可通过 `/api/proxy/proxies` 获取可用代理
- **安全热更新**：管理器与代理服务器每小时鉴权检查更新，验证 SHA256 和 Python 语法后原子替换

### 🛠 终极单轨架构

- **One Agent to Rule Them All**：彻底抛弃繁杂的 Bash 探针，由单一 Python 进程接管代理核心与系统监控，极大降低性能开销
- **无缝融合后台**：SPA (单页应用) 架构，登录后直接在同一个控制台管理节点和探针展示信息，零割裂感
- **TG 智能告警**：节点离线（超过2分钟）与恢复在线时，第一时间通过 Telegram 机器人推送告警

---

## 📸 界面预览

*(建议在此处添加您的真实截图)*

- **探针大盘展示** — 多视图卡片/表格/地图
- **单机 24H 趋势图** — CPU、内存、磁盘、网络、延迟
- **KUI 控制台与极速下发** — 8合1协议矩阵一键部署
- **住宅IP代理控制器** — 双活引擎调度界面

---

## 🚀 详细部署指南

本项目完全基于 Cloudflare Serverless 架构，您**不需要购买任何面板服务器**。

### 前置要求

- 一个 [GitHub](https://github.com) 账号
- 一个 [Cloudflare](https://dash.cloudflare.com) 账号（免费版即可）
- 一台或多台 VPS（Ubuntu 18-24 / Debian 10-13 / Alpine Linux）
- 住宅代理需要 VPS 支持 `/dev/net/tun`；若供外部设备连接，应在云防火墙和系统防火墙中仅对可信来源开放代理端口（默认 `7920/TCP`）

---

### 第一步：创建 Cloudflare D1 数据库

1. 登录 [Cloudflare 控制台](https://dash.cloudflare.com)，进入 **Workers & Pages** → **D1 SQL 数据库**
2. 点击 **Create database**，命名为 `kui-db`（或您喜欢的名字）
3. 创建完成后，记下数据库名称，后续部署时需要用到

> **注意**：您**不需要**手动建表！系统在首次访问时会自动完成 `servers`、`users`、`nodes`、`probe_servers` 等所有核心数据表的创建与迁移。

---

### 第二步：Fork 仓库到个人 GitHub

1. 打开本仓库页面
2. 点击右上角 **Fork** 将仓库复制到您的个人 GitHub 账号下
3. Fork 完成后，您将拥有一个完全相同的仓库副本

---

### 第三步：部署到 Cloudflare Pages

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)，进入 **Workers & Pages**
2. 点击 **Create application** → **Pages** → **Connect to Git**
3. 选择您刚刚 Fork 的仓库并授权
4. **构建设置**：
   - **Framework preset**：选择 `None`（无框架预设）
   - **Build command**：留空（`None`）
   - **Build output directory**：填写 `/`（根目录）
   - **Root directory**：保持默认 `/`
5. 生产分支选择本仓库当前使用的分支（例如 `dev`）；后续推送到该分支才会触发生产部署
6. 点击 **Save and Deploy**
7. 等待部署完成（通常 1-2 分钟），Cloudflare 会分配给您一个 `*.pages.dev` 域名

---

### 第四步：绑定 D1 数据库与环境变量

在 Pages 项目的 **Settings** → **Functions** → **D1 database bindings** 中：

1. **D1 数据库绑定**：
   - 变量名称：`DB`（**必须严格匹配**）
   - 选择您在第一步中创建的数据库（如 `kui-db`）
   - `ASSETS` 由 Cloudflare Pages 自动提供，用于鉴权安装器和 Agent 组件下载，不需要手工创建
   - 请按本文使用 **Cloudflare Pages** 部署；若改成普通 Worker 且没有 `ASSETS` 绑定，`/api/agent_update` 会返回 `503`

2. **环境变量**（Environment Variables）

#### 基础必填

| 变量名 | 说明 | 示例 | 必填 |
|---|---|---|---|
| `ADMIN_USERNAME` | KUI 后台管理员用户名 | `kui_admin` | ✅ |
| `ADMIN_PASSWORD` | KUI 后台管理员强密码 | 随机 24 位以上 | ✅ |
| `PROXY_USER` | Full Deploy 安装的住宅 SOCKS5 用户名 | `res_proxy` | ✅ |
| `PROXY_PASS` | 住宅 SOCKS5 强密码 | 随机 32 位以上 | ✅ |

虽然 Worker 代码对管理员账号保留了兼容默认值，但生产部署必须显式设置管理员账号和密码。`PROXY_USER`、`PROXY_PASS` 没有可用默认值；缺少任意一个时，住宅代理 API 返回 `503`，SOCKS5 监听器拒绝连接。

可以在本地生成随机密码：

```bash
openssl rand -base64 32
```

#### Telegram 与定时告警（可选）

| 变量名 | 说明 | 使用条件 |
|---|---|---|
| `TG_BOT_TOKEN` | Telegram Bot Token | 启用 Telegram 通知时配置 |
| `TG_CHAT_ID` | 接收告警的 Chat ID | 启用 Telegram 通知时配置 |
| `TG_WEBHOOK_SECRET` | Telegram Webhook 来源校验密钥 | 启用 Telegram 命令管理时必须配置 |
| `CRON_SECRET` | `/api/cron_check` 的 Bearer 密钥 | 使用外部 Cron 检查离线节点时配置 |

#### 迁移开关（可选）

| 变量名 | 说明 | 默认行为 |
|---|---|---|
| `LEGACY_AGENT_AUTH` | 设置为精确字符串 `false` 可关闭旧管理员哈希 Agent 兼容 | 临时兼容至 2026-08-01 UTC |

新部署无需设置此变量。历史 VPS 全部重新执行 Full Deploy Command 后，建议立即设置 `LEGACY_AGENT_AUTH=false` 并重新部署 Pages。

#### 住宅控制器无需配置

KUI 已内置基于 D1 的住宅代理控制器。Full Deploy Command 会自动使用当前 KUI 域名完成配置、控制和心跳上报。正常部署只需配置上面的四个基础变量，不要添加任何 `PROXY_CTRL_*` 变量。

代码中的 `PROXY_CTRL_*` 仅用于历史项目兼容和二次开发，不属于 KUI 标准部署流程。

#### 不是 Pages 环境变量的选项

以下变量只用于 VPS 进程的高级手工配置，不要填到 Cloudflare Pages 后期待自动下发：

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `PROXY_PORT` | `7920` | VPS 本地住宅代理监听端口 |
| `PROXY_MAX_CONNECTIONS` | `256` | 单台 VPS 最大并发代理连接数，最低为 16 |
| `PROXY_API_URL` | 当前 KUI 域名 | 统一 Agent 使用的住宅代理 API 根地址 |
| `C2_API_PREFIX` | `/api/proxy` | 住宅管理器控制器 API 前缀 |

> ⚠️ **安全提示**：不要使用 `admin/admin`、`proxy/888888` 等弱凭据。Deploy Command 包含服务器专属 Agent Token，只能在对应 VPS 的 root Shell 中执行，不要粘贴到公开 Issue、聊天群或命令日志。

> Cloudflare 的 **Production** 与 **Preview** 环境变量、D1 绑定相互独立。若生产分支为 `dev`，请确认该分支对应环境已经绑定 `DB` 并配置上述变量。修改变量后必须重新部署。

---

### 第五步：访问面板

1. 重新触发一次部署（在 Pages 项目页面点击 **Retry deployment**），确保环境变量和 D1 绑定生效
2. 访问您的 Pages 域名（如 `https://kui-monitor.pages.dev`）
3. 点击右上角 **👨‍💻 KUI 管理面板** 或 **系统准入** 登录后台
4. 使用您在第四步设置的账号密码登录

---

## 💻 一条命令接入完整 VPS

KUI、探针、sing-box 与住宅代理已经合并为一次部署流程，不需要再执行第二条住宅代理命令，也不需要配置额外的住宅控制器。

### 1. 在面板添加服务器

1. 登录后台，进入 **服务器与节点** 页面
2. 在 **接入机器** 表单中，填写：
   - **服务器别名**：如 `日本软银 01`
   - **公网 IP**：您的 VPS 公网 IP
   - **系统架构**：Debian/Ubuntu 选 `Linux`，Alpine 选 `Alpine`
3. 点击 **接入机器**

### 2. 获取部署指令

在刚刚添加的服务器卡片底部，系统会签发服务器专属 `agent_token` 并生成 **Deploy Command**。不要自行使用管理员密码或管理员密码哈希替代该 Token。

```bash
bash <(curl -fsSL --ipv4 -H 'Authorization: 服务器专属AgentToken' 'https://您的域名/api/agent_update?ip=您的VPS_IP&component=full-installer') \
  --api https://您的域名 \
  --ip 您的VPS_IP \
  --token 服务器专属AgentToken
```

### 3. 执行安装

使用 SSH 登录到您的 VPS，粘贴上述指令并回车：

```bash
# Ubuntu / Debian
bash <(curl -fsSL --ipv4 -H 'Authorization: 服务器专属AgentToken' 'https://您的域名/api/agent_update?ip=1.2.3.4&component=full-installer') \
  --api https://您的域名 \
  --ip 1.2.3.4 \
  --token 服务器专属AgentToken

# Alpine Linux
curl -fsSL --ipv4 -H 'Authorization: 服务器专属AgentToken' 'https://您的域名/api/agent_update?ip=1.2.3.4&component=full-installer' | sh -s -- \
  --api https://您的域名 \
  --ip 1.2.3.4 \
  --token 服务器专属AgentToken
```

安装脚本会自动完成以下操作：
- 清理历史残留进程
- 保留并使用系统现有软件源
- 安装底层网络依赖（Python3、curl、iptables 等）
- 部署 Sing-box 代理核心
- 初始化 KUI 工作目录
- 下载并启动全能 Python Agent
- 通过鉴权更新端点下载当前 Agent，并校验 SHA256 与 Python 语法
- 注册为系统守护进程（systemd / OpenRC）
- 鉴权下载住宅代理安装组件并校验 SHA256
- 安装 OpenVPN 与 TUN 依赖
- 部署 `proxy-lite`、`tun_main` 和 `tun_backup`
- 自动处理 sing-box 与住宅代理的端口接管

### 4. 验证接入

安装完成后约 10-30 秒，您的机器会自动出现在全景探针大盘中并开始上报数据。

> 2026-08-01 前请在每台历史 VPS 上重新执行面板当前生成的部署命令，以将旧的管理员哈希凭据迁移为服务器专属 Agent Token。完成全部迁移后可立即设置 `LEGACY_AGENT_AUTH=false`。

> 新版 Agent 每小时通过鉴权端点检查更新，校验 SHA256 和 Python 语法后原子替换并自动重载。历史 Agent 本身没有热更新能力，因此仍需执行一次新版部署命令完成初始化。

> Pages Functions 不直接运行 Cron Trigger。需要离线告警时，请让 Cloudflare Worker Cron、UptimeRobot 或其他定时服务每分钟 `POST https://您的域名/api/cron_check`，并携带请求头 `Authorization: Bearer <CRON_SECRET>`。

您可以直接在面板使用 **🚀 爆发下发** 功能，10 秒内部署 8 大节点阵列！

### 5. Agent 服务验证

```bash
# Debian / Ubuntu
systemctl is-active kui-agent sing-box proxy-lite
journalctl -u kui-agent -n 50 --no-pager
stat -c '%a %n' /opt/kui/config.json /etc/sing-box/config.json

# Alpine / OpenRC
rc-service kui-agent status
rc-service sing-box status
rc-service proxy-lite status
tail -n 50 /var/log/kui-agent.log
stat -c '%a %n' /opt/kui/config.json /etc/sing-box/config.json
```

安装后等待 30-90 秒再执行验证。预期结果：三个服务均正常运行，配置文件权限为 `600`，服务器心跳持续更新，住宅代理页面最终显示 `2 / 2`。

---

## 🌐 住宅 IP 双隧道代理

住宅代理服务 `proxy-lite` 已由 Full Deploy Command 自动安装。它复用同一台服务器的专属 Agent Token，不使用管理员登录凭据。

### 1. 配置 Pages 环境变量

至少配置：

```text
PROXY_USER=自定义用户名
PROXY_PASS=随机强密码
```

修改环境变量后重新部署 Pages，并确认后台 **住宅IP代理** 页面可以正常读取配置。

如果要从其他设备访问 SOCKS5，请仅向可信客户端 IP 放行 `7920/TCP`。不要将代理端口无来源限制地暴露到公网。

### 2. 一键部署

在后台 **服务器与节点** 页面选择 Debian/Ubuntu 或 Alpine，复制该服务器卡片中的 **Full Deploy Command** 并执行。命令会同时安装统一 Agent 与住宅双隧道。

### 3. 仅重装住宅代理（可选）

正常部署不需要执行以下命令。仅当统一 Agent 正常、但需要单独修复或重装住宅代理组件时使用。以下修复命令同样通过鉴权 API 获取当前安装器，不使用可能被 CDN 缓存的公开静态脚本：

```bash
# Debian / Ubuntu
bash <(curl -fsSL -H 'Authorization: 服务器专属AgentToken' 'https://您的域名/api/agent_update?ip=您的VPS_IP&component=proxy-installer') \
  --domain https://您的域名 \
  --controller https://您的域名 \
  --ip 您的VPS_IP \
  --token 服务器专属AgentToken

# Alpine（住宅代理脚本需要 Bash，不能用 sh 执行）
apk add --no-cache bash curl
curl -fsSL --ipv4 -H 'Authorization: 服务器专属AgentToken' 'https://您的域名/api/agent_update?ip=您的VPS_IP&component=proxy-installer' | bash -s -- \
  --domain https://您的域名 \
  --controller https://您的域名 \
  --ip 您的VPS_IP \
  --token 服务器专属AgentToken
```

独立住宅修复脚本会：

- 安装 OpenVPN、Python、iptables 和网络依赖
- 在替换文件前停止旧 `proxy-lite`，避免 systemd 重启风暴
- 通过 `/api/agent_update` 鉴权下载 `lite_manager.py` 和 `proxy_server.py`
- 校验响应 SHA256 和 Python 语法
- 将 Token 与本地凭据写入 `/etc/proxy-lite/env`，权限设为 `600`
- 创建 systemd/OpenRC 服务
- 建立 `tun_main`（ACTIVE）和 `tun_backup`（STANDBY）
- 此后每小时自动检查住宅代理组件更新

### 4. 验证双隧道

```bash
# Debian / Ubuntu
systemctl is-active proxy-lite
journalctl -u proxy-lite -n 100 --no-pager
ip -brief address show tun_main
ip -brief address show tun_backup
pgrep -a openvpn
stat -c '%a %n' /etc/proxy-lite/env

# Alpine / OpenRC
rc-service proxy-lite status
tail -n 100 /var/log/proxy-lite.log
ip -brief address show tun_main
ip -brief address show tun_backup
pgrep -a openvpn
stat -c '%a %n' /etc/proxy-lite/env
```

预期结果：

- `proxy-lite` 为 `active`
- `tun_main` 和 `tun_backup` 都有隧道地址
- 存在两个 OpenVPN 进程
- 后台 **活跃节点矩阵** 显示 `2 / 2`
- 一条隧道标记为 ACTIVE，另一条标记为 STANDBY
- `/etc/proxy-lite/env` 权限为 `600`

### 5. 验证 SOCKS5 出口

请使用 Pages 中配置的 `PROXY_USER/PROXY_PASS`：

```bash
curl -fsS --max-time 30 \
  --proxy socks5h://127.0.0.1:7920 \
  --proxy-user 'PROXY_USER:PROXY_PASS' \
  https://api.ipify.org
```

返回值应是当前 ACTIVE 住宅出口 IP，而不是 VPS 本机公网 IP。

---

## 🔄 历史 VPS 迁移与热更新

### 从旧管理员哈希 Token 迁移

旧版部署曾将管理员密码哈希写入 `/opt/kui/config.json`。新版会在兼容窗口内恢复上报，并在成功拉取配置后自动将服务器专属 Token 原子写回本地。

仍建议在 **2026-08-01 前**逐台重新执行面板当前生成的 Full Deploy Command。它会同时迁移统一 Agent 和住宅代理。全部迁移后设置：

```text
LEGACY_AGENT_AUTH=false
```

### 热更新范围

以下组件每小时通过鉴权端点检查更新：

- `/opt/kui/agent.py`
- `/opt/proxy_lite/lite_manager.py`
- `/opt/proxy_lite/proxy_server.py`

更新流程为：下载到临时文件 → 限制体积 → 校验 SHA256 → `py_compile` → 原子替换 → 进程自重载。Full Deploy Command、安装器和热更新均通过鉴权 `/api/agent_update` 获取当前部署资产，不依赖可能被 CDN 缓存的公开 `/vps/*` 路径。

---

## 🎨 主题与高级自定义

在后台的 **⚙️ 系统设置** 中，您可以自由调整大盘外观：

- **切换主题**：默认白、暗黑极客、新粗野主义、毛玻璃、赛博朋克、完全自定义
- **启用二次元/自定义壁纸**：在"自定义背景图片 URL"中填入图片直链，面板自动切换为毛玻璃半透明卡片风格
- **引入自定义脚本**：在"自定义底部 Script 注入"中填入樱花飘落、鼠标拖尾等 JS 源码（需带 `<script>` 标签），系统会通过虚拟 DOM 安全注入并立即生效
- **站点标题**：自定义面板左上角标题
- **弹窗公告**：配置首次访问弹窗内容
- **自动重置流量**：开启后每月自动清零流量统计

---

## 🏗 项目结构

```
K-UI-main/
├── index.html                    # SPA 单页应用（Vue 3 + Tailwind CSS）
├── functions/
│   └── api/
│       └── [[path]].js           # Cloudflare Pages Functions 后端
│                                   # 包含：API路由、协议生成、订阅解析、D1操作
└── vps/
    ├── agent.py                  # 全能 Python Agent（监控 + 代理管理 + 心跳上报）
    ├── kui.sh                    # VPS 智能跨系统安装脚本
    ├── lite_manager.py           # 住宅 IP 代理双活调度引擎
    ├── proxy_server.py           # SOCKS5 代理服务器核心
    └── residential-proxy.sh      # 住宅代理一键安装脚本
```

---

## 🔧 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 前端 | Vue 3 + Tailwind CSS | 响应式 SPA，6 大主题支持 |
| 后端 | Cloudflare Pages Functions | 无服务器计算，自动扩缩容 |
| 数据库 | Cloudflare D1 | 全球边缘 SQL 数据库 |
| 探针 | ECharts + Chart.js + Leaflet | 图表可视化 + 地理地图 |
| 代理核心 | Sing-box | 现代化代理核心 |
| Agent | Python 3 | 系统监控 + 代理管理 |

---

## 🔑 核心功能说明

### 代理协议支持

| 协议 | 说明 | 适用场景 |
|---|---|---|
| XTLS-Reality | 基于 VLESS + Reality，最高抗封锁 | 生产环境首选 |
| Hysteria2 | 基于 QUIC，极速低延迟 | 需要高速度 |
| TUIC v5 | 基于 QUIC，高并发 | 多用户高并发 |
| Trojan | 经典 Trojan 协议 | 兼容性好 |
| H2-Reality | HTTP/2 + Reality | 伪装正常网站流量 |
| gRPC-Reality | gRPC + Reality | 高隐蔽性 |
| AnyTLS | 新一代抗封锁协议 | 最新抗封锁 |
| Naive | 基于 HTTP/2 | 轻量简洁 |
| VLESS-Argo | VLESS + Cloudflare Argo | IP 被封时隧道穿透 |

### 探针监控指标

- CPU 使用率 + CPU 信息
- 内存使用率 + Swap 使用量
- 磁盘使用率 + 已用/总量
- 系统负载（Load Average）
- 实时网速（入/出）+ 月度总流量
- 进程数
- TCP/UDP 连接数
- 国内四网延迟（电信/联通/移动/字节跳动）24小时趋势

---

## ❓ 常见问题

**Q: 部署后提示 "DB binding not found"？**

A: 请检查 Pages 项目的 **Settings → Functions → D1 database bindings** 中变量名是否为 `DB`，且绑定了正确的数据库。

**Q: Agent 安装失败或下载超时？**

A: 新安装器从 Pages 的鉴权更新端点下载，不再依赖 GitHub Raw 或公开静态 Python 缓存。请检查服务器 IP 是否已在面板登记、`--token` 是否为该服务器专属 Token，以及 VPS 能否出站访问 Pages 域名。

**Q: 探针数据不上报？**

A: 请检查：
1. VPS 上 `kui-agent` 服务是否正常运行：`systemctl status kui-agent`
2. 防火墙是否放行出站 HTTPS（443 端口）
3. `/opt/kui/config.json` 中的 `api_url` 和 `token` 是否正确

**Q: 住宅代理后台显示 `0 / 2`？**

A: 依次检查：

1. `systemctl status proxy-lite`
2. `journalctl -u proxy-lite -n 150 --no-pager`
3. 是否出现 `/api/proxy/config` 的 `401/403`；出现时请重新执行服务器专属住宅代理安装命令
4. `ip -brief address show tun_main` 和 `tun_backup`
5. `/dev/net/tun` 是否存在
6. Pages 是否配置 `PROXY_USER`、`PROXY_PASS`

**Q: 推送 GitHub 后 VPS 为什么没有更新？**

A: 旧 Agent 没有热更新能力，必须执行一次新版部署命令完成引导。新版统一 Agent和住宅代理组件每小时自动更新。GitHub 推送还必须触发 Pages 生产分支部署；仅推送到未绑定的分支不会更新生产环境。

**Q: 现在还需要单独运行住宅代理安装命令吗？**

A: 不需要。服务器卡片的 Full Deploy Command 已自动执行住宅代理安装。独立 `residential-proxy.sh` 仅保留用于单独修复或重装住宅组件。

**Q: Pages 已更新，但 `/vps/*.py` 看起来还是旧内容？**

A: 公开静态 Python 路径可能存在 CDN 缓存。新版安装器与热更新使用带专属 Token 的 `/api/agent_update`，响应为 `no-store` 并带 `X-Agent-SHA256`，不依赖公开静态路径。

**Q: 支持哪些系统？**

A: 官方支持 Ubuntu 18-24、Debian 10-13、Alpine Linux。其他 systemd 发行版理论上也可运行，但未经过测试。

**Q: 是否需要公网域名？**

A: 部署 Cloudflare Pages 时需要。但 VPS Agent 通信仅需出站 HTTPS，不需要任何端口开放或域名解析。

---

## 📝 贡献与支持

如果您有任何想法或发现了 Bug，欢迎提交 [Pull Request](https://github.com/您的用户名/K-UI/compare) 或 [Issue](https://github.com/您的用户名/K-UI/issues)。

### 特别感谢

- [CF-Server-Monitor-Pro](https://github.com/a63414262/CF-Server-Monitor-Pro) — 探针系统基础
- [sing-box](https://github.com/SagerNet/sing-box) — 现代化代理核心
- [Cloudflare Pages](https://pages.cloudflare.com) — 无服务器托管平台
- 所有为本项目贡献代码、反馈问题的社区成员

### 免责声明

本项目整合了众多优秀的开源协议引擎（如 Sing-box、Xray 等）。请在遵循相关国家法律法规的前提下使用本项目，仅供学习、网络环境测试及探针监控交流使用。

---

## 📄 开源协议

[MIT License](LICENSE) © 2024+ KUI Cluster Gateway Team

---

**⭐ 如果这个项目对您有帮助，请给我们一个 Star！**
