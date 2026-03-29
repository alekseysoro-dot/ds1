# Changelog

Формат: `[дата] | [тип] | суть | что сделано | результат`
Типы: `баг` | `доработка` | `настройка` | `вопрос` | `инфраструктура` | `деплой`

---

## 2026-03-23

- `[доработка]` | Брейншторм по новому ТЗ (vision) | Изучён текущий price-parser.html, запущен визуальный компаньон; выбран активный маркетплейс WB; показан выбор UI для импорта CSV/фид | Пользователь выбрал импорт через фид (URL)
- `[вопрос]` | Выбор стратегии разработки | Предложены варианты: переделать существующий файл или писать с нуля | Выбран вариант А (рефактор существующего)
- `[доработка]` | Рефактор price-parser.html под новое ТЗ | Новый дизайн киберминимализм (#0a0a0f, #00f5ff, JetBrains Mono); WB единственный активный маркетплейс; импорт через фид; история цен 180 дней; рабочие быстрые фильтры; Email+TG в настройках; экспорт в CSV/Excel; сохранение товаров в localStorage; динамические статистики | Готово
- `[вопрос]` | Деплой через GitHub + Vercel | Объяснён пошаговый процесс: создание репо → upload файла → подключение Vercel → автодеплой | Уточняется: деплоить только price-parser.html или весь проект
- `[вопрос]` | Не видна кнопка Add file на GitHub | Объяснено: в пустом репо ищи ссылку "uploading an existing file"; альтернатива — git push через терминал | Пользователь нашёл ссылку на репо: https://github.com/alekseysoro-dot/parsernew.git
- `[деплой]` | Подключение локального репо к GitHub | Выданы команды: git remote add origin + git push -u origin main; объяснена авторизация через Personal Access Token | Ожидается выполнение пользователем
- `[деплой]` | Пуш на GitHub в репо parsernew | origin уже занят (ds1.git); добавлен remote parsernew; закоммичены файлы reverens; выполнен push -u parsernew main | Успешно — код на GitHub. Vercel: Root Directory = reverens, URL будет /price-parser.html
- `[деплой]` | Vercel не видит репозиторий parsernew | Залогинен через GitHub, но нет доступа к репо; инструкция: github.com/settings/installations → Vercel → Configure → All repositories → Save | Ожидается результат

## 2026-03-25

- `[доработка]` | Task 9 — модуль уведомлений Email + Telegram | Созданы scraper/notifier.py (send_email, send_telegram, notify_if_needed) и tests/scraper/test_notifier.py с 4 тестами + моком settings | 27/27 тестов прошли, коммит feature/backend-api 7f769b7
- `[доработка]` | Task 10 — планировщик, Playwright fallback, Dockerfile для scraper | Созданы scraper/wb_scraper.py (headless Chromium), scraper/scheduler.py (APScheduler, обновление каждые 3ч, очистка в 03:00), scraper/Dockerfile, 4 новых теста | 31/31 тестов прошли, коммит feature/backend-api 0fca57a
- `[доработка]` | Code review бэкенда (feature/backend-api, 12 коммитов) | Проверены все файлы API, scraper, тесты, Docker, фронтенд-интеграция | Найдено 4 критических, 7 важных, 6 минорных замечаний; блокеры: CORS/OPTIONS middleware, SSRF в feed import
