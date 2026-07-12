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
import socket
import platform
import tempfile
import shutil
import hashlib
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
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "7920"))
BASE_URL = API_URL.rsplit('/api/', 1)[0] if '/api/' in API_URL else API_URL
# 住宅IP代理后端：默认与 KUI 同域；独立部署 Free-Residential-IP-Proxy-Controller 时，
# 通过环境变量 PROXY_API_URL 或 config.json 的 proxy_api 指向其地址。
PROXY_API = os.environ.get("PROXY_API_URL") or (env.get("proxy_api") if isinstance(env, dict) else None) or BASE_URL

# 住宅IP代理控制器认证：优先使用控制器专用 Basic Auth，回退为 Bearer Token
PROXY_CTRL_USER = os.environ.get("PROXY_CTRL_USER", env.get("proxy_ctrl_user", "") if isinstance(env, dict) else "")
PROXY_CTRL_PASS = os.environ.get("PROXY_CTRL_PASS", env.get("proxy_ctrl_pass", "") if isinstance(env, dict) else "")

def _proxy_ctrl_headers():
    if PROXY_API.rstrip('/') != BASE_URL.rstrip('/') and PROXY_CTRL_USER and PROXY_CTRL_PASS:
        return { 'User-Agent': 'Mozilla/5.0', 'Authorization': 'Basic ' + base64.b64encode(f"{PROXY_CTRL_USER}:{PROXY_CTRL_PASS}".encode()).decode() }
    return HEADERS

last_reported_bytes = {}
argo_tunnels = {}
prev_cpu_total = prev_cpu_idle = 0
prev_rx = prev_tx = 0
loop_counter = 0
last_update_check = 0

# 🌟 住宅IP代理配置缓存
current_proxy_config = {}

def check_for_update():
    global last_update_check
    now = time.time()
    if now - last_update_check < 3600:
        return False
    last_update_check = now
    temp_path = os.path.abspath(__file__) + ".update.py"
    try:
        update_url = f"{BASE_URL}/api/agent_update?ip={urllib.parse.quote(VPS_IP, safe='')}"
        request = urllib.request.Request(update_url, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            source = response.read(2 * 1024 * 1024 + 1)
            expected_hash = response.headers.get("X-Agent-SHA256", "").lower()
        if not source or len(source) > 2 * 1024 * 1024 or not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or hashlib.sha256(source).hexdigest() != expected_hash:
            raise ValueError("agent update checksum mismatch")
        with open(__file__, "rb") as current:
            if hashlib.sha256(current.read()).hexdigest() == expected_hash:
                return False
        with open(temp_path, "wb") as update_file:
            update_file.write(source)
        os.chmod(temp_path, 0o700)
        checked = subprocess.run([sys.executable, "-m", "py_compile", temp_path], capture_output=True, text=True)
        if checked.returncode != 0:
            raise ValueError(f"agent update compile failed: {checked.stderr.strip()}")
        os.replace(temp_path, os.path.abspath(__file__))
        print(f"[agent] updated to {expected_hash[:12]}, restarting", flush=True)
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])
    except Exception as error:
        print(f"[agent] update check failed: {error}", flush=True)
        try:
            if os.path.exists(temp_path): os.remove(temp_path)
        except Exception:
            pass
    return False

# 🌟 动态心跳间隔，默认 5 秒
global_interval = 5

# 🌟 增加全局 Ping 状态缓存锁，防止在非测速轮次上传 '0' 导致前端图表归零
last_pings = {"ct": "0", "cu": "0", "cm": "0", "bd": "0"}
dynamic_ping = {"ct": None, "cu": None, "cm": None}
pending_report_id = None
pending_report_bytes = None
pending_node_traffic = None

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
            try:
                with open('/proc/1/environ', 'r', errors='ignore') as f: init_env = f.read()
                with open('/proc/cpuinfo', 'r', errors='ignore') as f: cpu_info = f.read().lower()
                if 'lxc' in init_env: virt = 'lxc'
                elif 'docker' in init_env: virt = 'docker'
                elif os.path.exists('/proc/user_beancounters'): virt = 'openvz'
                elif 'kvm' in cpu_info: virt = 'kvm'
                elif 'qemu' in cpu_info: virt = 'qemu'
                else: virt = "KVM/Physical"
            except Exception:
                virt = "Unknown"
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

