# План реализации функционала ASS (Auto Segmentation System)

## Этап 1: Ребрендинг проекта (AIContour -> ASS)
- `client_app.py`, `server_app.py`:
  - Заголовки окон: "ASS (Auto Segmentation System) — Клиент / Сервер".
  - `AppUserModelID`: "ASS.AutoSegmentationSystem.1.0".
  - Мьютексы: "ASSClientMutex_1.0" и "ASSServerMutex_1.0".
- `build_clientPyQT5.py`, `build_clientPyQT6.py`, `.bat`:
  - Выходной исполняемый файл: `ASS_Client.exe`.
  - Дистрибутив: `ASS_Client_Portable`.
- `elekta_mod.py`:
  - AE Titles по умолчанию: `ASS_SCP`, `ASS_SCU`.
- `README.md`:
  - Обновление названия и описания.

## Этап 2: Сохранение IP-адреса и сетевая стабильность клиента
- `config/client_settings.ini`:
  - Обычный текстовый INI-файл в локальной папке `config/` на клиенте (не скрытый, доступный для ручной правки в Блокноте).
- `client_app.py`:
  - Привязать `self.server_url_edit.textChanged` к моментальному сохранению `server_url` в INI.
  - При клике на индикатор «Сервер: Недоступен 🔴» или кнопке ошибки открывать быстрое диалоговое окно смены IP без необходимости ввода пароля администратора.
  - При обрыве связи серверный адрес не сбрасывать, опрос продолжать в фоне.

## Этап 3: Синхронизация очереди (Read-Only для чужих задач)
- `client_app.py`:
  - В `on_status_received` убрать фильтр по `client_name` — отображать все задачи очереди с сервера.
  - Для задач текущего клиента добавить визуальное отличие (пометка `[Этот ПК]` или цветовое выделение).
  - Контекстное меню очереди и кнопки управления:
    - Запретить отмену чужих задач.
    - Отключать кнопку «Отменить задачу» для строк других клиентов.
    - Исключить любые действия изменения приоритетов и структуры очереди.

## Этап 4: Вынос папки temp на отдельный диск (RAM-диск)
- `server/server_api.py`, `server/queue_manager.py`, `contour_engine.py`:
  - Добавить параметр конфигурации `temp_dir` в `config/server_settings.ini`.
  - Если `temp_dir` задан и существует — создавать рабочие директории распаковки КТ, NIfTI и масок в нем. Если нет — использовать стандартный `tempfile.gettempdir()`.
  - Гарантированная очистка временных подпапок после завершения или сбоя задачи.

## Этап 5: Корректировка типа структуры `body` в RTSTRUCT
- `contour_engine.py`:
  - При вызове `rtstruct.add_roi()` для структуры `body` (и ее алиасов `Body`, `External`):
    - Явно устанавливать в `ds.RTROIObservationsSequence[-1].RTROIInterpretedType = "EXTERNAL"`.
    - Устанавливать дескриптор `ROIObservationDescription` с указанием типа тела (`Type:Body`).
  - Проверить сохранение в `pydicom` для станций Elekta Monaco, Eclipse, RayStation.

## Этап 6: Тестирование и документация
- Запуск тестов `tests/test_*.py`.
- Фиксация изменений в `CHANGELOG.md` и `.agent/docs/ARCHIVE.md`.
