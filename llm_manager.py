from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QLineEdit, QComboBox, QLabel, QTextEdit,
                             QMessageBox, QDialogButtonBox, QGroupBox, QFormLayout)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPalette
from config import load_llm_profiles, save_llm_profiles
import requests

class LLMProfile:
    def __init__(self, name="", provider="openai", base_url="", api_key="", model=""):
        self.name = name
        self.provider = provider
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def to_dict(self):
        return {
            "name": self.name,
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model
        }

    @staticmethod
    def from_dict(d):
        return LLMProfile(
            d.get("name", ""),
            d.get("provider", "openai"),
            d.get("base_url", ""),
            d.get("api_key", ""),
            d.get("model", "")
        )

class LLMManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("大模型管理")
        self.setMinimumSize(700, 500)
        self.profiles = [LLMProfile.from_dict(p) for p in load_llm_profiles()]
        self.selected_profile = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["名称", "供应商", "Base URL", "模型", "API Key"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.on_edit_profile)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加")
        self.add_btn.clicked.connect(self.on_add_profile)
        self.edit_btn = QPushButton("编辑")
        self.edit_btn.clicked.connect(self.on_edit_current)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self.on_delete_profile)
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self.on_test_connection)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.test_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(len(self.profiles))
        for i, p in enumerate(self.profiles):
            self.table.setItem(i, 0, QTableWidgetItem(p.name))
            self.table.setItem(i, 1, QTableWidgetItem(p.provider))
            self.table.setItem(i, 2, QTableWidgetItem(p.base_url))
            self.table.setItem(i, 3, QTableWidgetItem(p.model))
            self.table.setItem(i, 4, QTableWidgetItem("*" * 8 + p.api_key[-4:] if len(p.api_key) > 4 else ""))

    def on_add_profile(self):
        dlg = LLMProfileEditDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self.profiles.append(dlg.get_profile())
            self.refresh_table()

    def on_edit_profile(self, item):
        row = item.row()
        self.edit_row(row)

    def on_edit_current(self):
        row = self.table.currentRow()
        if row >= 0:
            self.edit_row(row)

    def edit_row(self, row):
        profile = self.profiles[row]
        dlg = LLMProfileEditDialog(self, profile)
        if dlg.exec_() == QDialog.Accepted:
            self.profiles[row] = dlg.get_profile()
            self.refresh_table()

    def on_delete_profile(self):
        row = self.table.currentRow()
        if row >= 0:
            reply = QMessageBox.question(self, "确认", "确定要删除这个配置吗?",
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.profiles.pop(row)
                self.refresh_table()

    def on_test_connection(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一个配置")
            return

        profile = self.profiles[row]
        
        if not profile.base_url:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return

        self.test_connection(profile)

    def test_connection(self, profile):
        base_url = profile.base_url.strip()
        api_key = profile.api_key.strip()

        try:
            url = f"{base_url.rstrip('/')}/models"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                model_count = 0
                if "data" in data:
                    model_count = len(data["data"])
                elif isinstance(data, list):
                    model_count = len(data)
                
                if model_count > 0:
                    QMessageBox.information(self, "测试成功", 
                        f"连接成功！\nURL: {base_url}\n可用模型数: {model_count}")
                else:
                    QMessageBox.information(self, "测试成功", 
                        f"连接成功！\nURL: {base_url}\n但未找到可用模型")
            else:
                QMessageBox.warning(self, "测试失败", 
                    f"请求失败\n状态码: {response.status_code}\n错误: {response.text}")

        except requests.exceptions.ConnectionError:
            QMessageBox.warning(self, "测试失败", 
                f"无法连接到服务器\n{base_url}\n请检查网络连接或URL是否正确")
        except requests.exceptions.Timeout:
            QMessageBox.warning(self, "测试失败", "请求超时，请检查网络连接")
        except Exception as e:
            QMessageBox.warning(self, "测试失败", f"连接出错: {str(e)}")

    def on_accept(self):
        save_llm_profiles([p.to_dict() for p in self.profiles])
        self.accept()

    def get_selected_profile(self):
        row = self.table.currentRow()
        if row >= 0:
            return self.profiles[row]
        return None

    def get_profiles(self):
        return self.profiles

class LLMProfileEditDialog(QDialog):
    PROVIDERS = ["openai", "anthropic", "ollama", "azure", "custom"]

    def __init__(self, parent=None, profile=None):
        super().__init__(parent)
        self.profile = profile or LLMProfile()
        self.setWindowTitle("编辑大模型配置" if profile else "添加大模型配置")
        self.setMinimumWidth(500)
        self.init_ui()
        self.models_fetched = False

    def init_ui(self):
        layout = QFormLayout(self)

        self.name_edit = QLineEdit(self.profile.name)
        layout.addRow("名称:", self.name_edit)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self.PROVIDERS)
        if self.profile.provider in self.PROVIDERS:
            self.provider_combo.setCurrentText(self.profile.provider)
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        layout.addRow("供应商:", self.provider_combo)

        self.base_url_edit = QLineEdit(self.profile.base_url)
        layout.addRow("Base URL:", self.base_url_edit)

        self.api_key_edit = QLineEdit(self.profile.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("API Key:", self.api_key_edit)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setCurrentText(self.profile.model)
        self.model_combo.view().pressed.connect(self.on_model_highlighted)
        self.model_combo.showPopup = self.on_show_popup
        layout.addRow("模型:", self.model_combo)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addRow("", self.status_label)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.on_provider_changed(self.provider_combo.currentText())

    def on_provider_changed(self, provider):
        presets = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com",
            "ollama": "http://localhost:11434/v1",
            "azure": "https://YOUR_RESOURCE.openai.azure.com"
        }
        if self.base_url_edit.text() == "" or self.base_url_edit.text() in presets.values():
            self.base_url_edit.setText(presets.get(provider, ""))
        self.models_fetched = False

    def on_model_highlighted(self, index):
        if not self.models_fetched:
            self.fetch_models()

    def on_show_popup(self):
        if not self.models_fetched:
            self.fetch_models()
        QComboBox.showPopup(self.model_combo)

    def fetch_models(self):
        base_url = self.base_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()

        if not base_url:
            self.status_label.setText("请先填写 Base URL")
            return

        self.status_label.setText("正在获取模型列表...")

        try:
            url = f"{base_url.rstrip('/')}/models"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            models = []

            if "data" in data:
                for item in data["data"]:
                    if isinstance(item, dict) and "id" in item:
                        models.append(item["id"])
                    elif isinstance(item, str):
                        models.append(item)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "id" in item:
                        models.append(item["id"])
                    elif isinstance(item, str):
                        models.append(item)

            if models:
                self.model_combo.clear()
                self.model_combo.addItems(models)
                self.status_label.setText(f"已获取 {len(models)} 个模型")
            else:
                self.status_label.setText("未找到可用模型")

        except Exception as e:
            self.status_label.setText(f"获取失败: {str(e)}")

        self.models_fetched = True

    def get_profile(self):
        self.profile.name = self.name_edit.text()
        self.profile.provider = self.provider_combo.currentText()
        self.profile.base_url = self.base_url_edit.text()
        self.profile.api_key = self.api_key_edit.text()
        self.profile.model = self.model_combo.currentText()
        return self.profile