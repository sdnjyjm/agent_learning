from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QLabel, QComboBox, QProgressBar, QMessageBox,
                             QSplitter, QFrame)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import requests
import json
import os
from config import load_llm_profiles
from llm_manager import LLMProfile

class AnalyzeWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, sessions, profile, user_prompt):
        super().__init__()
        self.sessions = sessions
        self.profile = profile
        self.user_prompt = user_prompt

    def run(self):
        try:
            self.progress.emit(10)
            prompt = self.build_prompt()
            self.progress.emit(30)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.profile.api_key}"
            }

            system_prompt = "这是我使用本地agent和大模型交互产生的请求和响应数据，我是一个智能体开发入门人员，现在要学习智能体的工作原理，请根据用户输入的内容帮我分析本地agent是如何理解大模型指令工作的。"

            if self.profile.provider == "anthropic":
                headers["x-api-key"] = self.profile.api_key
                headers["anthropic-version"] = "2023-06-01"
                data = {
                    "model": self.profile.model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}]
                }
                url = f"{self.profile.base_url}/v1/messages"
            else:
                data = {
                    "model": self.profile.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7
                }
                url = f"{self.profile.base_url}/chat/completions"

            self.progress.emit(50)
            response = requests.post(url, headers=headers, json=data, timeout=120,verify= False)
            self.progress.emit(80)

            if response.status_code == 200:
                result = response.json()
                if self.profile.provider == "anthropic":
                    analysis = result["content"][0]["text"]
                else:
                    analysis = result["choices"][0]["message"]["content"]
                self.progress.emit(100)
                self.finished.emit(analysis)
            else:
                self.error.emit(f"API错误: {response.status_code}\n{response.text}")

        except Exception as e:
            self.error.emit(str(e))

    def load_json_file(self, session_num, file_type):
        config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
        file_path = os.path.join(config_dir, f"{session_num}-{file_type}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def build_prompt(self):
        sessions_data = []
        for i, s in enumerate(self.sessions):
            session_num = i + 1
            req_data = self.load_json_file(session_num, 'req')
            resp_data = self.load_json_file(session_num, 'resp')

            req_json = json.dumps(req_data, indent=2, ensure_ascii=False) if req_data else "文件不存在"
            resp_json = json.dumps(resp_data, indent=2, ensure_ascii=False) if resp_data else "文件不存在"

            session_info = f"""=== 会话 {session_num} ===
URL: {s.get('url', 'N/A')}
模型: {s.get('model', 'unknown')}
时间: {s.get('timestamp', 'N/A')}

用户消息:
{s.get('user', '')}

AI回复:
{s.get('ai', '')}

请求数据 (req.json):
{req_json}

响应数据 (resp.json):
{resp_json}

---"""
            sessions_data.append(session_info)

        prompt = f"""{self.user_prompt}

以下是相关的会话数据：

{"".join(sessions_data)}

请基于以上数据进行分析："""

        return prompt

class AIAnalyzerDialog(QDialog):
    def __init__(self, sessions, parent=None):
        super().__init__(parent)
        self.sessions = sessions
        self.profiles = [LLMProfile.from_dict(p) for p in load_llm_profiles()]
        self.worker = None
        self.setWindowTitle(f"AI会话分析 (已选{len(sessions)}条)")
        self.setMinimumSize(1200, 800)
        self.showMaximized()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("选择大模型:"))
        self.profile_combo = QComboBox()
        if not self.profiles:
            self.profile_combo.addItem("未配置 - 请先在设置中添加")
        else:
            for p in self.profiles:
                self.profile_combo.addItem(f"{p.name} ({p.provider})", p)
        top_layout.addWidget(self.profile_combo)

        self.analyze_btn = QPushButton("开始分析")
        self.analyze_btn.clicked.connect(self.start_analysis)
        top_layout.addWidget(self.analyze_btn)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        left_panel = QFrame()
        left_panel.setFrameShape(QFrame.StyledPanel)
        left_layout = QVBoxLayout(left_panel)
        
        left_header = QLabel("用户提示词")
        left_header.setStyleSheet("background-color: #0E639C; color: white; padding: 8px; font-weight: bold;")
        left_layout.addWidget(left_header)
        
        self.user_prompt_text = QTextEdit()
        self.user_prompt_text.setFont(QFont("Microsoft YaHei", 10))
        self.user_prompt_text.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        self.user_prompt_text.setPlaceholderText("请输入您的分析需求，例如：\n分析这个agent是如何理解并执行工具调用的？\n解释agent的思考过程和决策逻辑...")
        left_layout.addWidget(self.user_prompt_text)
        
        system_prompt_label = QLabel("系统提示词")
        system_prompt_label.setStyleSheet("background-color: #0E639C; color: white; padding: 8px; font-weight: bold; margin-top: 10px;")
        left_layout.addWidget(system_prompt_label)
        
        self.system_prompt_text = QTextEdit()
        self.system_prompt_text.setFont(QFont("Microsoft YaHei", 10))
        self.system_prompt_text.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        self.system_prompt_text.setText("这是我使用本地agent和大模型交互产生的请求和响应数据，我是一个智能体开发入门人员，现在要学习智能体的工作原理，请根据用户输入的内容帮我分析本地agent是如何理解大模型指令工作的。")
        self.system_prompt_text.setReadOnly(True)
        left_layout.addWidget(self.system_prompt_text)
        
        self.splitter.addWidget(left_panel)

        right_panel = QFrame()
        right_panel.setFrameShape(QFrame.StyledPanel)
        right_layout = QVBoxLayout(right_panel)
        
        right_header = QLabel("分析结果")
        right_header.setStyleSheet("background-color: #0E639C; color: white; padding: 8px; font-weight: bold;")
        right_layout.addWidget(right_header)
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Microsoft YaHei", 10))
        self.result_text.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        right_layout.addWidget(self.result_text)
        
        self.splitter.addWidget(right_panel)

        self.splitter.setSizes([600, 600])

    def start_analysis(self):
        if not self.profiles:
            QMessageBox.warning(self, "提示", "请先在大模型管理中添加配置")
            return

        idx = self.profile_combo.currentIndex()
        if idx < 0 or idx >= len(self.profiles):
            QMessageBox.warning(self, "提示", "请选择有效的大模型配置")
            return

        user_prompt = self.user_prompt_text.toPlainText().strip()
        if not user_prompt:
            QMessageBox.warning(self, "提示", "请输入分析需求")
            return

        profile = self.profiles[idx]
        self.analyze_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.result_text.setText("正在分析...")

        self.worker = AnalyzeWorker(self.sessions, profile, user_prompt)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.start()

    def on_finished(self, result):
        self.result_text.setText(result)
        self.analyze_btn.setEnabled(True)
        self.progress.setVisible(False)

    def on_error(self, error_msg):
        self.result_text.setText(f"错误: {error_msg}")
        self.analyze_btn.setEnabled(True)
        self.progress.setVisible(False)

    def close(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.accept()
