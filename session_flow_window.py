from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QLabel, QSplitter, QFrame, QSizePolicy,
                             QTreeWidget, QTreeWidgetItem, QHeaderView, QWidget, QApplication)
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer, QEvent
from PyQt5.QtGui import QFont, QColor, QBrush, QCursor
import json
import os
import re

class CustomTooltip(QDialog):
    def __init__(self, parent=None, tree_parent=None):
        super().__init__(parent)
        self.tree_parent = tree_parent
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            CustomTooltip {
                background-color: #2D2D2D;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2D2D2D;
                color: #D4D4D4;
                border: none;
            }
        """)
        self.text_edit.setMouseTracking(True)
        self.text_edit.installEventFilter(self)
        layout.addWidget(self.text_edit)

    def eventFilter(self, obj, event):
        if obj == self.text_edit:
            if event.type() == QEvent.Enter:
                if self.tree_parent:
                    self.tree_parent.cancel_hide()
                    self.tree_parent.set_in_tooltip(True)
            elif event.type() == QEvent.Leave:
                if self.tree_parent:
                    self.tree_parent.set_in_tooltip(False)
                    self.tree_parent.start_hide_timer()
            elif event.type() == QEvent.MouseButtonPress:
                if self.tree_parent:
                    self.tree_parent.set_in_tooltip(True)
            return True
        return super().eventFilter(obj, event)

    def set_text(self, text):
        processed_text = self.process_escapes(text)
        self.text_edit.setPlainText(processed_text)

    def process_escapes(self, text):
        if not isinstance(text, str):
            return str(text)

        has_escape = any(char in text for char in ('\\n', '\\t', '\\r', '\\u', '\\\\'))
        if has_escape:
            try:
                text = text.encode('utf-8').decode('unicode_escape')
            except:
                pass
        else:
            text = text.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
            text = text.replace('\\"', '"').replace("\\'", "'")

        return text

class JsonTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
            }
            QTreeWidget::item {
                padding: 2px 0;
            }
            QTreeWidget::item:hover {
                background-color: #2A2A2A;
            }
            QTreeWidget::branch {
                background-color: #1E1E1E;
            }
            QTreeWidget::branch:has-siblings:!adjoins-item {
                border-image: url(vline) 0;
            }
            QTreeWidget::branch:has-siblings:adjoins-item {
                border-image: url(branch-more) 0;
            }
            QTreeWidget::branch:!has-children:!has-siblings:adjoins-item {
                border-image: url(branch-end) 0;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                image: url(branch-closed);
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                border-image: none;
                image: url(branch-open);
            }
        """)
        self.font = QFont("Consolas", 10)
        self.setFont(self.font)

        self.tooltip = CustomTooltip(self, self)
        self.tooltip.hide()
        self.current_item = None
        self.show_timer = QTimer()
        self.show_timer.setSingleShot(True)
        self.show_timer.timeout.connect(self.show_tooltip)
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.really_hide_tooltip)
        self.setMouseTracking(True)
        self.tooltip.installEventFilter(self)
        self._in_tooltip = False

    def set_in_tooltip(self, value):
        self._in_tooltip = value

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            if hasattr(self, 'tooltip') and obj == self.tooltip:
                self.cancel_hide()
                self.set_in_tooltip(True)
                return True
        elif event.type() == QEvent.Leave:
            if hasattr(self, 'tooltip') and obj == self.tooltip:
                self.set_in_tooltip(False)
                self.start_hide_timer()
                return True
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        if self._in_tooltip:
            return

        self.hide_timer.stop()
        item = self.itemAt(event.pos())

        if item:
            self.current_item = item
            self.show_timer.start(1000)
        else:
            self.current_item = None
            self.show_timer.stop()

        super().mouseMoveEvent(event)

    def show_tooltip(self):
        if self._in_tooltip:
            return

        if not self.current_item:
            return

        item_data = self.current_item.data(0, Qt.UserRole)
        if not item_data:
            return

        text = item_data.get('full_text', '')
        if not text:
            return

        self.tooltip.set_text(text)

        screen = QApplication.primaryScreen()
        screen_size = screen.availableGeometry()
        width = min(screen_size.width() // 2, 800)
        height = min(screen_size.height() // 2, 600)
        self.tooltip.setFixedSize(width, height)

        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 10
        y = cursor_pos.y() + 10

        if x + width > screen_size.width():
            x = cursor_pos.x() - width - 10

        if y + height > screen_size.height():
            y = cursor_pos.y() - height - 10

        self.tooltip.move(x, y)
        self.tooltip.show()
        self.tooltip.activateWindow()

    def start_hide_timer(self):
        if not hasattr(self, 'show_timer'):
            return
        self.show_timer.stop()
        self.hide_timer.start(500)

    def really_hide_tooltip(self):
        if hasattr(self, 'tooltip'):
            self.tooltip.hide()

    def cancel_hide(self):
        if hasattr(self, 'hide_timer'):
            self.hide_timer.stop()

    def build_tree(self, data, parent=None, key=""):
        if parent is None:
            parent = self.invisibleRootItem()

        if isinstance(data, dict):
            if key:
                item = QTreeWidgetItem(parent, [key])
                item.setForeground(0, QBrush(QColor("#FFC66D")))
                item.setData(0, Qt.UserRole, {'full_text': key})
                parent = item

            for k, v in data.items():
                self.build_tree(v, parent, str(k))

        elif isinstance(data, list):
            if key:
                item = QTreeWidgetItem(parent, [key])
                item.setForeground(0, QBrush(QColor("#FF6B6B")))
                item.setData(0, Qt.UserRole, {'full_text': key})
                parent = item

            for i, v in enumerate(data):
                self.build_tree(v, parent, f"[{i}]")

        else:
            full_value_str = str(data)
            display_str = full_value_str
            if len(display_str) > 80:
                display_str = display_str[:77] + "..."

            if key:
                item_text = f"{key}: {display_str}"
                full_text = f"{key}: {full_value_str}"
            else:
                item_text = display_str
                full_text = full_value_str

            item = QTreeWidgetItem(parent, [item_text])
            item.setData(0, Qt.UserRole, {'full_text': full_text})

            if isinstance(data, str):
                item.setForeground(0, QBrush(QColor("#6A9955")))
            elif isinstance(data, (int, float)):
                item.setForeground(0, QBrush(QColor("#B5CEA8")))
            elif isinstance(data, bool):
                item.setForeground(0, QBrush(QColor("#FF6B6B")))
            elif data is None:
                item.setForeground(0, QBrush(QColor("#808080")))

class SessionFlowWindow(QDialog):
    def __init__(self, sessions, parent=None):
        super().__init__(parent)
        self.sessions = sessions if isinstance(sessions, list) else [sessions]
        model_names = ", ".join(s.get('model', 'unknown') for s in self.sessions)
        self.setWindowTitle(f"会话详情 ({len(self.sessions)}条) - {model_names}")
        self.setMinimumSize(1200, 800)
        self.showMaximized()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.splitter.addWidget(self.left_panel)

        self.left_header = QLabel("请求 (req.json)")
        self.left_header.setStyleSheet("background-color: #0E639C; color: white; padding: 8px; font-weight: bold;")
        self.left_layout.addWidget(self.left_header)

        self.req_tree = JsonTreeWidget()
        self.left_layout.addWidget(self.req_tree)

        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.splitter.addWidget(self.right_panel)

        self.right_header = QLabel("响应 (resp.json)")
        self.right_header.setStyleSheet("background-color: #0E639C; color: white; padding: 8px; font-weight: bold;")
        self.right_layout.addWidget(self.right_header)

        self.resp_tree = JsonTreeWidget()
        self.right_layout.addWidget(self.resp_tree)

        self.splitter.setSizes([600, 600])

        self.load_session(0)

    def load_session(self, index=0):
        if not self.sessions:
            return

        config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
        session_num = index + 1

        req_path = os.path.join(config_dir, f"{session_num}-req.json")
        resp_path = os.path.join(config_dir, f"{session_num}-resp.json")

        self.req_tree.clear()
        if os.path.exists(req_path):
            try:
                with open(req_path, 'r', encoding='utf-8') as f:
                    req_data = json.load(f)
                self.req_tree.build_tree(req_data)
                self.req_tree.expandToDepth(2)
            except Exception as e:
                self.req_tree.clear()
                item = QTreeWidgetItem(self.req_tree.invisibleRootItem(), [f"加载失败: {str(e)}"])
                item.setForeground(0, QBrush(QColor("#FF6B6B")))
        else:
            item = QTreeWidgetItem(self.req_tree.invisibleRootItem(), ["req.json 文件不存在"])
            item.setForeground(0, QBrush(QColor("#FF6B6B")))

        self.resp_tree.clear()
        if os.path.exists(resp_path):
            try:
                with open(resp_path, 'r', encoding='utf-8') as f:
                    resp_data = json.load(f)
                self.resp_tree.build_tree(resp_data)
                self.resp_tree.expandToDepth(2)
            except Exception as e:
                self.resp_tree.clear()
                item = QTreeWidgetItem(self.resp_tree.invisibleRootItem(), [f"加载失败: {str(e)}"])
                item.setForeground(0, QBrush(QColor("#FF6B6B")))
        else:
            item = QTreeWidgetItem(self.resp_tree.invisibleRootItem(), ["resp.json 文件不存在"])
            item.setForeground(0, QBrush(QColor("#FF6B6B")))