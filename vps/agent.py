# -*- coding: utf-8 -*-
import urllib.request
import urllib.parse
import json
import os
import time
import subprocess
import re
import sys
import base64
from datetime import datetime

# 强制系统编码锁
if sys.stdout.encoding != 'UTF-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

CONF_FILE = "/opt/kui/config.json"
SINGBOX_CONF_PATH = "/etc/sing-box/config.json"

try:
    with open(CONF_FILE, 'r') as f:
        env = json.load(f)
except Exception:
    print("Failed to read config file.")
    exit(1)

API_URL = env["api_url"]
REPORT_URL = env["report_url"]
VPS_IP = env["ip"]
TOKEN = env["token"]

HEADERS = {'Content-Type': 'application/json', 'Authorization': TOKEN, 'User-Agent': 'KUI-Unified-Agent/2.0'}

# 🌟 住宅IP代理：凭证与端口统一取自环境变量（与 Pages 端 PROXY_USER/PROXY_PASS/PROXY_PORT 保持一致）
PROXY_USER = os.environ.get("PROXY_USER", "proxy")
PROXY_PASS = os.environ.get("PROXY_PASS", "888888")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "7920"))
BASE_URL = API_URL.rsplit('/api/', 1)[0] if '/api/' in API_URL else API_URL
# 住宅IP代理后端：默认与 KUI 同域；独立部署 Free-Residential-IP-Proxy-Controller 时，
# 通过环境变量 PROXY_API_URL 或 config.json 的 proxy_api 指向其地址。
PROXY_API = os.environ.get("PROXY_API_URL") or (env.get("proxy_api") if isinstance(env, dict) else None) or BASE_URL

# 住宅IP代理控制器认证：优先使用控制器专用 Basic Auth，回退为 Bearer Token
PROXY_CTRL_USER = os.environ.get("PROXY_CTRL_USER", env.get("proxy_ctrl_user", "") if isinstance(env, dict) else "")
PROXY_CTRL_PASS = os.environ.get("PROXY_CTRL_PASS", env.get("proxy_ctrl_pass", "") if isinstance(env, dict) else "")

def _proxy_ctrl_headers():
    if PROXY_CTRL_USER and PROXY_CTRL_PASS:
        return { 'User-Agent': 'Mozilla/5.0', 'Authorization': 'Basic ' + base64.b64encode(f"{PROXY_CTRL_USER}:{PROXY_CTRL_PASS}".encode()).decode() }
    return HEADERS

last_reported_bytes = {}
argo_tunnels = {}
prev_cpu_total = prev_cpu_idle = 0
prev_rx = prev_tx = 0
loop_counter = 0

# 🌟 住宅IP代理配置缓存
current_proxy_config = {}

# 🌟 动态心跳间隔，默认 5 秒
global_interval = 5

# 🌟 增加全局 Ping 状态缓存锁，防止在非测速轮次上传 '0' 导致前端图表归零
last_pings = {"ct": "0", "cu": "0", "cm": "0", "bd": "0"}

# --- 缓存静态信息 ---
cached_os = cached_arch = cached_cpu_info = cached_virt = None

def get_static_sysinfo():
    global cached_os, cached_arch, cached_cpu_info, cached_virt
    if not cached_os:
        try:
            with open('/etc/os-release') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        cached_os = line.split('=')[1].strip().strip('"')
                        break
        except: cached_os = os.popen('uname -srm').read().strip()
    if not cached_arch: cached_arch = os.popen('uname -m').read().strip()
    if not cached_cpu_info:
        try:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if 'model name' in line:
                        cached_cpu_info = line.split(':')[1].strip()
                        break
        except: cached_cpu_info = "Unknown CPU"
    if not cached_virt:
        virt = os.popen('systemd-detect-virt 2>/dev/null').read().strip()
        if not virt or virt == 'none':
            if 'lxc' in open('/proc/1/environ', 'r', errors='ignore').read(): virt = 'lxc'
            elif 'docker' in open('/proc/1/environ', 'r', errors='ignore').read(): virt = 'docker'
            elif os.path.exists('/proc/user_beancounters'): virt = 'openvz'
            elif 'kvm' in open('/proc/cpuinfo', 'r', errors='ignore').read().lower(): virt = 'kvm'
            elif 'qemu' in open('/proc/cpuinfo', 'r', errors='ignore').read().lower(): virt = 'qemu'
            else: virt = "KVM/Physical"
        cached_virt = virt.upper()
    return cached_os, cached_arch, cached_cpu_info, cached_virt

