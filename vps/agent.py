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
import hmac
import threading
import configparser
import ipaddress
try:
    from realtime_client import RealtimeChannel
except ImportError:
    class RealtimeChannel:
        def __init__(self, *args, **kwargs): self.connected = False; self.enabled = False; self.ever_connected = False; self.last_disconnected = 0; self.started_at = 0
        def start(self): pass
        def stop(self): pass
        def send(self, data, message_type="status"): return False
from datetime import datetime

# 强制系统编码锁
if sys.stdout.encoding != 'UTF-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

CONF_FILE = "/opt/kui/config.json"
SINGBOX_CONF_PATH = "/etc/sing-box/config.json"
WARP_CONF_PATH = "/opt/kui/warp.json"
WARP_STATE_PATH = "/opt/kui/egress-state.json"
TRAFFIC_STATE_PATH = "/opt/kui/traffic-state.json"
WGCF_VERSION = "2.2.31"
WGCF_ASSETS = {
    "x86_64": ("amd64", "69147e1a517c66129edd8ac8cb60484d6c9515178d7b4a2f95e3c925f225572a"),
    "aarch64": ("arm64", "b9bdbdeaa3f9f4ba741ba55b8bd94c24f7166c27668eb7e8192ccf9746961182"),
}
CLOUDFLARED_VERSION = "2026.7.1"
CLOUDFLARED_ASSETS = {
    "x86_64": ("amd64", "79a0ade7fc854f62c1aaef48424d9d979e8c2fcd039189d24db82b84cd146be1"),
    "aarch64": ("arm64", "18f2c9bfc7a67a971bd96f1a5a1935def3c1e52aa386626f1566f04e9b5478d6"),
}

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
REALTIME_URL = env.get("realtime_url", "") if isinstance(env, dict) else ""

def _require_https_url(value, name):
    parsed = urllib.parse.urlsplit(value or "")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError(f"{name} must be HTTPS without credentials or fragment")
    return value.rstrip("/")

API_URL = _require_https_url(API_URL, "api_url")
REPORT_URL = _require_https_url(REPORT_URL, "report_url")
BASE_URL = API_URL.rsplit('/api/', 1)[0] if '/api/' in API_URL else API_URL
if urllib.parse.urlsplit(REPORT_URL).netloc != urllib.parse.urlsplit(BASE_URL).netloc: raise RuntimeError("report_url must use the Pages API origin")
PROXY_API = _require_https_url(PROXY_API, "proxy_api")
if REALTIME_URL: REALTIME_URL = _require_https_url(REALTIME_URL, "realtime_url")

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
proxy_port_conflict = None

def persist_agent_token(token):
    global TOKEN, HEADERS
    if not token or token == TOKEN:
        return
    updated = dict(env)
    updated["token"] = token
    temp_config = CONF_FILE + ".tmp"
    with open(temp_config, "w", encoding="utf-8") as config_file:
        json.dump(updated, config_file)
        config_file.flush()
        os.fsync(config_file.fileno())
    os.chmod(temp_config, 0o600)
    os.replace(temp_config, CONF_FILE)
    TOKEN = token
    HEADERS["Authorization"] = token
    print("[agent] migrated to the server-specific agent token", flush=True)

def _write_json_state(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
            json.dump(value, state_file, separators=(",", ":")); state_file.flush(); os.fsync(state_file.fileno())
        os.chmod(temp_path, 0o600); os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

def _load_traffic_state():
    try:
        with open(TRAFFIC_STATE_PATH, "r", encoding="utf-8") as state_file: state = json.load(state_file)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}

