#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для сборки автономного Windows-клиента (.exe) для AI Contour.
Скрипт автоматически:
1. Устанавливает PyInstaller и Pillow во внутренний venv (если они не установлены).
2. Конвертирует png-иконку в ico-формат.
3. Компилирует клиент с полным исключением тяжелых ML библиотек (torch, totalsegmentator и т.д.).
4. Формирует готовую переносимую сборку в ZIP-архив с сохранением структуры настроек.
"""

import os
import sys
import subprocess
import shutil
import zipfile
from pathlib import Path

def print_banner(text):
    print("\n" + "=" * 80)
    print(f" {text}")
    print("=" * 80 + "\n")

def check_and_install_dependencies():
    print_banner("1. Проверка и установка сборочных зависимостей")
    
    # Чтобы избежать ошибки "Fatal error in launcher: Unable to create process" из-за жестких путей к python.exe внутри pip.exe (например, после перемещения проекта),
    # мы запускаем pip через интерпретатор python: "python.exe -m pip"
    venv_python = Path("venv") / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = "python"
        print("[WARNING] venv/Scripts/python.exe не найден! Будет использован глобальный python.")
        pip_cmd = ["python", "-m", "pip"]
    else:
        venv_python = str(venv_python)
        print(f"[INFO] Обнаружен python в виртуальном окружении: {venv_python}")
        pip_cmd = [venv_python, "-m", "pip"]
        
    def install_with_fallbacks(package_name):
        """Пытается установить пакет через pip, поочередно пробуя различные зеркала PyPI в случае сбоя."""
        print(f"[INFO] Попытка установки {package_name} через официальный PyPI...")
        try:
            subprocess.check_call(pip_cmd + ["install", package_name])
            print(f"[OK] {package_name} успешно установлен.")
            return True
        except subprocess.CalledProcessError:
            print(f"[WARNING] Не удалось установить {package_name} через официальный PyPI.")

        # Альтернативные зеркала в заданном порядке приоритета
        mirrors = [
            ("Tsinghua University (Китай)", "https://pypi.tuna.tsinghua.edu.cn/simple"),
            ("Douban (Китай)", "https://pypi.doubanio.com/simple"),
            ("Яндекс (Россия)", "https://pypi.yandex.ru/simple")
        ]

        for name, url in mirrors:
            print(f"[INFO] Попытка установки {package_name} через зеркало {name} ({url})...")
            try:
                host = url.split("//")[1].split("/")[0]
                subprocess.check_call(pip_cmd + [
                    "install", package_name, 
                    "--index-url", url, 
                    "--trusted-host", host
                ])
                print(f"[OK] {package_name} успешно установлен через зеркало {name}!")
                return True
            except subprocess.CalledProcessError:
                print(f"[WARNING] Не удалось установить {package_name} через зеркало {name}.")

        raise RuntimeError(f"Критическая ошибка: Не удалось установить пакет {package_name} ни из одного источника.")

    try:
        # Проверяем pyinstaller
        import pyinstaller
        print("[OK] PyInstaller уже установлен.")
    except ImportError:
        print("[INFO] PyInstaller не найден. Запуск установки...")
        install_with_fallbacks("pyinstaller")
        
    try:
        # Проверяем pillow (нужен для генерации иконки)
        from PIL import Image
        print("[OK] Pillow уже установлен.")
    except ImportError:
        print("[INFO] Pillow не найден. Запуск установки для конвертации иконки...")
        install_with_fallbacks("pillow")

def generate_ico_icon():
    print_banner("2. Генерация иконки приложения")
    png_path = Path("app_icon.png")
    ico_path = Path("app_icon.ico")
    
    if not png_path.exists():
        print(f"[WARNING] Файл {png_path} не найден! Сборка будет выполнена со стандартной иконкой.")
        return False
        
    try:
        from PIL import Image
        print(f"[INFO] Конвертируем {png_path} в {ico_path}...")
        img = Image.open(png_path)
        
        # Windows ico поддерживает несколько разрешений
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_path, format="ICO", sizes=sizes)
        print(f"[OK] Иконка {ico_path} успешно сгенерирована.")
        return True
    except Exception as e:
        print(f"[WARNING] Ошибка генерации иконки: {e}. Сборка продолжится со стандартной иконкой.")
        return False

def build_executable(has_icon):
    print_banner("3. Запуск компиляции через PyInstaller")
    
    # Путь к pyinstaller.exe в venv
    pyinstaller_bin = Path("venv") / "Scripts" / "pyinstaller.exe"
    if not pyinstaller_bin.exists():
        pyinstaller_bin = "pyinstaller"
        print("[WARNING] venv/Scripts/pyinstaller.exe не найден! Будет использован глобальный pyinstaller.")
    else:
        pyinstaller_bin = str(pyinstaller_bin)
        print(f"[INFO] Обнаружен PyInstaller в venv: {pyinstaller_bin}")
        
    # Формируем аргументы
    args = [
        pyinstaller_bin,
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--add-data=app_icon.png;.",
        "--add-data=version.txt;.",
        "--name=AIContourClient",
    ]
    
    # Добавляем системные библиотеки VC++ Redistributable и ICU для портативности на чистых Windows системах
    system32_path = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
    required_dlls = [
        "vcruntime140.dll", 
        "vcruntime140_1.dll",
        "vcruntime140_threads.dll",
        "msvcp140.dll", 
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll",
        "msvcp140_codecvt_ids.dll",
        "concrt140.dll",
        "vcomp140.dll",
        "icu.dll",
        "icuin.dll",
        "icuuc.dll"
    ]
    for dll in required_dlls:
        dll_filepath = system32_path / dll
        if dll_filepath.exists():
            print(f"[INFO] Добавляем системную DLL в сборку: {dll}")
            # Добавляем и в корень (для основного приложения), и в папку Qt (для бинарников PyQt6)
            args.append(f"--add-binary={dll_filepath};.")
            args.append(f"--add-binary={dll_filepath};PyQt6/Qt6/bin")
        else:
            print(f"[WARNING] Системная DLL {dll} не найдена в {system32_path}!")

    # Добавляем иконку, если создана
    if has_icon:
        args.append("--icon=app_icon.ico")
        
    # ДОБАВЛЯЕМ СКРЫТЫЕ ИМПОРТЫ ДЛЯ PYDICOM, PYNETDICOM И PYQTGRAPH
    try:
        from PyInstaller.utils.hooks import collect_submodules
        pydicom_subs = collect_submodules('pydicom')
        pynetdicom_subs = collect_submodules('pynetdicom')
        pyqtgraph_subs = collect_submodules('pyqtgraph')
        print(f"[INFO] Собрано {len(pydicom_subs)} подмодулей pydicom, {len(pynetdicom_subs)} pynetdicom и {len(pyqtgraph_subs)} pyqtgraph.")
        for m in pydicom_subs + pynetdicom_subs + pyqtgraph_subs:
            args.append(f"--hidden-import={m}")
    except Exception as e:
        print(f"[WARNING] Не удалось автоматически собрать подмодули: {e}. Используем базовые hidden-imports.")
        args.append("--hidden-import=pydicom")
        args.append("--hidden-import=pynetdicom")
        args.append("--hidden-import=pyqtgraph")

    # ИСКЛЮЧАЕМ ТЯЖЕЛЫЕ БИБЛИОТЕКИ СЕРВЕРА
    # Это ключевой момент, чтобы клиент весил 50МБ, а не 3ГБ!
    heavy_excludes = [
        "torch", "torchvision", "torchaudio", 
        "totalsegmentator", "SimpleITK", "nibabel", 
        "matplotlib", "pandas", "h5py", "scipy",
        "contour_engine" # движок тоже исключаем, клиент работает только по сети через API
    ]
    for m in heavy_excludes:
        args.append(f"--exclude-module={m}")
        
    # Основной файл запуска
    args.append("client_app.py")
    
    print(f"[INFO] Выполняется команда сборки:\n{' '.join(args)}")
    subprocess.check_call(args)
    print("[OK] Компиляция .exe успешно завершена.")

def package_portable_zip():
    print_banner("4. Подготовка переносимого (Portable) ZIP-дистрибутива")
    
    dist_dir = Path("dist")
    exe_file = dist_dir / "AIContourClient.exe"
    config_src = Path("config")
    
    if not exe_file.exists():
        raise RuntimeError(f"[ERROR] Собранный файл {exe_file} не найден!")
        
    # Создаем временную структуру для упаковки
    package_dir = dist_dir / "AIContourClient_Portable"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Копируем исполняемый файл
    print(f"[INFO] Копируем {exe_file.name} в портативный каталог...")
    shutil.copy2(exe_file, package_dir / exe_file.name)
    
    # Копируем системные DLL прямо в портативную папку рядом с .exe для обхода приоритета DLL в System32 (Local Deployment)
    print("[INFO] Копируем системные DLL (MSVC++ и ICU) рядом с .exe для обхода приоритета System32...")
    system32_path = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
    required_dlls = [
        "vcruntime140.dll", 
        "vcruntime140_1.dll",
        "vcruntime140_threads.dll",
        "msvcp140.dll", 
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll",
        "msvcp140_codecvt_ids.dll",
        "concrt140.dll",
        "vcomp140.dll",
        "icu.dll",
        "icuin.dll",
        "icuuc.dll"
    ]
    for dll in required_dlls:
        dll_filepath = system32_path / dll
        if dll_filepath.exists():
            print(f"[INFO] Копируем DLL в портативный каталог: {dll}")
            shutil.copy2(dll_filepath, package_dir / dll)
        else:
            print(f"[WARNING] DLL {dll} не найдена в {system32_path}!")
            
    # Копируем opengl32sw.dll из venv прямо в портативную папку для софтверного рендеринга на серверах/RDP
    venv_opengl = Path("venv") / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin" / "opengl32sw.dll"
    if venv_opengl.exists():
        print(f"[INFO] Копируем {venv_opengl.name} в портативный каталог...")
        shutil.copy2(venv_opengl, package_dir / venv_opengl.name)
    else:
        print("[WARNING] opengl32sw.dll не найден в venv!")
    
    # 2. Исключаем копирование папки config/, так как клиент получает настройки с сервера.
    # Если на клиенте потребуется записать статистику, StatisticsManager создаст config/ автоматически.
    print("[INFO] Пропуск копирования папки config/ (все настройки запрашиваются с сервера).")
        
    # 3. Исключено создание README_portable.txt по требованию пользователя
    pass
        
    # 4. Упаковываем все в ZIP
    zip_filename = dist_dir / "AIContourClient_Portable.zip"
    if zip_filename.exists():
        zip_filename.unlink()
        
    print(f"[INFO] Упаковка в архив {zip_filename.name}...")
    with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zip_f:
        for root, dirs, files in os.walk(package_dir):
            for file in files:
                file_path = Path(root) / file
                # Сохраняем относительный путь внутри архива
                arcname = file_path.relative_to(package_dir)
                zip_f.write(file_path, arcname)
                
    # Очищаем временную папку
    shutil.rmtree(package_dir)
    
    print(f"[OK] Портативный ZIP-архив успешно создан: {zip_filename.resolve()}")
    print(f"Размер архива: {round(zip_filename.stat().st_size / (1024 * 1024), 2)} МБ")

def increment_version():
    print_banner("0. Обновление версии клиента")
    version_file = Path("version.txt")
    current_version = "2.0.0"
    
    if version_file.exists():
        try:
            current_version = version_file.read_text(encoding="utf-8").strip()
        except Exception as e:
            print(f"[WARNING] Не удалось прочитать version.txt: {e}. Будет использована версия 2.0.0")
            
    # Разбираем версию
    try:
        parts = current_version.split(".")
        if len(parts) == 3:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            patch += 1
            new_version = f"{major}.{minor}.{patch}"
        else:
            new_version = "2.0.1"
    except Exception:
        new_version = "2.0.1"
        
    try:
        version_file.write_text(new_version, encoding="utf-8")
        print(f"[OK] Версия обновлена: {current_version} -> {new_version}")
        return new_version
    except Exception as e:
        print(f"[ERROR] Не удалось сохранить новую версию в version.txt: {e}")
        return current_version

def patch_qt6_dll():
    print_banner("2.5. Патч Qt6Core.dll для совместимости с Windows Server 2016 / старыми Windows 10")
    
    # Путь к Qt6Core.dll во внутреннем venv
    dll_path = Path("venv") / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin" / "Qt6Core.dll"
    if not dll_path.exists():
        print("[WARNING] Qt6Core.dll не найден по стандартному пути. Пропуск патча.")
        return
        
    try:
        # Читаем бинарные данные
        data = dll_path.read_bytes()
        
        # Сигнатура вызова SetThreadDescription в kernel32.dll
        target = b"SetThreadDescription\x00"
        # Заменяем на SetThreadPriority (которая есть во всех версиях Windows и имеет такую же сигнатуру по регистрам)
        # Дополняем нулями до такой же длины (21 байт), чтобы не нарушить структуру PE-файла
        replacement = b"SetThreadPriority\x00\x00\x00\x00"
        
        if target in data:
            print("[INFO] Применяем патч к Qt6Core.dll (SetThreadDescription -> SetThreadPriority)...")
            # Создаем бэкап
            backup_path = dll_path.with_suffix(".dll.bak")
            if not backup_path.exists():
                shutil.copy2(dll_path, backup_path)
                print(f"[OK] Создан бэкап: {backup_path.name}")
                
            new_data = data.replace(target, replacement)
            dll_path.write_bytes(new_data)
            print("[OK] Qt6Core.dll успешно пропатчена для поддержки старых ОС!")
        else:
            # Возможно, уже пропатчена
            if b"SetThreadPriority\x00\x00\x00\x00" in data:
                print("[INFO] Qt6Core.dll уже содержит патч.")
            else:
                print("[WARNING] Не найдена сигнатура SetThreadDescription в Qt6Core.dll. Возможно, версия Qt изменена.")
    except Exception as e:
        print(f"[ERROR] Не удалось применить патч к Qt6Core.dll: {e}")

def main():
    try:
        # Убедимся, что рабочая директория — это корень проекта
        os.chdir(Path(__file__).parent.resolve())
        
        # Обновляем версию клиента
        increment_version()
        
        check_and_install_dependencies()
        
        # Применяем патч совместимости с Windows Server 2016 / старыми Windows 10
        patch_qt6_dll()
        
        has_icon = generate_ico_icon()
        build_executable(has_icon)
        package_portable_zip()
        
        print_banner("СБОРКА УСПЕШНО ВЫПОЛНЕНА! ДИСТРИБУТИВ В ПАПКЕ dist/")
        
    except Exception as e:
        print(f"\n[FATAL ERROR] Произошел критический сбой при сборке: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