def get_http_ping(url):
    try:
        out = subprocess.check_output(f'curl -o /dev/null -s -m 2 -w "%{{time_total}}" "http://{url}"', shell=True).decode().strip()
        return str(int(float(out) * 1000))
    except: return "0"

def get_net_dev_bytes():
    rx = tx = 0
    try:
        with open('/proc/net/dev') as f:
            lines = f.readlines()[2:]
            for line in lines:
                parts = line.split()
                if parts[0] != 'lo:':
                    rx += int(parts[1])
                    tx += int(parts[9])
    except: pass
    return rx, tx

def ensure_firewall_open(port):
    # 验证端口参数
    try:
        port_int = int(port)
        if not (1 <= port_int <= 65535):
            raise ValueError(f"端口 {port} 超出有效范围 (1-65535)")
    except (ValueError, TypeError):
        raise ValueError(f"无效的端口参数: {port}")
    
    port = str(port_int)
    for protocol in ["tcp", "udp"]:
        cmds = [
            f"iptables -C INPUT -p {protocol} --dport {port} -j ACCEPT 2>/dev/null || iptables -I INPUT -p {protocol} --dport {port} -j ACCEPT",
            f"iptables -C OUTPUT -p {protocol} --sport {port} -j ACCEPT 2>/dev/null || iptables -I OUTPUT -p {protocol} --sport {port} -j ACCEPT",
            f"ip6tables -C INPUT -p {protocol} --dport {port} -j ACCEPT 2>/dev/null || ip6tables -I INPUT -p {protocol} --dport {port} -j ACCEPT",
            f"ip6tables -C OUTPUT -p {protocol} --sport {port} -j ACCEPT 2>/dev/null || ip6tables -I OUTPUT -p {protocol} --sport {port} -j ACCEPT"
        ]
        for cmd in cmds: subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)
        if subprocess.run("command -v ufw", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            subprocess.run(f"ufw allow {port}/{protocol} >/dev/null 2>&1", shell=True)

def get_port_traffic(port, protocol="tcp"):
    ensure_firewall_open(port)
    try:
        in_bytes = out_bytes = 0
        
        # 验证端口是否存在于iptables规则中
        def check_port_exists(port, protocol):
            try:
                # 检查IPv4规则
                result = subprocess.run(f"iptables -L INPUT -n --line-numbers | grep -E 'dpt:{port}|spt:{port}'", 
                                      shell=True, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    return True
                
                # 检查IPv6规则
                result6 = subprocess.run(f"ip6tables -L INPUT -n --line-numbers | grep -E 'dpt:{port}|spt:{port}'", 
                                        shell=True, capture_output=True, text=True)
                if result6.returncode == 0 and result6.stdout.strip():
                    return True
                    
                return False
            except Exception:
                return False
        
        # 只有在端口存在于iptables规则中时才进行流量统计
        if check_port_exists(port, protocol):
            # 统计输入流量
            try:
                if protocol in ["tcp", "all"]:
                    result = subprocess.run(f"iptables -L INPUT -n --line-numbers | grep 'dpt:{port}'", 
                                          shell=True, capture_output=True, text=True)
                    if result.returncode == 0:
                        for line in result.stdout.strip().split('\n'):
                            if line.strip():
                                parts = line.split()
                                if len(parts) >= 10:  # 确保有足够的字段
                                    try:
                                        in_bytes += int(parts[1])
                                    except (ValueError, IndexError):
                                        continue
            except Exception:
                pass
            
            # 统计输出流量
            try:
                if protocol in ["tcp", "all"]:
                    result = subprocess.run(f"iptables -L OUTPUT -n --line-numbers | grep 'spt:{port}'", 
                                          shell=True, capture_output=True, text=True)
                    if result.returncode == 0:
                        for line in result.stdout.strip().split('\n'):
                            if line.strip():
                                parts = line.split()
                                if len(parts) >= 10:
                                    try:
                                        out_bytes += int(parts[1])
                                    except (ValueError, IndexError):
                                        continue
            except Exception:
                pass
            
            # 统计IPv6流量
            try:
                if protocol in ["tcp", "all"]:
                    result6 = subprocess.run(f"ip6tables -L INPUT -n --line-numbers | grep 'dpt:{port}'", 
                                           shell=True, capture_output=True, text=True)
                    if result6.returncode == 0:
                        for line in result6.stdout.strip().split('\n'):
                            if line.strip():
                                parts = line.split()
                                if len(parts) >= 10:
                                    try:
                                        in_bytes += int(parts[1])
                                    except (ValueError, IndexError):
                                        continue
            except Exception:
                pass
            
            try:
                if protocol in ["tcp", "all"]:
                    result6 = subprocess.run(f"ip6tables -L OUTPUT -n --line-numbers | grep 'spt:{port}'", 
                                           shell=True, capture_output=True, text=True)
                    if result6.returncode == 0:
                        for line in result6.stdout.strip().split('\n'):
                            if line.strip():
                                parts = line.split()
                                if len(parts) >= 10:
                                    try:
                                        out_bytes += int(parts[1])
                                    except (ValueError, IndexError):
                                        continue
            except Exception:
                pass
        
        return in_bytes + out_bytes
    except Exception: return 0

def get_system_status(current_interval):
    global prev_cpu_total, prev_cpu_idle, prev_rx, prev_tx, loop_counter, last_pings
    stats = {"cpu": 0, "mem": 0, "disk": 0, "uptime": "Unknown", "load": "0.00", "net_in_speed": 0, "net_out_speed": 0}
    
    try:
        with open('/proc/stat', 'r') as f:
            for line in f:
                if line.startswith('cpu '):
                    p = [float(x) for x in line.split()[1:]]
                    idle, total = p[3] + p[4], sum(p)
                    if prev_cpu_total > 0 and (total - prev_cpu_total) > 0:
                        stats["cpu"] = int(100.0 * (1.0 - (idle - prev_cpu_idle) / (total - prev_cpu_total)))
                    prev_cpu_total, prev_cpu_idle = total, idle
                    break
    except Exception: pass

    try:
        with open('/proc/meminfo', 'r') as f: mem = f.read()
        t = re.search(r'MemTotal:\s+(\d+)', mem); a = re.search(r'MemAvailable:\s+(\d+)', mem)
        u = re.search(r'SwapTotal:\s+(\d+)', mem); v = re.search(r'SwapFree:\s+(\d+)', mem)
        total_ram = int(t.group(1)) // 1024 if t else 0
        avail_ram = int(a.group(1)) // 1024 if a else 0
        used_ram = total_ram - avail_ram
        if total_ram > 0: stats["mem"] = int((used_ram / total_ram) * 100)
        
        stats["ram_total"] = str(total_ram)
        stats["ram_used"] = str(used_ram)
        stats["swap_total"] = str(int(u.group(1)) // 1024) if u else "0"
        stats["swap_used"] = str((int(u.group(1)) - int(v.group(1))) // 1024) if u and v else "0"
    except Exception: pass

    try:
        df = subprocess.check_output("df -m /", shell=True).decode().split('\n')[1].split()
        stats["disk_total"] = df[1]
        stats["disk_used"] = df[2]
        stats["disk"] = int(df[4].replace('%', ''))
    except: pass

    try:
        with open('/proc/loadavg') as f: stats["load"] = " ".join(f.read().split()[:3])
        with open('/proc/uptime') as f:
            up_sec = float(f.read().split()[0])
            d, h, m = int(up_sec//86400), int((up_sec%86400)//3600), int((up_sec%3600)//60)
            stats["uptime"] = f"{d} days, {h:02d}:{m:02d}" if d > 0 else f"{h:02d}:{m:02d}"
        
        stats["boot_time"] = os.popen("uptime -s 2>/dev/null || stat -c %y / 2>/dev/null | cut -d'.' -f1").read().strip()
        stats["processes"] = str(len(os.popen("ps -e").readlines()) - 1)
        stats["tcp_conn"] = os.popen("ss -ant 2>/dev/null | grep -v 'State' | wc -l").read().strip() or "0"
        stats["udp_conn"] = os.popen("ss -anu 2>/dev/null | grep -v 'State' | wc -l").read().strip() or "0"
    except: pass

    rx_now, tx_now = get_net_dev_bytes()
    stats["net_rx"] = str(rx_now); stats["net_tx"] = str(tx_now)
    # 动态除数计算实时网速
    if prev_rx > 0: stats["net_in_speed"] = (rx_now - prev_rx) / current_interval
    if prev_tx > 0: stats["net_out_speed"] = (tx_now - prev_tx) / current_interval
    prev_rx, prev_tx = rx_now, tx_now

    # 🌟 每间隔几次循环更新一次真实的 Ping 值缓存
    if loop_counter % 4 == 0:
        idx = (loop_counter // 4) % 3
        if idx == 0: ct, cu, cm = "bj-ct-dualstack.ip.zstaticcdn.com", "bj-cu-dualstack.ip.zstaticcdn.com", "bj-cm-dualstack.ip.zstaticcdn.com"
        elif idx == 1: ct, cu, cm = "sh-ct-dualstack.ip.zstaticcdn.com", "sh-cu-dualstack.ip.zstaticcdn.com", "sh-cm-dualstack.ip.zstaticcdn.com"
        else: ct, cu, cm = "gd-ct-dualstack.ip.zstaticcdn.com", "gd-cu-dualstack.ip.zstaticcdn.com", "gd-cm-dualstack.ip.zstaticcdn.com"
        last_pings["ct"] = get_http_ping(ct)
        last_pings["cu"] = get_http_ping(cu)
        last_pings["cm"] = get_http_ping(cm)
        last_pings["bd"] = get_http_ping("lf3-ips.zstaticcdn.com")

    # 把最近一次成功的 Ping 值塞入状态发给后端，避免前端由于读到0产生断崖
    stats["ping_ct"] = last_pings["ct"]
    stats["ping_cu"] = last_pings["cu"]
    stats["ping_cm"] = last_pings["cm"]
    stats["ping_bd"] = last_pings["bd"]

    os_info, arch, cpu_info, virt = get_static_sysinfo()
    stats.update({"os": os_info, "arch": arch, "cpu_info": cpu_info, "virt": virt})

    loop_counter += 1
    return stats

def ensure_cloudflared():
    if not os.path.exists("/usr/local/bin/cloudflared"):
        os.system("curl -L -o /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /usr/local/bin/cloudflared")

def process_argo_nodes(configs):
    argo_urls = []
    expected_ports = [str(n['port']) for n in configs if n.get('protocol') == 'VLESS-Argo']
    for port in expected_ports:
        if port not in argo_tunnels:
            ensure_cloudflared()
            cmd = ["/usr/local/bin/cloudflared", "tunnel", "--edge-ip-version", "auto", "--no-autoupdate", "--url", f"http://[::1]:{port}"]
            p = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
            url = None; start_t = time.time()
            while time.time() - start_t < 15:
                line = p.stderr.readline()
                if not line: break
                m = re.search(r'https://([a-zA-Z0-9-]+\.trycloudflare\.com)', line)
                if m: url = m.group(1); break
            if url: argo_tunnels[port] = {"proc": p, "url": url}
        if port in argo_tunnels: argo_urls.append({"id": [n['id'] for n in configs if str(n['port'])==port][0], "url": argo_tunnels[port]["url"]})
    for port in list(argo_tunnels.keys()):
        if port not in expected_ports:
            argo_tunnels[port]["proc"].terminate()
            del argo_tunnels[port]
    return argo_urls

def build_singbox_config(nodes, proxy_cfg=None, peers=None, mesh=None):
    singbox_config = {
        "log": {"level": "warn"},
        "inbounds": [],
        "outbounds": [{"type": "direct", "tag": "direct-out"}],
        "route": {"rules": []}
    }
    active_certs = []

    for node in nodes:
        in_tag, proto, port = f"in-{node['id']}", node["protocol"], int(node["port"])
        sni = node.get("sni") or "addons.mozilla.org"
        clean_uuid = node['uuid'].replace('-', '')
        
        if proto in ["Hysteria2", "TUIC", "Trojan", "VLESS-WS-TLS", "AnyTLS", "Naive"]:
            cert_path, key_path = f"/opt/kui/cert_{node['id']}.pem", f"/opt/kui/key_{node['id']}.pem"
            active_certs.extend([f"cert_{node['id']}.pem", f"key_{node['id']}.pem"])
            if not os.path.exists(cert_path):
                parts = sni.split('.'); cn = f"{parts[-2]}.{parts[-1]}" if len(parts) >= 2 else sni
                conf_path = f"/opt/kui/cert_{node['id']}.conf"
                with open(conf_path, "w") as f: f.write(f"[req]\ndistinguished_name = req_distinguished_name\nx509_extensions = v3_req\nprompt = no\n[req_distinguished_name]\nCN = {cn}\n[v3_req]\nsubjectAltName = @alt_names\n[alt_names]\nDNS = {sni}\n")
                os.system(f"openssl ecparam -genkey -name prime256v1 -out {key_path} >/dev/null 2>&1")
                os.system(f"openssl req -new -x509 -days 36500 -key {key_path} -out {cert_path} -config {conf_path} -extensions v3_req >/dev/null 2>&1")
                os.system(f"chmod 644 {cert_path} {key_path}")
                try: os.remove(conf_path)
                except: pass
        
        if proto == "VLESS": singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"]}]})
        elif proto in ["XTLS-Reality", "Reality"]: singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"], "flow": "xtls-rprx-vision"}], "tls": {"enabled": True, "server_name": sni, "reality": {"enabled": True, "handshake": {"server": sni, "server_port": 443}, "private_key": node["private_key"], "short_id": [node["short_id"]]}}})
        elif proto == "Hysteria2": singbox_config["inbounds"].append({"type": "hysteria2", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"password": node["uuid"]}], "tls": {"enabled": True, "alpn": ["h3"], "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "TUIC": singbox_config["inbounds"].append({"type": "tuic", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"], "password": node["private_key"]}], "tls": {"enabled": True, "alpn": ["h3"], "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "Trojan": singbox_config["inbounds"].append({"type": "trojan", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"password": node["private_key"]}], "tls": {"enabled": True, "server_name": sni, "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "H2-Reality": singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"]}], "tls": {"enabled": True, "server_name": sni, "reality": {"enabled": True, "handshake": {"server": sni, "server_port": 443}, "private_key": node["private_key"], "short_id": [node["short_id"]]}}, "transport": {"type": "http"}})
        elif proto == "gRPC-Reality": singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"]}], "tls": {"enabled": True, "server_name": sni, "reality": {"enabled": True, "handshake": {"server": sni, "server_port": 443}, "private_key": node["private_key"], "short_id": [node["short_id"]]}}, "transport": {"type": "grpc", "service_name": "grpc"}})
        elif proto == "AnyTLS": singbox_config["inbounds"].append({"type": "anytls", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"password": node["private_key"]}], "tls": {"enabled": True, "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "Naive": singbox_config["inbounds"].append({"type": "naive", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"username": node["uuid"], "password": node["private_key"]}], "tls": {"enabled": True, "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "Socks5": singbox_config["inbounds"].append({"type": "socks", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"username": node["uuid"], "password": node["private_key"]}]})
        elif proto == "VLESS-Argo": singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"]}], "transport": {"type": "ws", "path": "/"}})
        elif proto == "dokodemo-door":
            singbox_config["inbounds"].append({ "type": "direct", "tag": in_tag, "listen": "::", "listen_port": port })
            out_tag = f"out-{node['id']}"
            if node.get("relay_type") == "internal" and node.get("chain_target"):
                t = node["chain_target"]
                outbound = { "type": t["protocol"].lower(), "tag": out_tag, "server": t["ip"], "server_port": int(t["port"]), "uuid": t["uuid"] }
                if t["protocol"] == "Reality" or t["protocol"] == "XTLS-Reality":
                    outbound["tls"] = { "enabled": True, "server_name": t["sni"], "reality": { "enabled": True, "public_key": t["public_key"], "short_id": t["short_id"] } }
                singbox_config["outbounds"].append(outbound)
            else:
                singbox_config["outbounds"].append({ "type": "direct", "tag": out_tag, "override_address": node["target_ip"], "override_port": int(node["target_port"]) })
            singbox_config["route"]["rules"].append({ "inbound": [in_tag], "outbound": out_tag })

    # --- 住宅IP代理出口 / SOCKS5 服务注入（每台 VPS 默认开启，凭证统一取自环境变量）---
    if proxy_cfg:
        if isinstance(proxy_cfg, dict):
            proxy_enabled = proxy_cfg.get("enabled", True)
            proxy_port = int(proxy_cfg.get("port", PROXY_PORT))
            proxy_user = proxy_cfg.get("user", PROXY_USER)
            proxy_pass = proxy_cfg.get("pass", PROXY_PASS)
        else:
            proxy_enabled = bool(proxy_cfg)
            proxy_port, proxy_user, proxy_pass = PROXY_PORT, PROXY_USER, PROXY_PASS
        if proxy_enabled:
            try:
                singbox_config["inbounds"].append({
                    "type": "socks",
                    "tag": "residential-socks5",
                    "listen": "::",
                    "listen_port": int(proxy_port),
                    "users": [
                        {"username": str(proxy_user), "password": str(proxy_pass)}
                    ]
                })
            except Exception:
                pass

    try:
        for filename in os.listdir("/opt/kui/"):
            if (filename.startswith("cert_") or filename.startswith("key_")) and filename.endswith(".pem"):
                if filename not in active_certs: os.remove(os.path.join("/opt/kui/", filename))
    except Exception: pass

    # --- 住宅IP跨VPS互联（mesh）：把本机节点出口链式转发到其它 VPS 的 SOCKS5，实现出口IP共享/轮换 ---
    if peers and mesh and mesh.get("enabled"):
        try:
            chain_mode = mesh.get("mode", "all")
            chain_nodes = set(str(x) for x in (mesh.get("nodes") or []))
            rr = [0]
            for node in nodes:
                if node.get("protocol") == "dokodemo-door":
                    continue
                nid = str(node["id"])
                if chain_mode == "select" and nid not in chain_nodes:
                    continue
                if not peers:
                    break
                peer = peers[rr[0] % len(peers)]
                rr[0] += 1
                out_tag = f"mesh-out-{nid}"
                srv = peer.get("socks_ip") or peer.get("ip") or ""
                singbox_config["outbounds"].append({
                    "type": "socks",
                    "tag": out_tag,
                    "server": srv,
                    "server_port": int(peer.get("port") or PROXY_PORT),
                    "username": str(peer.get("user") or PROXY_USER),
                    "password": str(peer.get("pass") or PROXY_PASS)
                })
                in_tag = f"in-{nid}"
                singbox_config["route"]["rules"].append({"inbound": [in_tag], "outbound": out_tag})
        except Exception:
            pass

    for node in nodes:
        ensure_firewall_open(node["port"])
    os.makedirs(os.path.dirname(SINGBOX_CONF_PATH), exist_ok=True)
    new_config_str = json.dumps(singbox_config, indent=2)
    old_config_str = ""
    if os.path.exists(SINGBOX_CONF_PATH):
        with open(SINGBOX_CONF_PATH, "r") as f: old_config_str = f.read()

    if new_config_str != old_config_str:
        with open(SINGBOX_CONF_PATH, "w") as f: f.write(new_config_str)
        if os.path.exists("/sbin/openrc-run") or os.path.exists("/etc/alpine-release"): os.system("rc-service sing-box restart >/dev/null 2>&1")
        else: os.system("systemctl restart sing-box >/dev/null 2>&1")

def report_status(current_nodes, argo_urls):
    global last_reported_bytes, global_interval
    status = get_system_status(global_interval)
    status["ip"] = VPS_IP
    status["argo_urls"] = argo_urls
    
    deltas = []
    current_ids = set()
    for node in current_nodes:
        nid, port = node["id"], node["port"]
        current_ids.add(nid)
        proto = "udp" if node["protocol"] in ["Hysteria2", "TUIC"] else "tcp"
        current_bytes = get_port_traffic(port, proto)
        delta = current_bytes - last_reported_bytes.get(nid, current_bytes)
        if delta > 0: deltas.append({ "id": nid, "delta_bytes": delta })
        last_reported_bytes[nid] = current_bytes

    last_reported_bytes = {k: v for k, v in last_reported_bytes.items() if k in current_ids}
    status["node_traffic"] = deltas

    try: 
        req = urllib.request.Request(REPORT_URL, data=json.dumps(status).encode(), headers=HEADERS)
        res = urllib.request.urlopen(req, timeout=5)
        resp_data = json.loads(res.read().decode('utf-8'))
        if resp_data and "interval" in resp_data:
            global_interval = max(1, int(resp_data["interval"]))
    except Exception as e: pass

def register_self():
    try:
        base_url = API_URL.rsplit('/', 1)[0]
        vps_api = f"{base_url}/vps"
        data = json.dumps({"ip": VPS_IP, "name": f"VPS-{VPS_IP}"}).encode()
        req = urllib.request.Request(vps_api, data=data, headers={**HEADERS, 'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

def fetch_proxy_config():
    try:
        req = urllib.request.Request(f"{PROXY_API}/api/proxy/config?ip={VPS_IP}", headers=_proxy_ctrl_headers())
        res = urllib.request.urlopen(req, timeout=10)
        return json.loads(res.read().decode('utf-8'))
    except Exception:
        return None

def _extract_mesh(proxy_cfg):
    # 解析 mesh 配置：优先 per-VPS toggle.mesh，其次全局 global.mesh，再退回扁平 mesh
    if not isinstance(proxy_cfg, dict):
        return {}
    toggle = proxy_cfg.get("toggle")
    if isinstance(toggle, dict) and isinstance(toggle.get("mesh"), dict):
        return toggle["mesh"]
    g = proxy_cfg.get("global")
    if isinstance(g, dict) and isinstance(g.get("mesh"), dict):
        return g["mesh"]
    m = proxy_cfg.get("mesh")
    if isinstance(m, dict):
        return m
    return {}

def fetch_proxy_mesh(country="ANY"):
    # 拉取可供本机链式转发的对端 SOCKS5 出口（mesh 互联）
    # 外部控制器对等节点列表：优先走 /api/proxies（返回 socks5:// 纯文本），本地按国家过滤
    try:
        c = (country or "ANY").upper()
        url = f"{PROXY_API}/api/proxies?ip={VPS_IP}"
        req = urllib.request.Request(url, headers=_proxy_ctrl_headers())
        raw = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        peers = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or not line.startswith('socks5://'):
                continue
            try:
                parsed = urllib.parse.urlparse(line)
                peer_country = ''
                if parsed.fragment:
                    peer_country = parsed.fragment.split('_')[0].upper()
                if c and c != "ANY" and peer_country and peer_country != c:
                    continue
                host = parsed.hostname or ''
                port = parsed.port or PROXY_PORT
                user = parsed.username or PROXY_USER
                pwd = parsed.password or PROXY_PASS
                if host:
                    peers.append({"socks_ip": host, "port": port, "user": user, "pass": pwd, "country": peer_country})
            except Exception:
                continue
        return peers
    except Exception:
        return []

def report_proxy_status():
    try:
        pc = current_proxy_config
        def _g(key, default):
            if isinstance(pc, dict):
                if key in pc: return pc[key]
                g = pc.get("global")
                if isinstance(g, dict) and key in g: return g[key]
            return default
        enabled = _g("enabled", True)
        port = int(_g("port", PROXY_PORT))
        user = _g("user", PROXY_USER)
        pwd = _g("pass", PROXY_PASS)
        country = _g("country", "")
        payload = {
            "ip": VPS_IP,
            "socks_ip": VPS_IP,
            "port": int(port),
            "user": str(user),
            "pass": str(pwd),
            "country": str(country),
            "enabled": bool(enabled),
            "last_seen": int(time.time())
        }
        req = urllib.request.Request(f"{PROXY_API}/api/proxy/report", data=json.dumps(payload).encode(), headers=_proxy_ctrl_headers())
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

def fetch_and_apply_configs():
    try:
        res = urllib.request.urlopen(urllib.request.Request(f"{API_URL}?ip={VPS_IP}", headers=HEADERS), timeout=10)
        data = json.loads(res.read().decode('utf-8'))
        if data.get("success"):
            nodes = data.get("configs", [])
            global current_proxy_config
            pc = fetch_proxy_config()
            current_proxy_config = pc if pc is not None else data.get("proxy", {})
            mesh = _extract_mesh(current_proxy_config)
            peers = []
            if mesh.get("enabled"):
                peers = fetch_proxy_mesh(mesh.get("country", "ANY"))
                exit_ip = mesh.get("exit")
                if exit_ip and exit_ip != "ANY":
                    peers = [p for p in peers if p.get("ip") == exit_ip]
            build_singbox_config(nodes, current_proxy_config, peers, mesh)
            return nodes
    except Exception:
        pass
    return None

if __name__ == "__main__":
    current_active_nodes = []
    time.sleep(2)
    register_self()
    while True:
        fetched_nodes = fetch_and_apply_configs()
        if fetched_nodes is not None: current_active_nodes = fetched_nodes
        argo_urls = process_argo_nodes(current_active_nodes)
        report_status(current_active_nodes, argo_urls)
        report_proxy_status()
        time.sleep(global_interval)