def _ensure_wgcf():
    machine = platform.machine().lower()
    asset = WGCF_ASSETS.get(machine)
    if not asset:
        raise RuntimeError(f"WARP registration is unsupported on {machine}")
    arch, expected = asset
    target = "/opt/kui/wgcf"
    if os.path.exists(target):
        with open(target, "rb") as binary:
            if hashlib.sha256(binary.read()).hexdigest() == expected: return target
    url = f"https://github.com/ViRb3/wgcf/releases/download/v{WGCF_VERSION}/wgcf_{WGCF_VERSION}_linux_{arch}"
    temp_path = target + ".tmp"
    request = urllib.request.Request(url, headers={"User-Agent": "KUI-WARP/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        source = response.read(20 * 1024 * 1024)
    if hashlib.sha256(source).hexdigest() != expected:
        raise RuntimeError("wgcf checksum mismatch")
    with open(temp_path, "wb") as binary: binary.write(source)
    os.chmod(temp_path, 0o700)
    os.replace(temp_path, target)
    return target

def _load_or_create_warp_profile():
    if os.path.exists(WARP_CONF_PATH):
        try:
            with open(WARP_CONF_PATH, "r", encoding="utf-8") as profile_file:
                profile = json.load(profile_file)
            required = {"private_key", "ipv4_address", "ipv6_address", "peer_address", "peer_port", "peer_public_key"}
            if required.issubset(profile):
                ipv4 = ipaddress.ip_interface(profile["ipv4_address"]); ipv6 = ipaddress.ip_interface(profile["ipv6_address"]); ipaddress.ip_address(profile["peer_address"])
                if ipv4.version != 4 or ipv6.version != 6: raise ValueError("invalid WARP address families")
                peer_port = int(profile["peer_port"]); mtu = int(profile.get("mtu", 1280))
                if not 1 <= peer_port <= 65535 or not 1280 <= mtu <= 1420: raise ValueError("invalid WARP port or MTU")
                if len(base64.b64decode(profile["private_key"], validate=True)) != 32 or len(base64.b64decode(profile["peer_public_key"], validate=True)) != 32: raise ValueError("invalid WARP key")
                os.chmod(WARP_CONF_PATH, 0o600)
                return profile
        except Exception:
            pass
    wgcf = _ensure_wgcf()
    workdir = tempfile.mkdtemp(prefix="kui-warp-", dir="/opt/kui")
    try:
        registered = None
        for attempt in range(5):
            registered = subprocess.run([wgcf, "register", "--accept-tos"], cwd=workdir, capture_output=True, text=True, timeout=60)
            if registered.returncode == 0:
                break
            err_msg = (registered.stderr or registered.stdout).strip()
            if "429" in err_msg and attempt < 4:
                delay = 15 * (2 ** attempt)
                print(f"[agent] WARP registration rate-limited, retrying in {delay}s ({attempt+1}/5)", flush=True)
                time.sleep(delay)
                continue
            raise RuntimeError(f"WARP registration failed: {err_msg[-300:]}")
        if registered is None or registered.returncode != 0:
            raise RuntimeError("WARP registration failed after 5 attempts")
        generated = subprocess.run([wgcf, "generate"], cwd=workdir, capture_output=True, text=True, timeout=30)
        if generated.returncode != 0:
            raise RuntimeError(f"WARP profile generation failed: {(generated.stderr or generated.stdout).strip()[-300:]}")
        parser = configparser.ConfigParser(strict=False)
        parser.read(os.path.join(workdir, "wgcf-profile.conf"))
        addresses = [value.strip() for value in parser.get("Interface", "Address").split(",")]
        ipv4_address = next((value for value in addresses if ":" not in value), "")
        ipv6_address = next((value for value in addresses if ":" in value), "")
        endpoint = parser.get("Peer", "Endpoint")
        endpoint_host, endpoint_port = endpoint.rsplit(":", 1)
        endpoint_ips = socket.getaddrinfo(endpoint_host.strip("[]"), int(endpoint_port), socket.AF_UNSPEC, socket.SOCK_DGRAM)
        if not endpoint_ips:
            raise RuntimeError("WARP endpoint DNS resolution failed")
        profile = {
            "private_key": parser.get("Interface", "PrivateKey"),
            "ipv4_address": ipv4_address,
            "ipv6_address": ipv6_address,
            "peer_address": endpoint_ips[0][4][0],
            "peer_port": int(endpoint_port),
            "peer_public_key": parser.get("Peer", "PublicKey"),
            "mtu": int(parser.get("Interface", "MTU", fallback="1280")),
        }
        if not ipv4_address or not ipv6_address:
            raise RuntimeError("WARP registration did not return dual-stack addresses")
        descriptor, temp_profile = tempfile.mkstemp(prefix="warp.", suffix=".tmp", dir="/opt/kui")
        with os.fdopen(descriptor, "w", encoding="utf-8") as profile_file:
            json.dump(profile, profile_file)
            profile_file.flush()
            os.fsync(profile_file.fileno())
        os.chmod(temp_profile, 0o600)
        os.replace(temp_profile, WARP_CONF_PATH)
        return profile
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

def _load_warp_state():
    try:
        with open(WARP_STATE_PATH, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        mode = state.get("applied_mode", "native")
        if mode in {"off", "ipv4", "ipv6", "dual"}: mode = "native" if mode == "off" else f"warp_{mode}"
        return {"applied_mode": mode, "applied_revision": int(state.get("applied_revision", 0)), "pending_result": state.get("pending_result")}
    except Exception:
        return {"applied_mode": "native", "applied_revision": 0, "pending_result": None}

def _save_warp_state(mode, revision, pending_result=None):
    descriptor, temp_path = tempfile.mkstemp(prefix="warp-state.", suffix=".tmp", dir="/opt/kui")
    with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
        json.dump({"applied_mode": mode, "applied_revision": int(revision), "pending_result": pending_result}, state_file)
        state_file.flush(); os.fsync(state_file.fileno())
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, WARP_STATE_PATH)

def _singbox_service_healthy():
    if os.path.exists("/etc/alpine-release"):
        return subprocess.run(["rc-service", "sing-box", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15).returncode == 0
    return subprocess.run(["systemctl", "is-active", "--quiet", "sing-box"], timeout=15).returncode == 0

_warp_exit_ip = ""

def _verify_warp_exit(mode):
    global _warp_exit_ip
    if mode == "off": return True
    checks = []
    if mode in {"ipv4", "dual"}:
        checks.append(("IPv4", "https://1.1.1.1/cdn-cgi/trace", ["-4", "-k"]))
    if mode in {"ipv6", "dual"}:
        # The local check inbound only listens on IPv4. Do not pass curl -6:
        # it would try to reach 127.0.0.1 through IPv6 before SOCKS can route
        # the literal IPv6 destination through WARP.
        checks.append(("IPv6", "https://[2606:4700:4700::1111]/cdn-cgi/trace", ["-k"]))
    for family, url, extra_args in checks:
        verified = False
        for _ in range(4):
            result = subprocess.run(["curl", "-fsSL", "--connect-timeout", "5", "--max-time", "20", "--proxy", "socks5://127.0.0.1:39482", *extra_args, url], capture_output=True, text=True)
            if result.returncode == 0 and "warp=on" in result.stdout.lower():
                trace = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
                ip = trace.get("ip", "")
                if ip: _warp_exit_ip = ip
                verified = True; break
            time.sleep(2)
        if not verified: raise RuntimeError(f"WARP {family} data-plane verification failed")
    return True

_residential_exit_ip = ""

def _verify_residential_exit(proxy):
    global _residential_exit_ip
    host = str(proxy.get("addr") or "127.0.0.1")
    try:
        port = int(proxy.get("port") or PROXY_PORT)
    except (TypeError, ValueError):
        port = PROXY_PORT
    if not 1 <= port <= 65535:
        raise RuntimeError("invalid residential proxy port")
    user = str(proxy.get("user") or "")
    password = str(proxy.get("pass") or "")
    auth = f"{urllib.parse.quote(user, safe='')}:{urllib.parse.quote(password, safe='')}@" if user or password else ""
    proxy_url = f"socks5h://{auth}{host}:{port}"
    for _ in range(4):
        result = subprocess.run(["curl", "-4", "-fsSL", "--connect-timeout", "5", "--max-time", "15", "--proxy", proxy_url, "https://api.ipify.org"], capture_output=True, text=True)
        ip = result.stdout.strip()
        if result.returncode == 0 and re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip) and ip != VPS_IP:
            _residential_exit_ip = ip
            return True
        time.sleep(2)
    raise RuntimeError("residential proxy data-plane verification failed")

def _post_warp_result(payload):
    parsed = urllib.parse.urlsplit(API_URL)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    request = urllib.request.Request(f"{origin}/api/egress_result", data=json.dumps({"ip": VPS_IP, **payload}).encode(), headers={**HEADERS, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())

def check_for_update():
    global last_update_check
    if os.environ.get("KUI_DISABLE_AUTO_UPDATE") == "1":
        return False
    now = time.time()
    if now - last_update_check < 3600:
        return False
    last_update_check = now
    targets = (("realtime-client", os.path.join(os.path.dirname(os.path.abspath(__file__)), "realtime_client.py")), ("agent", os.path.abspath(__file__)))
    temporary_files = []
    changed = []
    try:
        for component, target in targets:
            temp_path = target + ".update.py"
            temporary_files.append(temp_path)
            update_url = f"{BASE_URL}/api/agent_update?ip={urllib.parse.quote(VPS_IP, safe='')}&component={component}"
            request = urllib.request.Request(update_url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=20) as response:
                source = response.read(2 * 1024 * 1024 + 1)
                expected_hash = response.headers.get("X-Agent-SHA256", "").lower()
                version = response.headers.get("X-Agent-Manifest-Version", "")
                length = response.headers.get("X-Agent-Length", "")
                supplied_mac = response.headers.get("X-Agent-MAC", "").lower()
            manifest = f"v1\n{component}\n{expected_hash}\n{len(source)}\n".encode()
            expected_mac = hmac.new(TOKEN.encode(), manifest, hashlib.sha256).hexdigest()
            if not source or len(source) > 2 * 1024 * 1024 or version != "1" or length != str(len(source)) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or not hmac.compare_digest(supplied_mac, expected_mac) or hashlib.sha256(source).hexdigest() != expected_hash:
                raise ValueError(f"{component} update checksum mismatch")
            current_hash = hashlib.sha256(open(target, "rb").read()).hexdigest() if os.path.exists(target) else ""
            if current_hash == expected_hash:
                continue
            with open(temp_path, "wb") as update_file: update_file.write(source)
            os.chmod(temp_path, 0o700)
            checked = subprocess.run([sys.executable, "-m", "py_compile", temp_path], capture_output=True, text=True, timeout=30)
            if checked.returncode != 0: raise ValueError(f"{component} update compile failed: {checked.stderr.strip()}")
            changed.append((temp_path, target))
        if not changed: return False
        replaced = []
        try:
            for temp_path, target in changed:
                backup = target + ".last-good"
                if os.path.exists(target): shutil.copy2(target, backup)
                os.replace(temp_path, target); replaced.append((target, backup))
        except Exception:
            for target, backup in reversed(replaced):
                if os.path.exists(backup): shutil.copy2(backup, target)
            raise
        _write_json_state("/opt/kui/.update-pending", {"updated_at": int(time.time()), "deadline_at": int(time.time()) + 120, "files": [target for _, target in changed]})
        print("[agent] components updated, restarting", flush=True)
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])
    except Exception as error:
        print(f"[agent] update check failed: {error}", flush=True)
        try:
            for temp_path in temporary_files:
                if os.path.exists(temp_path): os.remove(temp_path)
        except Exception:
            pass
    return False

# Dashboard viewers receive five-second updates. While nobody is connected,
# Durable Objects switch routine metric snapshots to a lower rate.
REALTIME_STATUS_ACTIVE_INTERVAL = 5
REALTIME_STATUS_IDLE_INTERVAL = 30
realtime_status_interval = REALTIME_STATUS_ACTIVE_INTERVAL
global_interval = REALTIME_STATUS_ACTIVE_INTERVAL
fast_mode = False
config_wakeup = threading.Event()
heartbeat_wakeup = threading.Event()
realtime_channel = None
last_http_report = 0
# Keep D1's fallback snapshot fresh for dashboard reloads and reconnects.
# WebSocket remains the primary five-second live channel.
REALTIME_HTTP_INTERVAL = 30

# 🌟 增加全局 Ping 状态缓存锁，防止在非测速轮次上传 '0' 导致前端图表归零
last_pings = {"ct": "0", "cu": "0", "cm": "0", "bd": "0"}
dynamic_ping = {"ct": None, "cu": None, "cm": None}
pending_report_id = None
pending_report_bytes = None
pending_node_traffic = None
pending_report_payload = None
_traffic_state = _load_traffic_state()
last_reported_bytes = {str(k): int(v) for k, v in (_traffic_state.get("last_reported_bytes") or {}).items()}
_pending = _traffic_state.get("pending") or {}
pending_report_id = _pending.get("report_id")
pending_report_bytes = _pending.get("report_bytes")
pending_node_traffic = _pending.get("node_traffic")
pending_report_payload = _pending.get("payload")
egress_retry_timer = None
egress_retry_lock = threading.Lock()

def _schedule_egress_retry(delay):
    global egress_retry_timer
    with egress_retry_lock:
        if egress_retry_timer: egress_retry_timer.cancel()
        egress_retry_timer = threading.Timer(max(1, delay), config_wakeup.set)
        egress_retry_timer.daemon = True
        egress_retry_timer.start()

# --- 缓存静态信息 ---
cached_os = cached_arch = cached_cpu_info = cached_virt = None

def run_text(command, timeout=5):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""

def get_static_sysinfo():
    global cached_os, cached_arch, cached_cpu_info, cached_virt
    if not cached_os:
        try:
            with open('/etc/os-release') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        cached_os = line.split('=')[1].strip().strip('"')
                        break
        except: cached_os = run_text('uname -srm') or "Unknown OS"
    if not cached_arch: cached_arch = run_text('uname -m') or platform.machine() or "unknown"
    if not cached_cpu_info:
        try:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if 'model name' in line:
                        cached_cpu_info = line.split(':')[1].strip()
                        break
        except: cached_cpu_info = "Unknown CPU"
    if not cached_virt:
        virt = run_text('systemd-detect-virt 2>/dev/null')
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

def ensure_firewall_open(port, transport=None):
    # 验证端口参数
    try:
        port_int = int(port)
        if not (1 <= port_int <= 65535):
            raise ValueError(f"端口 {port} 超出有效范围 (1-65535)")
    except (ValueError, TypeError):
        raise ValueError(f"无效的端口参数: {port}")
    
    port = str(port_int)
    for protocol in ([transport] if transport in {"tcp", "udp"} else ["tcp", "udp"]):
        cmds = [
            f"iptables -C INPUT -p {protocol} --dport {port} -j ACCEPT 2>/dev/null || iptables -I INPUT -p {protocol} --dport {port} -j ACCEPT",
            f"iptables -C OUTPUT -p {protocol} --sport {port} -j ACCEPT 2>/dev/null || iptables -I OUTPUT -p {protocol} --sport {port} -j ACCEPT",
            f"ip6tables -C INPUT -p {protocol} --dport {port} -j ACCEPT 2>/dev/null || ip6tables -I INPUT -p {protocol} --dport {port} -j ACCEPT",
            f"ip6tables -C OUTPUT -p {protocol} --sport {port} -j ACCEPT 2>/dev/null || ip6tables -I OUTPUT -p {protocol} --sport {port} -j ACCEPT"
        ]
        for cmd in cmds:
            try: subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5)
            except Exception: pass
        try:
            has_ufw = subprocess.run("command -v ufw", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3).returncode == 0
            if has_ufw: subprocess.run(f"ufw allow {port}/{protocol} >/dev/null 2>&1", shell=True, timeout=5)
        except Exception: pass

