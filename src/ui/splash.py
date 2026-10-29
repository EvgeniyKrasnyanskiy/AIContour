#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль splash.py: Компактный сплэш-скрин загрузки для Auto Segmentation System (ASS).
Отображает крупную иконку приложения и прогресс-бар непосредственно под ней без лишних рамок.
Поддерживает работу как в PyQt6, так и в PyQt5.
"""

import os
from pathlib import Path

def create_splash_screen(app, is_server: bool = False):
    """
    Создает и отображает крупную иконку со шкалой загрузки снизу.
    Возвращает экземпляр ModernSplashScreen.
    """
    try:
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QPixmap, QFont
        is_pyqt6 = True
    except ImportError:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
        from PyQt5.QtCore import Qt, QTimer
        from PyQt5.QtGui import QPixmap, QFont
        is_pyqt6 = False

    class ModernSplashScreen(QWidget):
        def __init__(self):
            super().__init__()
            flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint if is_pyqt6 else (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground if is_pyqt6 else Qt.WA_TranslucentBackground, True)
            
            # Увеличенный в 1.5 раза размер под крупную иконку (528x528) + прогресс-бар 500px без черных рамок
            self.setFixedSize(576, 590)
            
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            
            container = QWidget(self)
            container.setObjectName("splashCard")
            container.setStyleSheet("""
                QWidget#splashCard {
                    background: transparent;
                    border: none;
                }
            """)
            layout.addWidget(container)
            
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(0, 0, 0, 0)
            c_layout.setSpacing(8)
            c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            
            # Большая иконка приложения (в 1.5 раза крупнее: 528x528)
            self.logo_label = QLabel()
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            self.logo_label.setFixedSize(528, 528)
            
            base_dir = Path(__file__).resolve().parent.parent.parent
            icon_file = "icon_server.png" if is_server else "icon_client.png"
            icon_path = base_dir / icon_file
            if not icon_path.exists():
                icon_path = base_dir / ("icon_server.jpg" if is_server else "icon_client.jpg")
            if not icon_path.exists():
                icon_path = base_dir / "app_icon.png"
                
            if icon_path.exists():
                pix = QPixmap(str(icon_path))
                if not pix.isNull():
                    transform_mode = Qt.TransformationMode.SmoothTransformation if is_pyqt6 else Qt.SmoothTransformation
                    self.logo_label.setPixmap(pix.scaled(525, 525, Qt.AspectRatioMode.KeepAspectRatio if is_pyqt6 else Qt.KeepAspectRatio, transform_mode))
            
            c_layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            
            # Тонкий аккуратный прогресс-бар шириной 500px точно под иконкой
            self.progress_bar = QProgressBar()
            self.progress_bar.setFixedHeight(8)
            self.progress_bar.setFixedWidth(500)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(10)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #24242c;
                    border: none;
                    border-radius: 4px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #00ffd0);
                    border-radius: 4px;
                }
            """)
            c_layout.addWidget(self.progress_bar, 0, Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)

            # Текст статуса (лаконичный, шрифт 11px без изменений)
            self.status_label = QLabel("Загрузка...")
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            self.status_label.setStyleSheet("color: #888899; font-size: 11px; margin-top: 2px;")
            c_layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            
            self.center_on_screen(app)

        def center_on_screen(self, qapp):
            screen = qapp.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                x = (geom.width() - self.width()) // 2 + geom.x()
                y = (geom.height() - self.height()) // 2 + geom.y()
                self.move(x, y)

        def set_progress(self, value: int, message: str = ""):
            """Обновляет значение прогресс-бара и статус загрузки."""
            self.progress_bar.setValue(value)
            if message:
                self.status_label.setText(message)
            app.processEvents()

        def finish(self, main_window):
            """Отображает главное окно и закрывает сплэш-скрин."""
            main_window.showMaximized()
            main_window.raise_()
            main_window.activateWindow()
            app.processEvents()
            self.hide()
            self.close()

    splash = ModernSplashScreen()
    splash.show()
    app.processEvents()
    return splash
