# KUI x Server Monitor Pro

KUI 是一个部署在 **Cloudflare Workers** 的代理节点管理与服务器探针面板。Worker Assets 托管前端和 VPS 安装组件，D1 保存配置、用户、流量和探针数据；无需部署传统面板服务器。

[![Deploy to Cloudflare Workers](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/a6216abcd/KUIDEV)

## 一键部署

1. 点击上方 **Deploy to Cloudflare Workers**。
2. 登录 Cloudflare，选择账户并确认 Worker 名称。
3. Cloudflare 会自动创建并绑定 D1 数据库到 `DB`。不要删除这个 binding。
4. 部署成功后，在 Worker 的 **Settings → Variables and Secrets** 添加：

| 名称 | 类型 | 是否必填 | 说明 |
|---|---|---:|---|
| `ADMIN_PASSWORD` | Secret | 是 | 管理员密码，建议至少 16 位 |
| `ADMIN_USERNAME` | Variable | 否 | 管理员名称，默认 `admin` |
| `REALTIME_URL` | Variable | 否 | Realtime Worker 地址，启用实时推送时填写 |
| `CRON_SECRET` | Secret | 否 | 保护 `/api/cron_check` 接口 |
| `PROXY_USER` | Secret | 否 | 启用内置住宅代理时填写 |
| `PROXY_PASS` | Secret | 否 | 启用内置住宅代理时填写 |
| `PROXY_CTRL_URL` | Variable | 否 | 外部住宅代理控制器 HTTPS 地址 |

5. 保存变量后点击 **Deploy**，打开 Worker 地址即可登录。首次访问会自动初始化所有 D1 数据表。

默认登录名是 `admin`，密码为你设置的 `ADMIN_PASSWORD`。

## 自定义域名

在 Worker 的 **Settings → Domains & Routes → Add** 中绑定域名或子域名。绑定后直接使用该域名访问面板。

## 本地部署

适用于需要使用已有 D1、固定 Worker 名称或自行维护发布流程的场景。

```bash
git clone https://github.com/a6216abcd/KUIDEV.git
cd KUIDEV
npm install
npx wrangler login
npx wrangler secret put ADMIN_PASSWORD
npx wrangler deploy
```

当前 `wrangler.jsonc` 未指定 D1 ID，首次部署会自动创建数据库。若需要使用已有 D1，在 Cloudflare Dashboard 的 Worker **Settings → Bindings** 中将 `DB` 重绑到目标数据库后重新部署。

本地预览：

```bash
npm run dev
```

## Realtime Worker（可选）

KUI 主面板不依赖 Realtime Worker 也可正常运行。若需要 Dashboard WebSocket 实时状态、在线观众自适应上报频率和配置即时下发，则额外部署 `realtime/`：

```bash
cd realtime
npm install
# 修改 wrangler.jsonc：将 database_id 改为主 Worker 的 DB 对应 D1 ID
npx wrangler deploy
```

将部署完成后的 Realtime Worker URL 填入主 Worker 的 `REALTIME_URL` 变量。两者必须绑定同一个 D1。

## VPS 接入

1. 登录 KUI，进入 **服务器与节点**。
2. 添加 VPS 名称和公网 IP。
3. 复制页面生成的 Full Deploy Command，以 `root` 在 VPS 执行。
4. 等待 Agent 回连后创建节点或使用“8 合 1”批量部署。

支持 XTLS-Reality、Hysteria2、TUIC、Trojan、H2/gRPC-Reality、AnyTLS、Naive、VLESS-Argo、Socks5 与 Dokodemo-door。

## 主要能力

- 多用户、订阅令牌、流量配额和到期管理。
- Mihomo/Clash 订阅导出，包括 AnyTLS。
- CPU、内存、磁盘、网络、TCP/UDP 与线路延迟探针。
- 多种预设探针主题、自定义 CSS 和背景。
- 原生、WARP、住宅代理和手动 SOCKS5 节点出口。
- 可选 Telegram 告警与订阅保护。
- Worker Cron 每 5 分钟检查离线节点。

## 架构

```text
浏览器 / VPS Agent
        |
Cloudflare Worker
  |- Worker Assets: 前端与 VPS 安装文件
  |- /api/*: KUI 后端接口
  |- Cron: 离线检查
  `- D1 (DB): 配置、用户、节点、流量、探针数据

可选：Realtime Worker + Durable Objects
```

## 注意事项

- 不要提交 `ADMIN_PASSWORD`、D1 ID、Telegram Token 或代理凭据。
- `DB` 是固定 binding 名称，修改会导致后端无法访问数据库。
- 修改 Worker Variables 或 Bindings 后需要重新部署。
- 使用已有 D1 时，确认主 Worker 与可选 Realtime Worker 的 `DB` 指向同一个数据库。
- `workspace-preview.html` 仅用于本地预览，不参与 Worker 静态资源发布。

## 开源协议

MIT
