# KUI x Server Monitor Pro

## 项目赞助商

<p align="center">
  <a href="https://derouter.ai?ref=0oZZ1HVc" target="_blank">
    <strong>DeRouter</strong> - 基于区块链的透明大模型 API 网关
  </a>
</p>

DeRouter 提供 Claude、GPT 等模型 API 服务，支持透明可验证的模型调用。

- 官网：https://derouter.ai?ref=0oZZ1HVc
- X：https://x.com/derouter_net
- 有 API 需求或 Claude 账号托管需求可访问其官网了解详情。

<p align="center">
  <a href="https://bytevirt.com/aff.php?aff=209" target="_blank">
    <strong>ByteVirt</strong> - 高性价比云服务器与 VPS 服务商
  </a>
</p>

ByteVirt 提供多地域 VPS，适合部署 KUI VPS Agent、探针与代理节点。

- 官网：https://bytevirt.com/aff.php?aff=209
- 多地域机房与稳定网络，适用于 KUI 节点部署。

---

KUI 是一个部署在 **单一 Cloudflare Worker** 的代理节点管理与服务器探针面板。Worker Assets 托管前端和 VPS 安装组件，D1 保存配置、用户、流量和探针数据，Durable Objects 提供实时 WebSocket；无需部署传统面板服务器或额外 Realtime Worker。

[![Deploy to Cloudflare Workers](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/a6216abcd/K-UI-workers)

## 一键部署

1. 点击上方 **Deploy to Cloudflare Workers**。
2. 登录 Cloudflare，选择账户并确认 Worker 名称。
3. Cloudflare 会自动创建并绑定 D1 数据库到 `DB`，同时创建实时状态需要的 Durable Objects。不要删除这些 bindings。
4. 部署成功后直接打开 Worker 地址即可登录。首次访问会自动初始化所有 D1 数据表。

预设登录信息：

```text
用户名：admin
密码：admin
```

这是为完整一键部署准备的默认值。首次登录后必须在 Worker 的 **Settings → Variables and Secrets** 将 `ADMIN_PASSWORD` 覆盖为强 Secret 并重新部署。

内置住宅代理也已预设凭据：

```text
PROXY_USER=kui
PROXY_PASS=kui
```

启用住宅代理前，应在 Worker 的 **Variables and Secrets** 中将两项覆盖为独立的强 Secret 并重新部署。

## 自定义域名

在 Worker 的 **Settings → Domains & Routes → Add** 中绑定域名或子域名。绑定后直接使用该域名访问面板。

## 本地部署

适用于需要使用已有 D1、固定 Worker 名称或自行维护发布流程的场景。

```bash
git clone https://github.com/a6216abcd/K-UI-workers.git
cd K-UI-workers
npm install
npx wrangler login
npx wrangler deploy
```

当前 `wrangler.jsonc` 未指定 D1 ID，首次部署会自动创建数据库和实时 Durable Objects。若需要使用已有 D1，在 Cloudflare Dashboard 的 Worker **Settings → Bindings** 中将 `DB` 重绑到目标数据库后重新部署。

生产环境请立即替换默认密码：

```bash
npx wrangler secret put ADMIN_PASSWORD
npx wrangler deploy
```

本地预览：

```bash
npm run dev
```

## 已内置实时服务

实时 WebSocket、Agent 在线状态、即时配置刷新、公开探针实时更新和观众频率自适应均已内置于主 Worker。

部署后无需配置：

- `REALTIME_URL`
- `PAGES_ORIGIN`
- 单独的 Realtime Worker
- 单独的 Realtime D1 或 Durable Objects

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
  |- /agent/ws、/dashboard/*、/public/ws：内置实时服务
  |- Cron: 离线检查
  |- D1 (DB): 配置、用户、节点、流量、探针数据
  `- Durable Objects: VPS 实时状态与 Dashboard Hub
```

## 注意事项

- 一键部署默认使用 `admin/admin` 和住宅代理凭据 `kui/kui`。公开使用前必须将 `ADMIN_PASSWORD`、`PROXY_USER`、`PROXY_PASS` 覆盖为 Secret。
- 不要提交自定义 `ADMIN_PASSWORD`、D1 ID、Telegram Token 或代理凭据。
- `DB` 是固定 binding 名称，修改会导致后端无法访问数据库。
- 修改 Worker Variables 或 Bindings 后需要重新部署。
- 使用已有 D1 时，确认 `DB` 绑定指向正确数据库。
- `workspace-preview.html` 仅用于本地预览，不参与 Worker 静态资源发布。

## 开源协议

MIT
