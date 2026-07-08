#!/usr/bin/env bash
# ==========================================================
# KUI 住宅IP代理 Agent 安装脚本 (Residential Proxy Agent)
# 用法:
#   bash <(curl -sL https://<KUI_PAGES>/vps/residential-proxy.sh) \
#        --domain https://<KUI_PAGES> --controller https://<RESIDENTIAL_CTRL>
#   --domain      : 本仓库 (KUI Pages) 域名，用于下载 /vps/ 下的 agent 脚本
#   --controller  : 住宅IP代理控制器域名 (Free-Residential-IP-Proxy-Controller 部署地址)
#                   即 agent 心跳上报 (C2) 地址，对应面板 PROXY_CTRL_URL
# ==========================================================
set -euo pipefail

DOMAIN=""
CONTROLLER=""

while [ "$#" -gt 0 ]; do
    case $1 in
        --domain) DOMAIN="$2"; shift 2 ;;
        --controller) CONTROLLER="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if [ -z "$DOMAIN" ]; then
    echo "❌ 错误: 缺少 --domain (本仓库域名，用于拉取 /vps/ 下的 agent 脚本)"
    exit 1
fi
if [ -z "$CONTROLLER" ]; then
    CONTROLLER="$DOMAIN"
fi

export C2_URL="$CONTROLLER"
export WEB_USER="${WEB_USER:-admin}"
export WEB_PASS="${WEB_PASS:-admin888}"

echo "=========================================================="
echo "     Proxy Controller (Active-Standby Multi-Tunnel)    "
echo "=========================================================="
echo "[*] 操作系统: $(uname -srm)"
echo "[*] 包管理器检测中..."

detect_pkg_manager() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "apt"
    elif command -v apk >/dev/null 2>&1; then
        echo "apk"
    elif command -v yum >/dev/null 2>&1; then
        echo "yum"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    else
        echo ""
    fi
}

detect_init_system() {
    if [ -d /run/systemd/system ] || command -v systemctl >/dev/null 2>&1; then
        echo "systemd"
    elif [ -f /sbin/openrc-run ] || [ -d /etc/init.d ]; then
        echo "openrc"
    else
        echo ""
    fi
}

PKG_MGR=$(detect_pkg_manager)
INIT_SYS=$(detect_init_system)

echo "[*] 包管理器: ${PKG_MGR:-未识别}"
echo "[*] 初始化系统: ${INIT_SYS:-未识别}"

if [ -z "$PKG_MGR" ]; then
    echo "❌ 错误: 未识别包管理器，请手动安装 openvpn python3 curl iproute2 iptables"
    exit 1
fi

if [ -z "$INIT_SYS" ]; then
    echo "⚠️  警告: 未识别初始化系统，将尝试手动启动代理进程"
fi

install_dependencies() {
    echo "[0/4] 安装系统依赖..."
    case "$PKG_MGR" in
        apt)
            apt-get update -q || { echo "❌ apt-get update 失败"; exit 1; }
            apt-get install -y --no-install-recommends \
                openvpn python3 curl iproute2 iptables cron psmisc \
                || { echo "❌ 依赖安装失败"; exit 1; }
            ;;
        apk)
            apk update || true
            apk add --no-cache \
                openvpn python3 curl iproute2 iptables dcron psmisc \
                || { echo "❌ apk 依赖安装失败"; exit 1; }
            ;;
        yum|dnf)
            $PKG_MGR install -y \
                openvpn python3 curl iproute2 iptables cron psmisc \
                || { echo "❌ $PKG_MGR 依赖安装失败"; exit 1; }
            ;;
    esac
    echo "[+] 依赖安装完成"
}

setup_sysctl() {
    echo "[1/4] 配置内核网络参数..."
    cat > /etc/sysctl.d/99-proxy-lite.conf << 'SYSCTL'
net.ipv4.conf.all.rp_filter=2
net.ipv4.conf.default.rp_filter=2
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
SYSCTL
    if command -v sysctl >/dev/null 2>&1; then
        sysctl --system >/dev/null 2>&1 || {
            echo "⚠️  sysctl --system 部分失败，尝试单独应用..."
            sysctl -w net.ipv4.conf.all.rp_filter=2 >/dev/null 2>&1 || true
            sysctl -w net.ipv4.conf.default.rp_filter=2 >/dev/null 2>&1 || true
            sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
            sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null 2>&1 || true
        }
    fi
    echo "[+] 内核参数配置完成"
}

download_agents() {
    echo "[2/4] 从安全中心拉取双活极速引擎..."
    mkdir -p /opt/proxy_lite/configs
    cd /opt/proxy_lite

    curl -fSL --retry 3 --retry-delay 2 -o lite_manager.py "${DOMAIN}/vps/lite_manager.py" || {
        echo "❌ 下载 lite_manager.py 失败，请检查域名: ${DOMAIN}/vps/lite_manager.py"
        exit 1
    }
    curl -fSL --retry 3 --retry-delay 2 -o proxy_server.py "${DOMAIN}/vps/proxy_server.py" || {
        echo "❌ 下载 proxy_server.py 失败，请检查域名: ${DOMAIN}/vps/proxy_server.py"
        exit 1
    }
    chmod 644 /opt/proxy_lite/lite_manager.py /opt/proxy_lite/proxy_server.py
    echo "[+] 引擎文件下载完成"
}

install_service() {
    echo "[3/4] 配置系统守护服务..."

    if [ "$INIT_SYS" = "systemd" ]; then
        SERVICE_FILE="/lib/systemd/system/proxy-lite.service"
        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Proxy Core Engine (Active-Standby)
After=network.target

[Service]
Type=simple
Environment="C2_URL=${CONTROLLER}"
Environment="WEB_USER=${WEB_USER:-admin}"
Environment="WEB_PASS=${WEB_PASS:-admin888}"
Environment="PROXY_USER=${PROXY_USER:-proxy}"
Environment="PROXY_PASS=${PROXY_PASS:-888888}"
Environment="PYTHONIOENCODING=utf-8"
Environment="LANG=C.UTF-8"
WorkingDirectory=/opt/proxy_lite
ExecStart=/usr/bin/python3 -u lite_manager.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable proxy-lite.service
        systemctl restart proxy-lite.service
        echo "[+] 引擎更新成功！主备双活通道、异步刷IP逻辑已全量加载。"
    else
        echo "[*] 未检测到 systemd，跳过 systemd 服务安装"
        echo "    请手动启动: cd /opt/proxy_lite && python3 -u lite_manager.py"
    fi
}

main() {
    install_dependencies
    setup_sysctl
    download_agents
    install_service

    echo ""
    echo "=========================================================="
    echo "[+] 住宅IP代理引擎部署完成！"
    echo "=========================================================="
    echo "    检查状态: systemctl status proxy-lite"
    echo "    查看日志: journalctl -u proxy-lite -f"
    echo "=========================================================="
}

main "$@"
