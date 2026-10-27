#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль splash.py: Премиальный сплэш-скрин загрузки для Auto Segmentation System (ASS)
Поддерживает работу как в PyQt6, так и в PyQt5.
"""

import os
from pathlib import Path

def create_splash_screen(app, is_server: bool = False):
    """
    Создает и отображает стильный сплэш-скрин загрузки программы.
    Возвращает экземпляр ModernSplashScreen.
    """
    # Определяем доступный Qt (PyQt6 или PyQt5)
    try:
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap, QFont, QColor
        is_pyqt6 = True
    except ImportError:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QPixmap, QFont, QColor
        is_pyqt6 = False

    class ModernSplashScreen(QWidget):
        def __init__(self):
            super().__init__()
            # Настройка окна: без рамок, поверх остальных окон
            flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint if is_pyqt6 else (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground if is_pyqt6 else Qt.WA_TranslucentBackground, True)
            
            self.setFixedSize(480, 320)
            
            # Корневой контейнер с закругленными углами и тенью
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            
            container = QWidget(self)
            container.setObjectName("splashContainer")
            container.setStyleSheet("""
                QWidget#splashContainer {
                    background-color: #18181c;
                    border: 1px solid #33333a;
                    border-radius: 12px;
                }
            """)
            layout.addWidget(container)
            
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(25, 25, 25, 20)
            c_layout.setSpacing(10)
            
            # Логотип
            self.logo_label = QLabel()
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            
            # Ищем соответствующую иконку (сервер или клиент)
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
                    self.logo_label.setPixmap(pix.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatio if is_pyqt6 else Qt.KeepAspectRatio, transform_mode))
            
            c_layout.addWidget(self.logo_label)
            
            # Заголовок
            title_label = QLabel("Auto Segmentation System")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            title_font = QFont("Segoe UI", 16, QFont.Weight.Bold if is_pyqt6 else QFont.Bold)
            title_label.setFont(title_font)
            title_label.setStyleSheet("color: #ffffff; margin-top: 2px;")
            c_layout.addWidget(title_label)
            
            # Подзаголовок режима
            mode_text = "[Сервер]" if is_server else "[Клиент]"
            mode_color = "#00ffd0" if not is_server else "#00bcd4"
            mode_label = QLabel(mode_text)
            mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            mode_font = QFont("Segoe UI", 11, QFont.Weight.DemiBold if is_pyqt6 else 63)
            mode_label.setFont(mode_font)
            mode_label.setStyleSheet(f"color: {mode_color};")
            c_layout.addWidget(mode_label)
            
            c_layout.addStretch()
            
            # Текст текущего статуса загрузки
            self.status_label = QLabel("Запуск компонентов системы...")
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            self.status_label.setStyleSheet("color: #9999a5; font-size: 11px;")
            c_layout.addWidget(self.status_label)
            
            # Прогресс-бар
            self.progress_bar = QProgressBar()
            self.progress_bar.setFixedHeight(6)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(10)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #23232a;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #00ffd0);
                    border-radius: 3px;
                }
            """)
            c_layout.addWidget(self.progress_bar)
            
            # Центрирование на экране
            self.center_on_screen(app)

        def center_on_screen(self, qapp):
            screen = qapp.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                x = (geom.width() - self.width()) // 2 + geom.x()
                y = (geom.height() - self.height()) // 2 + geom.y()
                self.move(x, y)

        def set_progress(self, value: int, message: str = ""):
            """Обновляет значение прогресс-бара и поясняющий текст."""
            self.progress_bar.setValue(value)
            if message:
                self.status_label.setText(message)
            app.processEvents()

        def finish(self, main_window):
            """Закрывает заставку и передает фокус главному окну."""
            main_window.show()
            self.close()

    splash = ModernSplashScreen()
    splash.show()
    app.processEvents()
    return splash