def _read_iptables_port_bytes(port):
    """基于 ensure_firewall_open 插入的 dport(INPUT)/sport(OUTPUT) ACCEPT 规则，
    读取该端口的进出累计字节，实现真正的单节点精确计量。
    返回 None 表示未找到规则或读取失败（上层据此返回 0，避免误计）。"""
    port_s = str(port)
    total = 0
    found = False
    for tool, chain, key in (
        ("iptables", "INPUT", f"dpt:{port_s}"), ("iptables", "OUTPUT", f"spt:{port_s}"),
        ("ip6tables", "INPUT", f"dpt:{port_s}"), ("ip6tables", "OUTPUT", f"spt:{port_s}"),
    ):
        try:
            out = subprocess.run([tool, "-nvxL", chain], capture_output=True, text=True, timeout=3).stdout
        except Exception:
            continue
        key_pattern = re.compile(rf'(?<!\d){re.escape(key)}(?!\d)')
        for line in out.splitlines():
            if "ACCEPT" not in line or not key_pattern.search(line):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                # iptables -nvx 列序: pkts bytes target ...
                total += int(parts[1])
                found = True
            except Exception:
                pass
    return total if found else None

def get_port_traffic(port, protocol="tcp"):
    ensure_firewall_open(port)

    # 查找匹配端口对应的节点 inbound tag
    node_tag = None
    for node in current_active_nodes:
        if str(node.get("port")) == str(port):
            node_tag = f"in-{node['id']}"
            break

    # 优先：sing-box HTTP API 获取单入站精确流量（cumulative bytes）
    if node_tag:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:9090/stats/inbound/{node_tag}",
                headers={"User-Agent": "KUI-Agent"}
            )
            with urllib.request.urlopen(req, timeout=2) as r:
                raw = r.read().decode("utf-8")
                data = json.loads(raw)
                val = data.get("value")
                if val is not None:
                    return int(val)
                # 部分版本把 bytes 装在 .bytes 字段
                b = data.get("bytes")
                if b is not None:
                    return int(b)
                # 部分版本返回数组 [up, down]
                arr = data.get("traffic") or data.get("value_list")
                if isinstance(arr, list) and len(arr) >= 2:
                    return int(arr[0]) + int(arr[1])
        except Exception:
            pass

    # 兜底：iptables 单端口累计字节（真正的单节点计量）。
    # 注意：绝不能回退到"系统全网卡总流量"——那样每个节点都会拿到同一个总量，
    # report_status 里逐节点累加会把用户流量放大 N 倍（N=节点数）。
    port_bytes = _read_iptables_port_bytes(port)
    if port_bytes is not None:
        return port_bytes

    return 0

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
        last_pings["ct"] = get_http_ping(dynamic_ping["ct"] or ct)
        last_pings["cu"] = get_http_ping(dynamic_ping["cu"] or cu)
        last_pings["cm"] = get_http_ping(dynamic_ping["cm"] or cm)
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
    target = "/usr/local/bin/cloudflared"
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return True
    arch_map = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64", "armv7l": "arm"}
    arch = arch_map.get(platform.machine().lower())
    if not arch:
        return False
    fd, tmp_path = tempfile.mkstemp(prefix="cloudflared-", dir="/usr/local/bin")
    os.close(fd)
    try:
        result = subprocess.run(["curl", "-fL", "--retry", "3", "-o", tmp_path, f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"], timeout=120)
        if result.returncode != 0 or os.path.getsize(tmp_path) == 0:
            return False
        os.chmod(tmp_path, 0o755)
        os.replace(tmp_path, target)
        return True
    except Exception:
        return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def stop_process(process):
    if not process:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except Exception:
        try: process.kill(); process.wait(timeout=3)
        except Exception: pass

def process_argo_nodes(configs):
    argo_urls = []
    expected_ports = [str(n['port']) for n in configs if n.get('protocol') == 'VLESS-Argo']
    for port in list(argo_tunnels.keys()):
        if argo_tunnels[port]["proc"].poll() is not None:
            stop_process(argo_tunnels[port]["proc"])
            argo_tunnels[port].get("log_file") and argo_tunnels[port]["log_file"].close()
            del argo_tunnels[port]
    for port in expected_ports:
        if port not in argo_tunnels:
            if not ensure_cloudflared():
                continue
            cmd = ["/usr/local/bin/cloudflared", "tunnel", "--edge-ip-version", "auto", "--no-autoupdate", "--url", f"http://[::1]:{port}"]
            log_path = f"/opt/kui/argo_{port}.log"
            log_file = open(log_path, "w+")
            p = subprocess.Popen(cmd, stderr=log_file, stdout=subprocess.DEVNULL, text=True)
            url = None; start_t = time.time()
            while time.time() - start_t < 15:
                if p.poll() is not None: break
                log_file.flush(); log_file.seek(0)
                match = re.search(r'https://([a-zA-Z0-9-]+\.trycloudflare\.com)', log_file.read())
                if match: url = match.group(1); break
                time.sleep(0.5)
            if url: argo_tunnels[port] = {"proc": p, "url": url, "log_file": log_file}
            else: stop_process(p); log_file.close()
        if port in argo_tunnels: argo_urls.append({"id": [n['id'] for n in configs if str(n['port'])==port][0], "url": argo_tunnels[port]["url"]})
    for port in list(argo_tunnels.keys()):
        if port not in expected_ports:
            stop_process(argo_tunnels[port]["proc"])
            argo_tunnels[port].get("log_file") and argo_tunnels[port]["log_file"].close()
            del argo_tunnels[port]
    return argo_urls

def build_chain_outbound(target, tag):
    proto = target.get("protocol", "")
    outbound = {"tag": tag, "server": target["ip"], "server_port": int(target["port"])}
    if proto in ["VLESS", "XTLS-Reality", "Reality", "H2-Reality", "gRPC-Reality"]:
        outbound.update({"type": "vless", "uuid": target["uuid"]})
        if "Reality" in proto:
            outbound["tls"] = {"enabled": True, "server_name": target.get("sni") or "addons.mozilla.org", "reality": {"enabled": True, "public_key": target.get("public_key", ""), "short_id": target.get("short_id", "")}}
        if proto in ["XTLS-Reality", "Reality"]: outbound["flow"] = "xtls-rprx-vision"
        if proto == "H2-Reality": outbound["transport"] = {"type": "http"}
        if proto == "gRPC-Reality": outbound["transport"] = {"type": "grpc", "service_name": "grpc"}
    elif proto == "Trojan":
        outbound.update({"type": "trojan", "password": target.get("password", ""), "tls": {"enabled": True, "server_name": target.get("sni") or "addons.mozilla.org", "insecure": True}})
    elif proto == "Hysteria2":
        outbound.update({"type": "hysteria2", "password": target.get("uuid") or target.get("password", ""), "tls": {"enabled": True, "server_name": target.get("sni") or "addons.mozilla.org", "insecure": True}})
    elif proto == "TUIC":
        outbound.update({"type": "tuic", "uuid": target["uuid"], "password": target.get("password", ""), "tls": {"enabled": True, "server_name": target.get("sni") or "addons.mozilla.org", "insecure": True}})
    elif proto == "AnyTLS":
        outbound.update({"type": "anytls", "password": target.get("password", ""), "tls": {"enabled": True, "server_name": target.get("sni") or "addons.mozilla.org", "insecure": True}})
    else:
        return None
    return outbound

def build_singbox_config(nodes, proxy_cfg=None, peers=None, mesh=None, socks5_outbound=None):
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
                os.chmod(cert_path, 0o644)
                os.chmod(key_path, 0o600)
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
                outbound = build_chain_outbound(t, out_tag)
                if outbound:
                    singbox_config["outbounds"].append(outbound)
                else:
                    continue
            else:
                singbox_config["outbounds"].append({ "type": "direct", "tag": out_tag, "override_address": node["target_ip"], "override_port": int(node["target_port"]) })
            singbox_config["route"]["rules"].append({ "inbound": [in_tag], "outbound": out_tag })

    # --- 住宅IP代理出口 / SOCKS5 服务注入（如端口已被 proxy_server.py 占用则跳过，避免双进程抢端口炸 sing-box）---
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
            port_in_use = False
            for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
                try:
                    test = socket.socket(family, socket.SOCK_STREAM)
                    test.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    result = test.connect_ex((addr, int(proxy_port)))
                    test.close()
                    if result == 0:
                        port_in_use = True
                        break
                except Exception:
                    pass
            if not port_in_use:
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
            else:
                print(f"[agent] 端口 {proxy_port} 已被 proxy_server 占用，跳过 sing-box SOCKS5 注入", flush=True)

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

    # --- SOCKS5 出站代理：全局出站 / 按分类选择性出站（YouTube / AI / 谷歌 / 流媒体）---
    if socks5_outbound and socks5_outbound.get("enabled"):
        try:
            s5_addr = socks5_outbound.get("addr", "")
            s5_port = int(socks5_outbound.get("port", 0))
            if s5_addr and s5_port > 0:
                s5_tag = "socks5-outbound"
                s5_outbound = {"type": "socks", "tag": s5_tag, "server": s5_addr, "server_port": s5_port}
                s5_user = socks5_outbound.get("user", "")
                s5_pass = socks5_outbound.get("pass", "")
                if s5_user:
                    s5_outbound["username"] = str(s5_user)
                if s5_pass:
                    s5_outbound["password"] = str(s5_pass)
                singbox_config["outbounds"].append(s5_outbound)
                s5_mode = socks5_outbound.get("mode", "global")
                if s5_mode == "selective":
                    # 按分类选择性出站：仅勾选的分类域名走 SOCKS5
                    CATEGORY_DOMAINS = {
                        "youtube": {
                            "keywords": ["youtube", "youtu", "googlevideo", "ytimg"],
                            "suffixes": [".youtube.com", ".youtu.be", ".googlevideo.com", ".ytimg.com"]
                        },
                        "ai": {
                            "keywords": ["openai", "chatgpt", "claude", "anthropic", "gemini", "bard", "copilot", "grok", "perplexity", "midjourney"],
                            "suffixes": [".openai.com", ".anthropic.com", ".claude.ai", ".chatgpt.com", ".deepmind.com", ".cohere.com", ".huggingface.co", ".perplexity.ai", ".midjourney.com", ".ai.com"]
                        },
                        "google": {
                            "keywords": ["google"],
                            "suffixes": [".google.com", ".googleapis.com", ".googleusercontent.com", ".googlesyndication.com", ".googleadservices.com", ".gstatic.com", ".google-analytics.com"]
                        },
                        "streaming": {
                            "keywords": ["netflix", "hulu", "disney", "hbo", "spotify", "tiktok", "twitch", "vimeo", "dailymotion", "bilibili", "crunchyroll", "peacock"],
                            "suffixes": [".netflix.com", ".hulu.com", ".disneyplus.com", ".hbomax.com", ".spotify.com", ".tiktok.com", ".twitch.tv", ".vimeo.com", ".dailymotion.com", ".bilibili.com", ".crunchyroll.com", ".peacocktv.com"]
                        }
                    }
                    s5_domains_raw = socks5_outbound.get("domains", "")
                    selected = []
                    if s5_domains_raw:
                        try:
                            parsed = json.loads(s5_domains_raw)
                            if isinstance(parsed, dict):
                                selected = parsed.get("categories", [])
                        except Exception:
                            pass
                    all_keywords = []
                    all_suffixes = []
                    for cat in selected:
                        entry = CATEGORY_DOMAINS.get(cat)
                        if entry:
                            all_keywords.extend(entry["keywords"])
                            all_suffixes.extend(entry["suffixes"])
                    if all_keywords or all_suffixes:
                        route_rule = {"domain_keyword": all_keywords, "domain_suffix": all_suffixes, "outbound": s5_tag}
                        singbox_config["route"]["rules"].append(route_rule)
                else:
                    # 全局出站：所有非转发节点流量走 SOCKS5
                    existing_routed = set()
                    for rule in singbox_config["route"]["rules"]:
                        for ib in rule.get("inbound", []):
                            existing_routed.add(ib)
                    for node in nodes:
                        if node.get("protocol") == "dokodemo-door":
                            continue
                        in_tag = f"in-{node['id']}"
                        if in_tag not in existing_routed:
                            singbox_config["route"]["rules"].append({"inbound": [in_tag], "outbound": s5_tag})
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
        temp_config = SINGBOX_CONF_PATH + ".tmp"
        with open(temp_config, "w") as f: f.write(new_config_str)
        os.chmod(temp_config, 0o600)
        sing_box = shutil.which("sing-box")
        if not sing_box:
            print("[agent] sing-box binary not found; keeping last known-good config", flush=True)
            os.remove(temp_config)
            return
        checked = subprocess.run([sing_box, "check", "-c", temp_config], capture_output=True, text=True)
        if checked.returncode != 0:
            print(f"[agent] sing-box config rejected: {checked.stderr.strip()}", flush=True)
            os.remove(temp_config)
            return
        os.replace(temp_config, SINGBOX_CONF_PATH)
        if os.path.exists("/sbin/openrc-run") or os.path.exists("/etc/alpine-release"):
            subprocess.run(["rc-service", "sing-box", "restart"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["systemctl", "restart", "sing-box"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def report_status(current_nodes, argo_urls):
    global last_reported_bytes, global_interval, dynamic_ping, pending_report_id, pending_report_bytes, pending_node_traffic
    status = get_system_status(global_interval)
    status["ip"] = VPS_IP
    status["argo_urls"] = argo_urls
    
    deltas = []
    pending_bytes = dict(last_reported_bytes)
    current_ids = set()
    for node in current_nodes:
        nid, port = node["id"], node["port"]
        current_ids.add(nid)
        proto = "udp" if node["protocol"] in ["Hysteria2", "TUIC"] else "tcp"
        current_bytes = get_port_traffic(port, proto)
        baseline = pending_bytes.get(nid, current_bytes)
        delta = current_bytes - baseline if current_bytes >= baseline else current_bytes
        if delta > 0: deltas.append({ "id": nid, "delta_bytes": delta })
        pending_bytes[nid] = current_bytes

    if not pending_report_id:
        pending_report_id = f"{VPS_IP}:{time.time_ns()}"
        pending_report_bytes = {k: v for k, v in pending_bytes.items() if k in current_ids}
        pending_node_traffic = deltas
    status["node_traffic"] = pending_node_traffic
    status["report_id"] = pending_report_id

    try: 
        req = urllib.request.Request(REPORT_URL, data=json.dumps(status).encode(), headers=HEADERS)
        res = urllib.request.urlopen(req, timeout=5)
        resp_data = json.loads(res.read().decode('utf-8'))
        last_reported_bytes = pending_report_bytes
        pending_report_id = None
        pending_report_bytes = None
        pending_node_traffic = None
        if resp_data and "interval" in resp_data:
            global_interval = min(max(1, int(resp_data["interval"])), 3600)
        for key in ("ct", "cu", "cm"):
            value = resp_data.get(f"ping_{key}")
            dynamic_ping[key] = None if not value or value == "default" else value
    except Exception as e: pass

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
        proxy_path = "/api/proxy/proxies" if PROXY_API.rstrip('/') == BASE_URL.rstrip('/') else "/api/proxies"
        url = f"{PROXY_API}{proxy_path}?ip={VPS_IP}"
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
                    peers.append({"ip": host, "socks_ip": host, "port": port, "user": user, "pass": pwd, "country": peer_country})
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
                    peers = [p for p in peers if p.get("socks_ip") == exit_ip or p.get("ip") == exit_ip]
            socks5_outbound = data.get("socks5_outbound", {})
            build_singbox_config(nodes, current_proxy_config, peers, mesh, socks5_outbound)
            return nodes
    except Exception:
        pass
    return None

if __name__ == "__main__":
    current_active_nodes = []
    time.sleep(2)
    while True:
        try:
            check_for_update()
            fetched_nodes = fetch_and_apply_configs()
            if fetched_nodes is not None: current_active_nodes = fetched_nodes
            argo_urls = process_argo_nodes(current_active_nodes)
            report_status(current_active_nodes, argo_urls)
            report_proxy_status()
        except Exception as error:
            print(f"[agent] main loop error: {error}", flush=True)
        time.sleep(global_interval)
