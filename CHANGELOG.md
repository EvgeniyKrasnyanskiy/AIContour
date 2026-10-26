# Changelog

Все заметные изменения в проекте ASS (Auto Segmentation System) фиксируются в данном файле.
Формат соответствует [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

## [Unreleased]
### Added
- **Единая очередь на клиенте:** клиент отображает полный список задач с сервера; задачи текущего клиента визуально выделяются (`[Этот ПК]`), чужие задачи защищены от отмены и модификации (режим «только чтение»).
- **Мгновенное сохранение IP и удобная настройка:** поле адреса сервера моментально синхронизируется в обычный текстовый файл `config/client_settings.ini`; добавлен быстрый диалог настройки сетевого IP по клику на индикатор статуса сервера.
- **Поддержка кастомной папки `temp_dir`:** возможность выноса промежуточной обработки КТ и архивов на выделенный диск или RAM-диск (например, `R:\temp`) на сервере и клиенте.
- **Корректная классификация `body` в DICOM RTSTRUCT:** теги `RTROIInterpretedType = "BODY"` и `ROIObservationDescription = "Type:Body,..."` для корректного отображения тела как Body (а не OAR/External) на станциях планирования Monaco, Eclipse и др.
- Модульные тесты `tests/test_body_structure_type.py` для валидации генерации RTSTRUCT и конфигурации путей.
- Базовая документация: [ROADMAP.md](.agent/docs/ROADMAP.md), [ARCHIVE.md](.agent/docs/ARCHIVE.md), [IMPLEMENTATION_PLAN.md](.agent/docs/IMPLEMENTATION_PLAN.md).

### Changed
- **Ребрендинг проекта:** полный переход с AIContour на **ASS (Auto Segmentation System)** (заголовки окон, AppUserModelID, системные мьютексы, сборщики `ASS_Client.exe`, дистрибутивы `ASS_Client_Portable.zip`, DICOM AE Titles `ASS_SCP` / `ASS_SCU`).