def _read_iptables_port_bytes(port, protocol):
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
            if "ACCEPT" not in line or not key_pattern.search(line) or protocol not in line.lower().split():
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

def get_port_traffic(port, protocol="tcp", node_id=None):
    node_tag = f"in-{node_id}" if node_id else None

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

    # Firewall counters include unauthenticated probes and are not reliable
    # per-user billing data. Fail closed until sing-box stats are available.
    return None

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
        df_output = subprocess.run(["df", "-m", "/"], capture_output=True, text=True, timeout=3, check=True).stdout
        df = df_output.split('\n')[1].split()
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
        
        stats["boot_time"] = run_text("uptime -s 2>/dev/null || stat -c %y / 2>/dev/null | cut -d'.' -f1", timeout=3)
        process_count = run_text("ps -e | wc -l", timeout=3)
        stats["processes"] = str(max(0, int(process_count or '1') - 1))
        stats["tcp_conn"] = run_text("ss -ant 2>/dev/null | grep -v 'State' | wc -l", timeout=3) or "0"
        stats["udp_conn"] = run_text("ss -anu 2>/dev/null | grep -v 'State' | wc -l", timeout=3) or "0"
    except: pass

    rx_now, tx_now = get_net_dev_bytes()
    stats["net_rx"] = str(rx_now); stats["net_tx"] = str(tx_now)
    # Measure elapsed wall time instead of the requested heartbeat interval.
    # The latter changes with dashboard activity and was leaving stale zero
    # speeds after reconfiguration or a failed HTTP fallback report.
    now = time.monotonic()
    previous_sample_at = getattr(get_system_status, "previous_sample_at", 0.0)
    elapsed = now - previous_sample_at if previous_sample_at else 0.0
    if elapsed > 0:
        stats["net_in_speed"] = max(0, rx_now - prev_rx) / elapsed
        stats["net_out_speed"] = max(0, tx_now - prev_tx) / elapsed
    get_system_status.previous_sample_at = now
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
    asset = CLOUDFLARED_ASSETS.get(platform.machine().lower())
    if not asset:
        return False
    arch, expected = asset
    if os.path.isfile(target):
        with open(target, "rb") as binary:
            if hashlib.sha256(binary.read()).hexdigest() == expected: return True
    fd, tmp_path = tempfile.mkstemp(prefix="cloudflared-", dir="/usr/local/bin")
    os.close(fd)
    try:
        result = subprocess.run(["curl", "-fL", "--retry", "3", "--max-filesize", "60000000", "-o", tmp_path, f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/cloudflared-linux-{arch}"], timeout=120)
        if result.returncode != 0 or os.path.getsize(tmp_path) == 0:
            return False
        with open(tmp_path, "rb") as binary:
            if hashlib.sha256(binary.read()).hexdigest() != expected: return False
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

def build_singbox_config(nodes, proxy_cfg=None, peers=None, mesh=None, socks5_outbound=None, warp_mode="off"):
    global proxy_port_conflict
    singbox_config = {
        "log": {"level": "warn"},
        "inbounds": [],
        "outbounds": [{"type": "direct", "tag": "direct-out"}],
        "route": {"rules": []}
    }
    active_certs = []
    valid_nodes = []
    listener_keys = set()
    if warp_mode not in {"off", "ipv4", "ipv6", "dual"}:
        raise ValueError("invalid WARP mode")

    for node in nodes:
        try:
            node_id = str(node["id"])
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", node_id): raise ValueError("invalid node id")
            in_tag, proto, port = f"in-{node_id}", node["protocol"], int(node["port"])
            if not 1 <= port <= 65535: raise ValueError("invalid port")
            transport = "udp" if proto in {"Hysteria2", "TUIC"} else "tcp"
            listener_key = (transport, port)
            if listener_key in listener_keys: raise ValueError(f"duplicate {transport} listener port {port}")
            listener_keys.add(listener_key)
            supported = {"VLESS", "XTLS-Reality", "Reality", "Hysteria2", "TUIC", "Trojan", "H2-Reality", "gRPC-Reality", "AnyTLS", "Naive", "Socks5", "VLESS-Argo", "dokodemo-door"}
            if proto not in supported:
                raise ValueError(f"unsupported protocol {proto}")
            if proto != "dokodemo-door" and not isinstance(node.get("uuid"), str):
                raise ValueError("uuid is required")
            if proto in {"XTLS-Reality", "Reality", "H2-Reality", "gRPC-Reality"} and (not node.get("private_key") or not node.get("short_id")):
                raise ValueError("Reality private_key and short_id are required")
            if proto in {"TUIC", "Trojan", "AnyTLS", "Naive", "Socks5"} and not node.get("private_key"):
                raise ValueError(f"{proto} password is required")
            if proto == "dokodemo-door" and node.get("relay_type") != "internal" and (not node.get("target_ip") or not node.get("target_port")):
                raise ValueError("dokodemo target_ip and target_port are required")
        except (KeyError, TypeError, ValueError) as error:
            print(f"[agent] skipping invalid node {node.get('id', '<unknown>')}: {error}", flush=True)
            continue
        sni = node.get("sni") or "addons.mozilla.org"
        clean_uuid = node.get('uuid', '').replace('-', '')
        
        if proto in ["Hysteria2", "TUIC", "Trojan", "VLESS-WS-TLS", "AnyTLS", "Naive"]:
            cert_path, key_path = f"/opt/kui/cert_{node['id']}.pem", f"/opt/kui/key_{node['id']}.pem"
            active_certs.extend([f"cert_{node['id']}.pem", f"key_{node['id']}.pem"])
            if not os.path.exists(cert_path):
                parts = sni.split('.'); cn = f"{parts[-2]}.{parts[-1]}" if len(parts) >= 2 else sni
                conf_path = f"/opt/kui/cert_{node['id']}.conf"
                with open(conf_path, "w") as f: f.write(f"[req]\ndistinguished_name = req_distinguished_name\nx509_extensions = v3_req\nprompt = no\n[req_distinguished_name]\nCN = {cn}\n[v3_req]\nsubjectAltName = @alt_names\n[alt_names]\nDNS = {sni}\n")
                subprocess.run(["openssl", "ecparam", "-genkey", "-name", "prime256v1", "-out", key_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["openssl", "req", "-new", "-x509", "-days", "36500", "-key", key_path, "-out", cert_path, "-config", conf_path, "-extensions", "v3_req"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                os.chmod(cert_path, 0o644)
                os.chmod(key_path, 0o600)
                try: os.remove(conf_path)
                except: pass
        
        if proto == "VLESS": singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"]}]})
        elif proto in ["XTLS-Reality", "Reality"]: singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"], "flow": "xtls-rprx-vision"}], "tls": {"enabled": True, "server_name": sni, "reality": {"enabled": True, "handshake": {"server": sni, "server_port": 443}, "private_key": node["private_key"], "short_id": [node["short_id"]]}}})
        elif proto == "Hysteria2": singbox_config["inbounds"].append({"type": "hysteria2", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"password": node["uuid"]}], "tls": {"enabled": True, "alpn": ["h3"], "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "TUIC": singbox_config["inbounds"].append({"type": "tuic", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"], "password": node["private_key"]}], "tls": {"enabled": True, "alpn": ["h3"], "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "Trojan": singbox_config["inbounds"].append({"type": "trojan", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"password": node["private_key"]}], "tls": {"enabled": True, "server_name": sni, "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "H2-Reality": singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"]}], "tls": {"enabled": True, "server_name": sni, "alpn": ["h2", "http/1.1"], "reality": {"enabled": True, "handshake": {"server": sni, "server_port": 443}, "private_key": node["private_key"], "short_id": [node["short_id"]]}}, "transport": {"type": "http", "host": [sni], "path": "/"}})
        elif proto == "gRPC-Reality": singbox_config["inbounds"].append({"type": "vless", "tag": in_tag, "listen": "::", "listen_port": port, "users": [{"uuid": node["uuid"]}], "tls": {"enabled": True, "server_name": sni, "alpn": ["h2"], "reality": {"enabled": True, "handshake": {"server": sni, "server_port": 443}, "private_key": node["private_key"], "short_id": [node["short_id"]]}}, "transport": {"type": "grpc", "service_name": "grpc"}})
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
        valid_nodes.append(node)

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
            # proxy-lite owns the residential listener. During simultaneous
            # service restarts its socket may not be open yet; detecting only
            # an already-bound port lets sing-box steal the port in that gap.
            proxy_lite_installed = os.path.exists("/etc/proxy-lite/env") and os.path.exists("/opt/proxy_lite/proxy_server.py")
            if not proxy_lite_installed:
                if proxy_port_conflict is not False:
                    print(f"[agent] 端口 {proxy_port} 可用，由 sing-box 提供 SOCKS5 入站", flush=True)
                proxy_port_conflict = False
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
                if proxy_port_conflict is not True:
                    print(f"[agent] 端口 {proxy_port} 预留给 proxy-lite，跳过 sing-box SOCKS5 入站", flush=True)
                proxy_port_conflict = True

    # --- 住宅IP跨VPS互联（mesh）：把本机节点出口链式转发到其它 VPS 的 SOCKS5，实现出口IP共享/轮换 ---
    mesh_enabled = bool(peers and mesh and mesh.get("enabled"))
    if mesh_enabled and socks5_outbound and socks5_outbound.get("enabled"):
        print("[agent] server SOCKS5 outbound takes priority; mesh routing skipped", flush=True)
        mesh_enabled = False
    if mesh_enabled:
        try:
            chain_mode = mesh.get("mode", "all")
            chain_nodes = set(str(x) for x in (mesh.get("nodes") or []))
            rr = [0]
            for node in valid_nodes:
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
                singbox_config["inbounds"].append({"type": "socks", "tag": "egress-check-in", "listen": "127.0.0.1", "listen_port": 39482})
                singbox_config["route"]["rules"].append({"inbound": ["egress-check-in"], "outbound": s5_tag})
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
                        proxy_inbounds = {f"in-{node['id']}" for node in valid_nodes if node.get("protocol") != "dokodemo-door"}
                        # Domain rules only work after sing-box extracts the TLS/HTTP
                        # destination from inbound traffic. sing-box 1.13 requires
                        # this as a non-final route action, not legacy inbound fields.
                        singbox_config["route"]["rules"].insert(0, {"inbound": sorted(proxy_inbounds), "action": "sniff", "timeout": "1s"})
                        route_rule = {"domain_keyword": all_keywords, "domain_suffix": all_suffixes, "outbound": s5_tag}
                        singbox_config["route"]["rules"].append(route_rule)
                        # Residential exits are IPv4-only. Prevent unmatched IPv6
                        # requests from falling through to a previous/native path
                        # after switching from WARP dual-stack to selective mode.
                        singbox_config["route"]["rules"].append({"inbound": sorted(proxy_inbounds), "ip_version": 6, "action": "reject"})
                else:
                    # 全局出站：所有非转发节点流量走 SOCKS5
                    existing_routed = set()
                    for rule in singbox_config["route"]["rules"]:
                        for ib in rule.get("inbound", []):
                            existing_routed.add(ib)
                    for node in valid_nodes:
                        if node.get("protocol") == "dokodemo-door":
                            continue
                        in_tag = f"in-{node['id']}"
                        if in_tag not in existing_routed:
                            singbox_config["route"]["rules"].append({"inbound": [in_tag], "outbound": s5_tag})
        except Exception:
            pass

    if warp_mode != "off":
        if mesh_enabled:
            raise RuntimeError("WARP cannot be combined with residential mesh routing")
        if socks5_outbound and socks5_outbound.get("enabled"):
            raise RuntimeError("SOCKS5 outbound and WARP outbound cannot be enabled together")
        profile = _load_or_create_warp_profile()
        addresses = []
        allowed_ips = []
        if warp_mode in {"ipv4", "dual"}:
            addresses.append(profile["ipv4_address"])
            allowed_ips.append("0.0.0.0/0")
        if warp_mode in {"ipv6", "dual"}:
            addresses.append(profile["ipv6_address"])
            allowed_ips.append("::/0")
        singbox_config["endpoints"] = [{
            "type": "wireguard", "tag": "warp-out", "system": False,
            "mtu": min(max(int(profile.get("mtu", 1280)), 1280), 1420),
            "address": addresses, "private_key": profile["private_key"],
            "peers": [{
                "address": profile["peer_address"], "port": int(profile["peer_port"]),
                "public_key": profile["peer_public_key"], "allowed_ips": allowed_ips,
                "persistent_keepalive_interval": 25,
            }],
        }]
        strategy = "prefer_ipv4" if warp_mode != "ipv6" else "prefer_ipv6"
        dns_server = "2606:4700:4700::1111" if warp_mode == "ipv6" else "1.1.1.1"
        singbox_config["dns"] = {
            "servers": [{"type": "udp", "tag": "warp-dns", "server": dns_server, "server_port": 53, "detour": "warp-out"}],
            "final": "warp-dns", "strategy": strategy,
        }
        warp_inbounds = [f"in-{node['id']}" for node in valid_nodes if node.get("protocol") != "dokodemo-door"]
        if warp_inbounds:
            singbox_config["route"]["rules"].append({"inbound": warp_inbounds, "action": "route", "outbound": "warp-out"})
            if warp_mode == "ipv4": singbox_config["route"]["rules"].append({"inbound": warp_inbounds, "ip_version": 6, "action": "reject"})
            elif warp_mode == "ipv6": singbox_config["route"]["rules"].append({"inbound": warp_inbounds, "ip_version": 4, "action": "reject"})
        singbox_config["inbounds"].append({"type": "socks", "tag": "egress-check-in", "listen": "127.0.0.1", "listen_port": 39482})
        check_rule = {"inbound": ["egress-check-in"], "action": "route", "outbound": "warp-out"}
        singbox_config["route"]["rules"].append(check_rule)

    for node in valid_nodes:
        ensure_firewall_open(node["port"], "udp" if node.get("protocol") in {"Hysteria2", "TUIC"} else "tcp")
    os.makedirs(os.path.dirname(SINGBOX_CONF_PATH), exist_ok=True)
    new_config_str = json.dumps(singbox_config, indent=2)
    old_config_str = ""
    if os.path.exists(SINGBOX_CONF_PATH):
        with open(SINGBOX_CONF_PATH, "r") as f: old_config_str = f.read()
        os.chmod(SINGBOX_CONF_PATH, 0o600)

    if new_config_str != old_config_str:
        temp_config = SINGBOX_CONF_PATH + ".tmp"
        with open(temp_config, "w") as f: f.write(new_config_str)
        os.chmod(temp_config, 0o600)
        sing_box = shutil.which("sing-box")
        if not sing_box:
            os.remove(temp_config)
            raise RuntimeError("sing-box binary not found")
        checked = subprocess.run([sing_box, "check", "-c", temp_config], capture_output=True, text=True, timeout=30)
        if checked.returncode != 0:
            os.remove(temp_config)
            raise RuntimeError(f"sing-box config rejected: {checked.stderr.strip()[-500:]}")
        backup_config = SINGBOX_CONF_PATH + ".last-good"
        if old_config_str:
            with open(backup_config + ".tmp", "w") as backup: backup.write(old_config_str)
            os.chmod(backup_config + ".tmp", 0o600)
            os.replace(backup_config + ".tmp", backup_config)
        os.replace(temp_config, SINGBOX_CONF_PATH)
        if os.path.exists("/sbin/openrc-run") or os.path.exists("/etc/alpine-release"):
            restarted = subprocess.run(["rc-service", "sing-box", "restart"], capture_output=True, text=True, timeout=30)
            healthy = restarted.returncode == 0 and subprocess.run(["rc-service", "sing-box", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15).returncode == 0
        else:
            restarted = subprocess.run(["systemctl", "restart", "sing-box"], capture_output=True, text=True, timeout=30)
            healthy = restarted.returncode == 0 and subprocess.run(["systemctl", "is-active", "--quiet", "sing-box"], timeout=15).returncode == 0
        if not healthy:
            rollback_healthy = False
            if old_config_str:
                with open(SINGBOX_CONF_PATH + ".rollback", "w") as rollback: rollback.write(old_config_str)
                os.chmod(SINGBOX_CONF_PATH + ".rollback", 0o600)
                os.replace(SINGBOX_CONF_PATH + ".rollback", SINGBOX_CONF_PATH)
                if os.path.exists("/etc/alpine-release"): subprocess.run(["rc-service", "sing-box", "restart"], timeout=30)
                else: subprocess.run(["systemctl", "restart", "sing-box"], timeout=30)
                rollback_healthy = _singbox_service_healthy()
            raise RuntimeError(f"sing-box restart failed; rollback_healthy={str(rollback_healthy).lower()}")
    elif os.path.exists("/sbin/openrc-run") or os.path.exists("/etc/alpine-release"):
        subprocess.run(["rc-service", "sing-box", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if not _singbox_service_healthy(): raise RuntimeError("sing-box is not healthy after start")
    else:
        subprocess.run(["systemctl", "start", "sing-box"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if not _singbox_service_healthy(): raise RuntimeError("sing-box is not healthy after start")
    if socks5_outbound and socks5_outbound.get("source") == "residential": _verify_residential_exit(socks5_outbound)
    if warp_mode != "off": _verify_warp_exit(warp_mode)
    for filename in os.listdir("/opt/kui/"):
        if (filename.startswith("cert_") or filename.startswith("key_")) and filename.endswith(".pem") and filename not in active_certs:
            try: os.remove(os.path.join("/opt/kui/", filename))
            except OSError: pass

def report_status(current_nodes, argo_urls, force_http=False, allow_http=True):
    global last_reported_bytes, global_interval, fast_mode, dynamic_ping, pending_report_id, pending_report_bytes, pending_node_traffic, pending_report_payload, last_http_report
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
        current_bytes = get_port_traffic(port, proto, nid)
        if current_bytes is None:
            continue
        baseline = pending_bytes.get(nid, current_bytes)
        delta = current_bytes - baseline if current_bytes >= baseline else current_bytes
        if delta > 0: deltas.append({ "id": nid, "delta_bytes": delta })
        pending_bytes[nid] = current_bytes

    if not pending_report_id:
        pending_report_id = f"{VPS_IP}:{time.time_ns()}"
    # Keep accumulating against the last successful HTTP baseline. WebSocket
    # updates are display-only and must not advance billable traffic counters.
    if pending_report_payload is None:
        pending_report_bytes = {k: v for k, v in pending_bytes.items() if k in current_ids}
        pending_node_traffic = deltas
    status["node_traffic"] = pending_node_traffic
    status["report_id"] = pending_report_id
    _write_json_state(TRAFFIC_STATE_PATH, {"last_reported_bytes": last_reported_bytes, "pending": {"report_id": pending_report_id, "report_bytes": pending_report_bytes, "node_traffic": pending_node_traffic, "payload": pending_report_payload}})

    websocket_sent = realtime_channel.send(status) if realtime_channel and realtime_channel.connected else False
    if websocket_sent and not force_http and time.time() - last_http_report < REALTIME_HTTP_INTERVAL:
        return True
    if realtime_channel and realtime_channel.enabled and not websocket_sent and time.time() - realtime_channel.last_disconnected < 30:
        return False
    if not websocket_sent and not allow_http:
        return False

    try: 
        if pending_report_payload is None:
            pending_report_payload = dict(status)
            pending_report_payload["node_traffic"] = list(pending_node_traffic or [])
            _write_json_state(TRAFFIC_STATE_PATH, {"last_reported_bytes": last_reported_bytes, "pending": {"report_id": pending_report_id, "report_bytes": pending_report_bytes, "node_traffic": pending_node_traffic, "payload": pending_report_payload}})
        req = urllib.request.Request(REPORT_URL, data=json.dumps(pending_report_payload).encode(), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as response:
            resp_data = json.loads(response.read().decode('utf-8'))
        last_reported_bytes = pending_report_bytes
        pending_report_id = None
        pending_report_bytes = None
        pending_node_traffic = None
        pending_report_payload = None
        last_http_report = time.time()
        _write_json_state(TRAFFIC_STATE_PATH, {"last_reported_bytes": last_reported_bytes, "pending": None})
        if resp_data and "interval" in resp_data:
            global_interval = min(max(1, int(resp_data["interval"])), 3600)
        new_fast_mode = bool(resp_data.get("fast_mode"))
        if new_fast_mode and not fast_mode:
            config_wakeup.set()
        fast_mode = new_fast_mode
        for key in ("ct", "cu", "cm"):
            value = resp_data.get(f"ping_{key}")
            dynamic_ping[key] = None if not value or value == "default" else value
        return True
    except Exception as error:
        print(f"[agent] status report failed: {error}", flush=True)
        return False

def fetch_proxy_config():
    try:
        req = urllib.request.Request(f"{PROXY_API}/api/proxy/config?ip={VPS_IP}", headers=_proxy_ctrl_headers())
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as error:
        print(f"[agent] proxy config fetch failed: {error}", flush=True)
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
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode('utf-8')
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
    except Exception as error:
        print(f"[agent] proxy mesh fetch failed: {error}", flush=True)
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
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read(1)
    except Exception as error:
        print(f"[agent] proxy status report failed: {error}", flush=True)

def fetch_and_apply_configs():
    global REALTIME_URL, realtime_channel
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API_URL}?ip={VPS_IP}", headers=HEADERS), timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        if data.get("success"):
            persist_agent_token(data.get("agent_token"))
            new_realtime_url = data.get("realtime_url") or ""
            if new_realtime_url: new_realtime_url = _require_https_url(new_realtime_url, "realtime_url")
            if new_realtime_url and new_realtime_url != REALTIME_URL:
                REALTIME_URL = new_realtime_url
                env["realtime_url"] = new_realtime_url
                try:
                    temp_config = CONF_FILE + ".tmp"
                    with open(temp_config, "w", encoding="utf-8") as config_file: json.dump(env, config_file)
                    os.chmod(temp_config, 0o600); os.replace(temp_config, CONF_FILE)
                except Exception: pass
                if realtime_channel: realtime_channel.stop()
                realtime_channel = create_realtime_channel()
                realtime_channel.start()
            nodes = data.get("configs", [])
            global current_proxy_config
            current_proxy_config = data.get("proxy") if isinstance(data.get("proxy"), dict) else {}
            mesh = _extract_mesh(current_proxy_config)
            peers = []
            if mesh.get("enabled"):
                peers = fetch_proxy_mesh(mesh.get("country", "ANY"))
                exit_ip = mesh.get("exit")
                if exit_ip and exit_ip != "ANY":
                    peers = [p for p in peers if p.get("country") == exit_ip or p.get("socks_ip") == exit_ip or p.get("ip") == exit_ip]
            egress = data.get("egress", {})
            desired_egress = egress.get("desired_mode", "native")
            revision = int(egress.get("revision", 0))
            local_warp = _load_warp_state()
            if local_warp.get("pending_result"):
                try:
                    ack = _post_warp_result(local_warp["pending_result"])
                    if (local_warp["pending_result"].get("success") is True and ack.get("accepted")) or revision != int(local_warp["pending_result"].get("revision", -1)):
                        _save_warp_state(local_warp["applied_mode"], local_warp["applied_revision"])
                except Exception:
                    pass
                retry_after = int(local_warp["pending_result"].get("retry_after", 0))
                if local_warp["pending_result"].get("success") is False and retry_after > time.time():
                    _schedule_egress_retry(retry_after - time.time())
            remote_applied_revision = int(egress.get("applied_revision", 0))
            applied_revision = max(remote_applied_revision, local_warp["applied_revision"])
            applied_egress = local_warp["applied_mode"] if local_warp["applied_revision"] > remote_applied_revision else egress.get("applied_mode", local_warp["applied_mode"])
            apply_egress_change = revision > applied_revision
            pending_failure = local_warp.get("pending_result") or {}
            if apply_egress_change and pending_failure.get("success") is False and int(pending_failure.get("revision", -1)) == revision:
                retry_after = int(pending_failure.get("retry_after", 0))
                if time.time() < retry_after: apply_egress_change = False
            runtime_egress = desired_egress if apply_egress_change else applied_egress
            residential = data.get("residential_outbound", {})
            proxy_mode = egress.get("proxy_mode", "global")
            proxy_categories = egress.get("proxy_categories", "")
            proxy_categories_list = [c.strip() for c in proxy_categories.split(",") if c.strip()] if proxy_categories else []
            proxy_domains = json.dumps({"categories": proxy_categories_list}) if proxy_mode == "selective" and proxy_categories_list else ""
            if runtime_egress == "residential":
                runtime_socks = {"enabled": True, "source": "residential", "addr": residential.get("addr", "127.0.0.1"), "port": residential.get("port", 7920), "user": residential.get("user", ""), "pass": residential.get("pass", ""), "mode": proxy_mode, "domains": proxy_domains}
            elif runtime_egress == "socks5":
                runtime_socks = {"enabled": True, "source": "manual", "addr": egress.get("socks5_addr", ""), "port": int(egress.get("socks5_port", 0)), "user": egress.get("socks5_user", ""), "pass": egress.get("socks5_pass", ""), "mode": proxy_mode, "domains": proxy_domains}
            else:
                runtime_socks = {}
            runtime_warp = runtime_egress[5:] if runtime_egress.startswith("warp_") else "off"
            config_hash = hashlib.sha256(json.dumps({"nodes": nodes, "egress": runtime_egress}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            try:
                if runtime_egress == "residential" and not residential.get("available"): raise RuntimeError("residential proxy is unavailable")
                build_singbox_config(nodes, current_proxy_config, peers, mesh, runtime_socks, runtime_warp)
                if apply_egress_change:
                    egress_ip = _warp_exit_ip if runtime_egress.startswith("warp_") else (_residential_exit_ip if runtime_egress == "residential" else "")
                    result = {"success": True, "component": "egress", "revision": revision, "desired_mode": desired_egress, "applied_mode": desired_egress, "rolled_back": False, "rollback_healthy": True, "applied_at": int(time.time() * 1000), "egress_ip": egress_ip}
                    _save_warp_state(desired_egress, revision, result)
                    try:
                        ack = _post_warp_result(result)
                        if ack.get("accepted"): _save_warp_state(desired_egress, revision)
                    except Exception: pass
                    if realtime_channel and realtime_channel.connected: realtime_channel.send(result, "config.result")
                elif realtime_channel and realtime_channel.connected:
                    realtime_channel.send({"success": True, "component": "config", "config_hash": config_hash, "old_config_active": False, "rollback_healthy": True, "applied_at": int(time.time() * 1000)}, "config.result")
            except Exception as error:
                if apply_egress_change:
                    # A WARP registration can become unusable after prolonged
                    # network loss. Drop the cached profile so the scheduled
                    # retry registers a fresh identity instead of failing on
                    # the same WireGuard handshake indefinitely.
                    if runtime_warp != "off" and "WARP " in str(error):
                        try: os.remove(WARP_CONF_PATH)
                        except FileNotFoundError: pass
                    rollback_healthy = False
                    try:
                        rb_proxy_mode = egress.get("proxy_mode", "global")
                        rb_proxy_categories = egress.get("proxy_categories", "")
                        rb_proxy_cats_list = [c.strip() for c in rb_proxy_categories.split(",") if c.strip()] if rb_proxy_categories else []
                        rb_proxy_domains = json.dumps({"categories": rb_proxy_cats_list}) if rb_proxy_mode == "selective" and rb_proxy_cats_list else ""
                        if applied_egress == "residential":
                            rollback_socks = {"enabled": True, "source": "residential", "addr": residential.get("addr", "127.0.0.1"), "port": residential.get("port", 7920), "user": residential.get("user", ""), "pass": residential.get("pass", ""), "mode": rb_proxy_mode, "domains": rb_proxy_domains}
                        elif applied_egress == "socks5":
                            rollback_socks = {"enabled": True, "source": "manual", "addr": egress.get("socks5_addr", ""), "port": int(egress.get("socks5_port", 0)), "user": egress.get("socks5_user", ""), "pass": egress.get("socks5_pass", ""), "mode": rb_proxy_mode, "domains": rb_proxy_domains}
                        else:
                            rollback_socks = {}
                        rollback_warp = applied_egress[5:] if applied_egress.startswith("warp_") else "off"
                        build_singbox_config(nodes, current_proxy_config, peers, mesh, rollback_socks, rollback_warp)
                        rollback_healthy = _singbox_service_healthy()
                    except Exception:
                        rollback_healthy = False
                    retries = int(pending_failure.get("retries", 0)) + 1
                    retry_delay = min(300, 30 * (2 ** min(retries - 1, 4)))
                    result = {"success": False, "component": "egress", "revision": revision, "desired_mode": desired_egress, "applied_mode": applied_egress, "rolled_back": rollback_healthy, "rollback_healthy": rollback_healthy, "error": str(error)[:500], "retries": retries, "retry_after": int(time.time() + retry_delay), "applied_at": int(time.time() * 1000)}
                    _save_warp_state(applied_egress, applied_revision, result)
                    _schedule_egress_retry(retry_delay)
                    try:
                        ack = _post_warp_result(result)
                        if not ack.get("accepted"): pass
                    except Exception: pass
                    if realtime_channel and realtime_channel.connected: realtime_channel.send(result, "config.result")
                elif realtime_channel and realtime_channel.connected:
                    realtime_channel.send({"success": False, "component": "config", "config_hash": config_hash, "error": str(error)[:500], "old_config_active": _singbox_service_healthy(), "rollback_healthy": _singbox_service_healthy(), "applied_at": int(time.time() * 1000)}, "config.result")
                raise
            return nodes
    except Exception as error:
        print(f"[agent] config fetch/apply failed: {error}", flush=True)
    return None

if __name__ == "__main__":
    heartbeat_state = {"nodes": [], "argo_urls": []}

    def on_realtime_message(message):
        global realtime_status_interval
        if message.get("type") == "status.interval":
            requested_interval = int(message.get("seconds", REALTIME_STATUS_IDLE_INTERVAL))
            realtime_status_interval = max(REALTIME_STATUS_ACTIVE_INTERVAL, min(REALTIME_STATUS_IDLE_INTERVAL, requested_interval))
            heartbeat_wakeup.set()
        if message.get("type") in {"config.refresh", "transport.connected", "transport.disconnected"}: config_wakeup.set()
        if message.get("type") in {"transport.connected", "transport.disconnected"}: heartbeat_wakeup.set()

    def create_realtime_channel():
        return RealtimeChannel(REALTIME_URL, VPS_IP, TOKEN, "core", on_realtime_message)

    realtime_channel = create_realtime_channel()
    realtime_channel.start()

    def heartbeat_loop():
        while True:
            started = time.monotonic()
            try:
                websocket_online = bool(realtime_channel and realtime_channel.connected)
                fallback_ready = not realtime_channel or not realtime_channel.enabled or time.time() - (realtime_channel.last_disconnected or realtime_channel.started_at) >= 30
                report_status(list(heartbeat_state["nodes"]), list(heartbeat_state["argo_urls"]), force_http=not websocket_online, allow_http=websocket_online or fallback_ready)
            except Exception as error:
                print(f"[agent] heartbeat loop error: {error}", flush=True)
            elapsed = time.monotonic() - started
            if realtime_channel and realtime_channel.connected:
                heartbeat_interval = realtime_status_interval
            elif realtime_channel and realtime_channel.enabled and not realtime_channel.ever_connected and time.time() - realtime_channel.started_at < 30:
                heartbeat_interval = max(1, 30 - (time.time() - realtime_channel.started_at))
            elif realtime_channel and realtime_channel.ever_connected and time.time() - realtime_channel.last_disconnected < 30:
                heartbeat_interval = max(1, 30 - (time.time() - realtime_channel.last_disconnected))
            else:
                heartbeat_interval = min(max(90, global_interval), 300)
            heartbeat_wakeup.wait(timeout=max(1, heartbeat_interval - min(heartbeat_interval - 1, elapsed)))
            heartbeat_wakeup.clear()

    time.sleep(2)
    initial_nodes = fetch_and_apply_configs()
    if os.path.exists("/opt/kui/.update-pending"):
        if initial_nodes is None or not _singbox_service_healthy() or not report_status(list(initial_nodes), [], force_http=True):
            print("[agent] updated version failed readiness checks", flush=True)
            raise SystemExit(1)
        try: os.remove("/opt/kui/.update-pending")
        except FileNotFoundError: pass
    if initial_nodes is not None: heartbeat_state["nodes"] = initial_nodes
    threading.Thread(target=heartbeat_loop, name="kui-heartbeat", daemon=True).start()
    while True:
        config_wakeup.clear()
        while realtime_channel and realtime_channel.enabled and not realtime_channel.connected:
            grace_remaining = 30 - (time.time() - (realtime_channel.last_disconnected or realtime_channel.started_at))
            if grace_remaining <= 0:
                break
            config_wakeup.wait(timeout=grace_remaining)
            config_wakeup.clear()
        loop_started = time.monotonic()
        try:
            check_for_update()
            fetched_nodes = fetch_and_apply_configs()
            if fetched_nodes is not None: heartbeat_state["nodes"] = fetched_nodes
            heartbeat_state["argo_urls"] = process_argo_nodes(heartbeat_state["nodes"])
        except Exception as error:
            print(f"[agent] main loop error: {error}", flush=True)
        elapsed = time.monotonic() - loop_started
        if elapsed > 20:
            print(f"[agent] slow loop completed in {elapsed:.1f}s", flush=True)
        config_interval = REALTIME_HTTP_INTERVAL if realtime_channel and realtime_channel.connected else (30 if fast_mode else 300)
        config_wakeup.wait(timeout=max(1, config_interval - min(config_interval - 1, elapsed)))
