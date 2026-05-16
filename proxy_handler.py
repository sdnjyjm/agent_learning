import sys
import os
import time
import json
import winreg
import ctypes
import subprocess
import threading
from config import load_config, save_config, SESSIONS_FILE

PROXY_PORT = 8080

def log_debug(msg):
    with open("mitm_debug.log", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        f.flush()

def get_system_proxy_status():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
                             0, winreg.KEY_READ)
        proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')
        proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
        winreg.CloseKey(key)

        is_enabled = proxy_enable == 1

        proxy_server_lower = proxy_server.lower()
        our_proxy_patterns = [
            f'127.0.0.1:{PROXY_PORT}',
            f'localhost:{PROXY_PORT}',
        ]
        is_our_proxy = any(pattern in proxy_server_lower for pattern in our_proxy_patterns)

        if not is_our_proxy and f'={PROXY_PORT}' in proxy_server:
            parts = proxy_server.split(';')
            for part in parts:
                if f'127.0.0.1:{PROXY_PORT}' in part or f'localhost:{PROXY_PORT}' in part:
                    is_our_proxy = True
                    break

        return is_enabled, is_our_proxy, proxy_server
    except Exception as e:
        log_debug(f"get_system_proxy_status error: {e}")
        return False, False, ""

def set_system_proxy(enable=True):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
                             0, winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 1 if enable else 0)
        if enable:
            winreg.SetValueEx(key, 'ProxyServer', 0, winreg.REG_SZ, f'127.0.0.1:{PROXY_PORT}')
        winreg.CloseKey(key)
        ctypes.windll.wininet.InternetSetOptionW(0, 39, 0, 0)
        ctypes.windll.wininet.InternetSetOptionW(0, 37, 0, 0)
        return True
    except Exception as e:
        log_debug(f"set_system_proxy error: {e}")
        return False

def export_mitm_cert_p12():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.hazmat.backends import default_backend
        from cryptography import x509

        cert_dir = os.path.join(os.path.expanduser("~"), ".mitmproxy")
        cert_path = os.path.join(cert_dir, "mitmproxy-ca-cert.pem")
        if not os.path.exists(cert_path):
            cert_path = os.path.join(cert_dir, "mitmproxy-ca-cert.cer")

        if not os.path.exists(cert_path):
            return False, "证书文件未找到，请先运行mitmdump生成证书"

        export_dir = os.path.dirname(os.path.abspath(__file__))
        p12_path = os.path.join(export_dir, "mitmproxy-ca-cert.p12")
        privkey_path = os.path.join(cert_dir, "mitmproxy-ca-cert-privkey.pem")

        with open(cert_path, "rb") as f:
            cert_data = f.read()

        cert_obj = x509.load_pem_x509_certificate(cert_data, default_backend())

        private_key = None
        if os.path.exists(privkey_path):
            with open(privkey_path, "rb") as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
        else:
            try:
                private_key = serialization.load_pem_private_key(cert_data, password=None, backend=default_backend())
            except:
                pass

        if private_key:
            p12_data = pkcs12.serialize_key_and_certificates(
                name=b"mitmproxy",
                key=private_key,
                cert=cert_obj,
                cas=None,
                encryption_algorithm=serialization.NoEncryption()
            )
        else:
            p12_data = pkcs12.serialize_key_and_certificates(
                name=b"mitmproxy",
                key=None,
                cert=cert_obj,
                cas=None,
                encryption_algorithm=serialization.NoEncryption()
            )

        with open(p12_path, "wb") as f:
            f.write(p12_data)

        return True, f"证书已导出到: {p12_path}"
    except Exception as e:
        log_debug(f"export_mitm_cert_p12 error: {e}")
        return False, str(e)

def start_mitmproxy(script_path, port=8080):
    cmd = [
        sys.executable, "-m", "mitmproxy",
        "--mode", f"regular@{port}",
        "-q",
        "-s", script_path
    ]
    try:
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return proc
    except Exception as e:
        log_debug(f"start_mitmproxy error: {e}")
        return None

def stop_mitmproxy(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except:
            proc.kill()

class ProxyManager:
    def __init__(self, port=8080):
        self.port = port
        self.proc = None
        self.running = False

    def start(self, script_path):
        if self.running:
            return True
        set_system_proxy(True)
        self.proc = start_mitmproxy(script_path, self.port)
        self.running = self.proc is not None
        return self.running

    def stop(self):
        if not self.running:
            return
        set_system_proxy(False)
        stop_mitmproxy(self.proc)
        self.running = False
        self.proc = None

    def is_running(self):
        return self.running

proxy_manager = ProxyManager()
