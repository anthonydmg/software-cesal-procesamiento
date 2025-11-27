import sys
import os
import json
import datetime
from pathlib import Path
from PySide6.QtCore import QStandardPaths

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QListWidget, QFileDialog, QLabel, QMessageBox
)

APP_NAME = "AgroHass"
ORG_NAME = "Inicteluni"

class AppDataManager():
    def __init__(self, app_name = APP_NAME, org_name = ORG_NAME):
        self.app_name = app_name
        self.org_name = org_name
    
    def get_config_path(self):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        return os.path.join(config_dir, "recent_projects.json")
    
    def load_recent_projects(self):
        config_path = self.get_config_path()
        if os.path.exists(config_path):
            with open(config_path,  "r") as f:
                return json.load(f)
        return []
    
    def save_recent_projects(self, projects):
        config_path = self.get_config_path()
        with open(config_path, "w") as f:
            json.dump(projects, f, indent = 4)

#save_recent_projects({})