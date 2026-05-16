from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QTableWidget, QTableWidgetItem,
                             QHeaderView, QTextEdit, QSplitter, QMenu, QAction,
                             QMessageBox, QStatusBar, QToolBar, QFrame, QCheckBox,
                             QGroupBox, QProgressBar, QApplication)
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette
import json
import time
import threading
import subprocess
import sys
import os
from pathlib import Path

from config import load_config, save_config, load_sessions, save_sessions
from proxy_handler import set_system_proxy, export_mitm_cert_p12, get_system_proxy_status
from llm_manager import LLMManagerDialog
from session_flow_window import SessionFlowWindow
from ai_analyzer import AIAnalyzerDialog

class MainWindow(QMainWindow):
    def __init__(self, proxy_proc=None):
        super().__init__()
        self.sessions = []
        self.proxy_running = False
        self.proxy_proc = proxy_proc
        self.config = load_config()
        
        self.detect_proxy_status()
        
        self.init_ui()
        self.load_sessions()
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.check_for_new_sessions)
        self.refresh_timer.start(1000)
        
        self.proxy_check_timer = QTimer()
        self.proxy_check_timer.timeout.connect(self.update_proxy_status_display)
        self.proxy_check_timer.start(5000)

    def detect_proxy_status(self):
        is_enabled, is_our_proxy, proxy_server = get_system_proxy_status()
        self.proxy_running = is_enabled and is_our_proxy

    def update_proxy_status_display(self):
        is_enabled, is_our_proxy, proxy_server = get_system_proxy_status()
        if is_enabled and is_our_proxy:
            self.proxy_status_label.setText("代理状态: 运行中")
            self.proxy_status_label.setStyleSheet("color: #98C379; font-weight: bold; padding: 0 10px;")
            self.set_proxy_btn.setEnabled(False)
            self.unset_proxy_btn.setEnabled(True)
        elif is_enabled and not is_our_proxy:
            self.proxy_status_label.setText(f"代理状态: 第三方代理 ({proxy_server})")
            self.proxy_status_label.setStyleSheet("color: #DCDCAA; font-weight: bold; padding: 0 10px;")
            self.set_proxy_btn.setEnabled(True)
            self.unset_proxy_btn.setEnabled(False)
        else:
            self.proxy_status_label.setText("代理状态: 已停止")
            self.proxy_status_label.setStyleSheet("color: #FF6B6B; font-weight: bold; padding: 0 10px;")
            self.set_proxy_btn.setEnabled(True)
            self.unset_proxy_btn.setEnabled(False)

    def init_ui(self):
        self.setWindowTitle("Agent Learning")
        self.setMinimumSize(1200, 800)

        self.create_toolbar()
        self.create_central_widget()
        self.create_statusbar()

        self.apply_stylesheet()

    def create_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.proxy_status_label = QLabel("代理状态: 已停止")
        self.proxy_status_label.setStyleSheet("color: #FF6B6B; font-weight: bold; padding: 0 10px;")
        toolbar.addWidget(self.proxy_status_label)

        toolbar.addSeparator()

        self.set_proxy_btn = QPushButton("设置系统代理")
        self.set_proxy_btn.clicked.connect(self.on_set_proxy)
        toolbar.addWidget(self.set_proxy_btn)

        self.unset_proxy_btn = QPushButton("取消系统代理")
        self.unset_proxy_btn.clicked.connect(self.on_unset_proxy)
        self.unset_proxy_btn.setEnabled(False)
        toolbar.addWidget(self.unset_proxy_btn)

        toolbar.addSeparator()

        self.trust_cert_btn = QPushButton("导出MITM证书")
        self.trust_cert_btn.clicked.connect(self.on_export_cert)
        toolbar.addWidget(self.trust_cert_btn)

        toolbar.addSeparator()

        self.llm_manager_btn = QPushButton("大模型管理")
        self.llm_manager_btn.clicked.connect(self.on_open_llm_manager)
        toolbar.addWidget(self.llm_manager_btn)

        self.clear_sessions_btn = QPushButton("清空会话")
        self.clear_sessions_btn.clicked.connect(self.on_clear_sessions)
        toolbar.addWidget(self.clear_sessions_btn)

    def create_central_widget(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)

        self.create_session_list_panel(splitter)
        self.create_session_detail_panel(splitter)

        splitter.setSizes([400, 800])
        layout.addWidget(splitter)

    def create_session_list_panel(self, parent):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setMaximumWidth(500)
        layout = QVBoxLayout(frame)

        header = QLabel("会话列表 (HTTP Inspector)")
        header.setStyleSheet("background-color: #0E639C; color: white; padding: 5px; font-weight: bold;")
        layout.addWidget(header)

        self.session_table = QTableWidget()
        self.session_table.setColumnCount(6)
        self.session_table.setHorizontalHeaderLabels(["#", "时间", "模型", "首字", "耗时", "Token"])
        self.session_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.session_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.session_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.session_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.session_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.session_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.session_table.setColumnWidth(0, 40)
        self.session_table.setColumnWidth(1, 80)
        self.session_table.setColumnWidth(3, 60)
        self.session_table.setColumnWidth(4, 60)
        self.session_table.setColumnWidth(5, 60)
        self.session_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.session_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.session_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.session_table.itemClicked.connect(self.on_session_selected)
        self.session_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_table.customContextMenuRequested.connect(self.on_context_menu)
        layout.addWidget(self.session_table)

        parent.addWidget(frame)

    def create_session_detail_panel(self, parent):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(frame)

        self.detail_tabs = QWidget()
        detail_layout = QVBoxLayout(self.detail_tabs)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFont(QFont("Consolas", 10))
        self.detail_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
        """)
        detail_layout.addWidget(self.detail_text)

        layout.addWidget(self.detail_tabs)
        parent.addWidget(frame)

    def create_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2D2D30;
            }
            QToolBar {
                background-color: #383838;
                border: none;
                padding: 2px;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 5px 12px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:disabled {
                background-color: #4A4A4A;
                color: #808080;
            }
            QTableWidget {
                background-color: #1E1E1E;
                color: #A9B7C6;
                gridline-color: #3C3C3C;
                border: none;
            }
            QHeaderView::section {
                background-color: #383838;
                color: #CCCCCC;
                padding: 4px;
                border: 1px solid #2D2D30;
            }
            QLabel {
                color: #CCCCCC;
            }
            QStatusBar {
                background-color: #007ACC;
                color: white;
            }
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
        """)

    def load_sessions(self):
        self.sessions = load_sessions()
        self.refresh_session_table()

    def refresh_session_table(self):
        self.session_table.setRowCount(len(self.sessions))
        for i, s in enumerate(self.sessions):
            self.session_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.session_table.setItem(i, 1, QTableWidgetItem(s.get('timestamp', '')[-8:]))
            self.session_table.setItem(i, 2, QTableWidgetItem(s.get('model', 'unknown')))
            self.session_table.setItem(i, 3, QTableWidgetItem(s.get('ttft', 'N/A')))
            self.session_table.setItem(i, 4, QTableWidgetItem(s.get('duration', 'N/A')))
            tokens = s.get('tokens', {})
            token_str = f"{tokens.get('total_tokens', 0)}"
            self.session_table.setItem(i, 5, QTableWidgetItem(token_str))

            for col in range(6):
                item = self.session_table.item(i, col)
                if item:
                    item.setBackground(QColor("#1E1E1E"))
                    item.setForeground(QColor("#A9B7C6"))

        self.status_bar.showMessage(f"共 {len(self.sessions)} 条会话")

    def check_for_new_sessions(self):
        current_sessions = load_sessions()
        if len(current_sessions) > len(self.sessions):
            self.sessions = current_sessions
            self.refresh_session_table()

    def on_session_selected(self, item):
        row = item.row()
        if 0 <= row < len(self.sessions):
            s = self.sessions[row]
            self.display_session_detail(s)

    def display_session_detail(self, session):
        import json
        import re
        
        def decode_escapes(s):
            if s is None:
                return ""
            s = str(s)
            
            if '\\n' in s or '\\t' in s or '\\r' in s or '\\"' in s or "\\'" in s or '\\\\' in s:
                try:
                    import ast
                    try:
                        if s.startswith('"') and s.endswith('"') or s.startswith("'") and s.endswith("'"):
                            return ast.literal_eval(s)
                        return ast.literal_eval(f'"{s}"')
                    except:
                        pass
                except:
                    pass
            
            return s
        
        def escape_html(s):
            if s is None:
                return ""
            s = str(s)
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;")
        
        def format_content(content):
            if content is None:
                return ""
            if isinstance(content, list):
                result = []
                for item in content:
                    if isinstance(item, dict):
                        result.append(json.dumps(item, indent=2, ensure_ascii=False))
                    else:
                        result.append(decode_escapes(str(item)))
                return '\n'.join(result)
            if isinstance(content, dict):
                return json.dumps(content, indent=2, ensure_ascii=False)
            return decode_escapes(str(content))
        
        user_content = format_content(session.get('user', ''))
        ai_content = format_content(session.get('ai', ''))
        reasoning_content = format_content(session.get('reasoning', ''))
        
        html_parts = [
            f"""<html>
<head>
<style>
    body {{ font-family: 'Consolas', monospace; background-color: #1E1E1E; color: #D4D4D4; margin: 10px; }}
    .header {{ background-color: #2D2D30; padding: 10px; border-radius: 5px; margin-bottom: 10px; }}
    .meta {{ color: #FFC66D; }}
    .user {{ color: #A9B7C6; background-color: #252526; padding: 10px; border-radius: 3px; margin: 5px 0; white-space: pre-wrap; }}
    .ai {{ color: #629755; background-color: #252526; padding: 10px; border-radius: 3px; margin: 5px 0; white-space: pre-wrap; }}
    .reasoning {{ color: #DCDCAA; background-color: #252526; padding: 10px; border-radius: 3px; margin: 5px 0; white-space: pre-wrap; }}
    .json {{ color: #CE9178; background-color: #252526; padding: 10px; border-radius: 3px; margin: 5px 0; white-space: pre-wrap; font-family: 'Consolas', monospace; }}
    h3 {{ color: #569CD6; margin: 10px 0 5px 0; }}
</style>
</head>
<body>
<div class="header">
<span class="meta">URL:</span> {escape_html(session.get('url', 'N/A'))}<br>
<span class="meta">模型:</span> {escape_html(session.get('model', 'unknown'))} |
<span class="meta">首字延迟:</span> {escape_html(session.get('ttft', 'N/A'))} |
<span class="meta">总耗时:</span> {escape_html(session.get('duration', 'N/A'))} |
<span class="meta">速度:</span> {escape_html(session.get('speed', 'N/A'))}<br>
<span class="meta">Token:</span> 输入 {session.get('tokens', {}).get('prompt_tokens', 0)} /
输出 {session.get('tokens', {}).get('completion_tokens', 0)} /
总计 {session.get('tokens', {}).get('total_tokens', 0)}
</div>

<h3>用户消息:</h3>
<div class="user">{escape_html(user_content)}</div>

<h3>AI回复:</h3>
<div class="ai">{escape_html(ai_content)}</div>"""
        ]
        
        if reasoning_content:
            html_parts.append(f"""
<h3>Reasoning:</h3>
<div class="reasoning">{escape_html(reasoning_content)}</div>""")
        
        function_call = session.get('function_call')
        if function_call:
            func_json = json.dumps(function_call, indent=2, ensure_ascii=False)
            html_parts.append(f"""
<h3>Function Call:</h3>
<div class="json">{escape_html(func_json)}</div>""")
        
        tool_calls = session.get('tool_calls')
        if tool_calls:
            tool_json = json.dumps(tool_calls, indent=2, ensure_ascii=False)
            html_parts.append(f"""
<h3>Tool Calls:</h3>
<div class="json">{escape_html(tool_json)}</div>""")
        
        html_parts.append("""
</body>
</html>""")
        
        self.detail_text.setHtml(''.join(html_parts))

    def on_context_menu(self, pos):
        selected_rows = set([item.row() for item in self.session_table.selectedItems()])
        if not selected_rows:
            return

        menu = QMenu()

        view_action = QAction("查看会话详情", self)
        view_action.triggered.connect(lambda: self.on_view_session_detail(selected_rows))
        menu.addAction(view_action)

        analyze_action = QAction("AI解析会话内容", self)
        analyze_action.triggered.connect(lambda: self.on_ai_analyze(selected_rows))
        menu.addAction(analyze_action)

        menu.addSeparator()

        delete_action = QAction("删除会话", self)
        delete_action.triggered.connect(lambda: self.on_delete_sessions(selected_rows))
        menu.addAction(delete_action)

        menu.exec_(self.session_table.mapToGlobal(pos))

    def on_view_session_detail(self, rows):
        selected_sessions = [self.sessions[row] for row in sorted(rows) if 0 <= row < len(self.sessions)]
        if selected_sessions:
            dlg = SessionFlowWindow(selected_sessions, self)
            dlg.exec_()

    def on_ai_analyze(self, rows):
        selected = [self.sessions[r] for r in rows if 0 <= r < len(self.sessions)]
        if not selected:
            return
        dlg = AIAnalyzerDialog(selected, self)
        dlg.exec_()

    def on_delete_sessions(self, rows):
        reply = QMessageBox.question(self, "确认", f"确定要删除选中的 {len(rows)} 条会话吗?",
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            indices = sorted(rows, reverse=True)
            for idx in indices:
                if 0 <= idx < len(self.sessions):
                    self.sessions.pop(idx)
            save_sessions(self.sessions)
            self.refresh_session_table()

    def on_set_proxy(self):
        if not self.proxy_running:
            set_system_proxy(True)
            self.proxy_running = True
            self.proxy_status_label.setText("代理状态: 运行中")
            self.proxy_status_label.setStyleSheet("color: #98C379; font-weight: bold; padding: 0 10px;")
            self.set_proxy_btn.setEnabled(False)
            self.unset_proxy_btn.setEnabled(True)
            self.status_bar.showMessage("系统代理已设置")

    def on_unset_proxy(self):
        if self.proxy_running:
            set_system_proxy(False)
            self.proxy_running = False
            self.proxy_status_label.setText("代理状态: 已停止")
            self.proxy_status_label.setStyleSheet("color: #FF6B6B; font-weight: bold; padding: 0 10px;")
            self.set_proxy_btn.setEnabled(True)
            self.unset_proxy_btn.setEnabled(False)
            self.status_bar.showMessage("系统代理已取消")

    def on_export_cert(self):
        success, msg = export_mitm_cert_p12()
        if success:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)

    def on_open_llm_manager(self):
        dlg = LLMManagerDialog(self)
        dlg.exec_()

    def on_clear_sessions(self):
        reply = QMessageBox.question(self, "确认", "确定要清空所有会话吗?",
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.sessions = []
            save_sessions([])
            self.refresh_session_table()
            self.detail_text.clear()

    def closeEvent(self, event):
        event.accept()
