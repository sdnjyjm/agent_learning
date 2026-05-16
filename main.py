import sys
import os
import ctypes
import subprocess
import threading
import time
import json
import signal
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer, QCoreApplication

from config import is_admin, get_config_dir, SESSIONS_FILE, load_sessions
from main_window import MainWindow
from proxy_handler import set_system_proxy

PROXY_PORT = 8080
DB_FILE = SESSIONS_FILE

def log_debug(msg):
    try:
        with open("llm_monitor.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
            f.flush()
        print(f"DEBUG: {msg}")
    except Exception as e:
        print(f"Failed to write log: {e}")

def start_mitmproxy(script_path):
    log_debug(f"Starting mitmdump with script: {script_path}")
    log_debug(f"Script exists: {os.path.exists(script_path)}")
    
    proxy_cmd = [
        sys.executable, "-c",
        f"from mitmproxy.tools.main import mitmdump; import sys; "
        f"sys.argv[1:] = ['--mode', 'regular@8080', '-q', '-s', r'{script_path}']; "
        f"mitmdump()"
    ]
    log_debug(f"Command: {' '.join(proxy_cmd[:2])} ...")
    
    try:
        proc = subprocess.Popen(proxy_cmd, 
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        log_debug(f"mitmdump started with PID {proc.pid}")
        
        time.sleep(1)
        if proc.poll() is not None:
            log_debug(f"mitmdump exited immediately!")
            return None
        
        return proc
    except Exception as e:
        log_debug(f"start mitmdump error: {type(e).__name__}: {e}")
        return None

def main():
    log_debug("="*50)
    log_debug("LLM Monitor starting...")
    log_debug(f"Python version: {sys.version}")
    log_debug(f"Working directory: {os.getcwd()}")
    
    log_debug(f"Running as administrator: {is_admin()}")
    
    config_dir = get_config_dir()
    log_debug(f"Config directory: {config_dir}")
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    
    if os.path.exists(DB_FILE):
        log_debug(f"Removing existing sessions file: {DB_FILE}")
        os.remove(DB_FILE)
    log_debug(f"Sessions file path: {DB_FILE}")

    for f in os.listdir(config_dir):
        if f.endswith('-req.json') or f.endswith('-resp.json'):
            f_path = os.path.join(config_dir, f)
            try:
                os.remove(f_path)
                log_debug(f"Removed existing file: {f_path}")
            except:
                pass

    app = QApplication(sys.argv)
    log_debug("Qt application created")

    script_path = os.path.abspath('mitm_addon.py').replace('\\', '/')
    log_debug(f"Addon script path: {script_path}")
    
    proxy_proc = start_mitmproxy(script_path)
    if proxy_proc:
        log_debug("mitmdump started successfully")
    else:
        log_debug("FAILED to start mitmdump!")

    window = MainWindow(proxy_proc)
    window.show()
    log_debug("Main window shown")

    def update_sessions():
        try:
            log_debug(f"Checking for new sessions...")
            log_debug(f"Sessions file exists: {os.path.exists(DB_FILE)}")
            
            if os.path.exists(DB_FILE):
                file_size = os.path.getsize(DB_FILE)
                log_debug(f"Sessions file size: {file_size} bytes")
                
                with open(DB_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    log_debug(f"File content preview (first 500 chars): {content[:500]}")
                    f.seek(0)
                    lines = f.readlines()
                    log_debug(f"Number of lines in sessions file: {len(lines)}")
                
                sessions = []
                for i, line in enumerate(lines):
                    line = line.strip()
                    if line:
                        try:
                            s = json.loads(line)
                            sessions.append(s)
                            log_debug(f"Loaded session {i}: model={s.get('model', 'unknown')}, user_len={len(s.get('user', ''))}")
                        except Exception as e:
                            log_debug(f"Failed to parse line {i}: {e}")
                
                if sessions and sessions != window.sessions:
                    log_debug(f"Found {len(sessions) - len(window.sessions)} new sessions")
                    window.sessions = sessions
                    from config import save_sessions
                    save_sessions(sessions)
                    window.refresh_session_table()
                else:
                    log_debug(f"No new sessions (current: {len(window.sessions)})")
        except Exception as e:
            log_debug(f"update_sessions error: {type(e).__name__}: {e}")
        
        QTimer.singleShot(1000, update_sessions)

    QTimer.singleShot(2000, update_sessions)
    log_debug("Session update timer started")

    def cleanup():
        log_debug("Cleaning up...")
        
        if proxy_proc and proxy_proc.poll() is None:
            log_debug("Terminating mitmdump process (PID: {})...".format(proxy_proc.pid))
            try:
                proxy_proc.terminate()
                log_debug("Waiting for mitmdump to exit (timeout 3s)...")
                try:
                    proxy_proc.wait(timeout=3)
                    log_debug("mitmdump terminated gracefully")
                except subprocess.TimeoutExpired:
                    log_debug("mitmdump did not exit in time, force killing...")
                    try:
                        import os
                        os.kill(proxy_proc.pid, signal.SIGKILL)
                    except:
                        proxy_proc.kill()
                    proxy_proc.wait(timeout=2)
                    log_debug("mitmdump killed")
            except Exception as e:
                log_debug(f"Error terminating mitmdump: {type(e).__name__}: {e}")
                try:
                    proxy_proc.kill()
                    proxy_proc.wait(timeout=1)
                except:
                    pass
        
        log_debug("Disabling system proxy...")
        try:
            set_system_proxy(False)
            log_debug("System proxy disabled")
        except Exception as e:
            log_debug(f"Error disabling proxy: {type(e).__name__}: {e}")
        
        log_debug("Cleanup complete")

    def handle_signal(signum, frame):
        log_debug(f"Received signal {signum}, initiating cleanup...")
        cleanup()
        QCoreApplication.quit()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, handle_signal)

    app.aboutToQuit.connect(cleanup)

    log_debug("Entering Qt event loop...")
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
