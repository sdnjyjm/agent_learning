import sys
import os
import ctypes
import subprocess
import json
from pathlib import Path

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def get_config_dir():
    base = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, 'config')
    ensure_dir(d)
    return d

CONFIG_DIR = get_config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
SESSIONS_FILE = os.path.join(CONFIG_DIR, 'sessions.json')
LLM_PROFILES_FILE = os.path.join(CONFIG_DIR, 'llm_profiles.json')

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'proxy_port': 8080, 'auto_proxy': True}

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_sessions():
    sessions = []
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            sessions.append(json.loads(line))
                        except:
                            pass
        except:
            pass
    return sessions

def save_sessions(sessions):
    with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
        for session in sessions:
            f.write(json.dumps(session, ensure_ascii=False) + '\n')

def load_llm_profiles():
    if os.path.exists(LLM_PROFILES_FILE):
        with open(LLM_PROFILES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_llm_profiles(profiles):
    with open(LLM_PROFILES_FILE, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)
