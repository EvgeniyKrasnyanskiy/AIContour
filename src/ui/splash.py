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
            
            # Компактный размер точно под крупную иконку (360x360) + прогресс-бар
            self.setFixedSize(384, 412)
            
            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(0)
            
            container = QWidget(self)
            container.setObjectName("splashCard")
            container.setStyleSheet("""
                QWidget#splashCard {
                    background-color: #151518;
                    border: 1px solid #2d2d35;
                    border-radius: 16px;
                }
            """)
            layout.addWidget(container)
            
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(10, 10, 10, 10)
            c_layout.setSpacing(8)
            
            # Большая иконка приложения
            self.logo_label = QLabel()
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            self.logo_label.setFixedSize(352, 352)
            
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
                    self.logo_label.setPixmap(pix.scaled(350, 350, Qt.AspectRatioMode.KeepAspectRatio if is_pyqt6 else Qt.KeepAspectRatio, transform_mode))
            
            c_layout.addWidget(self.logo_label)
            
            # Тонкий аккуратный прогресс-бар точно под иконкой
            self.progress_bar = QProgressBar()
            self.progress_bar.setFixedHeight(6)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(10)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #24242c;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #00ffd0);
                    border-radius: 3px;
                }
            """)
            c_layout.addWidget(self.progress_bar)

            # Текст статуса (лаконичный, прямо под полосой прогресса)
            self.status_label = QLabel("Загрузка...")
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter if is_pyqt6 else Qt.AlignCenter)
            self.status_label.setStyleSheet("color: #888899; font-size: 11px; margin-top: 2px;")
            c_layout.addWidget(self.status_label)
            
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
            """Отображает главное окно, ждет отрисовки и плавно закрывает сплэш-скрин."""
            main_window.showMaximized()
            main_window.raise_()
            main_window.activateWindow()
            app.processEvents()
            # Даем окну полностью завершить рендеринг виджетов перед скрытием заставки
            QTimer.singleShot(450, self.close)

    splash = ModernSplashScreen()
    splash.show()
    app.processEvents()
    return splash
