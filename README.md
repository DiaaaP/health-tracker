# Sana — health tracker

Учебный трекер женского здоровья с интерфейсом на казахском и русском языках.

## Структура

```text
frontend/   HTML, CSS и JavaScript
backend/    FastAPI, Pydantic и SQLite
docs/       материалы для защиты
```

## Локальный запуск полной версии

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

После запуска:

- приложение: http://127.0.0.1:8000/
- Swagger API: http://127.0.0.1:8000/docs
- проверка backend: http://127.0.0.1:8000/api/health

SQLite-база `backend/sana.db` создаётся автоматически и не сохраняется в Git.

## Регистрация

- `POST /api/auth/register` — создаёт пользователя.
- `POST /api/auth/login` — проверяет email и пароль.

Пользователи сохраняются в таблице `users`. Пароли в открытом виде не хранятся:
backend сохраняет только защищённый hash с индивидуальной солью. Проверить оба
запроса можно через Swagger по адресу http://127.0.0.1:8000/docs.

## Локальный AI-чат через Ollama

AI-чат работает напрямую из браузера с локальной Ollama. Backend проекта для
этого менять не нужно.

```powershell
ollama serve
ollama pull qwen2.5:3b
```

После запуска откройте раздел `AI-чат`. Адрес Ollama уже указан во frontend:
`http://127.0.0.1:11434`. Название модели можно поменять прямо на странице чата.
Ответы AI используются только как общая информация и не заменяют врача.

## Публичная frontend-версия

GitHub Pages: https://diaaap.github.io/health-tracker/

На GitHub Pages backend недоступен, поэтому frontend автоматически использует
локальное хранилище как демонстрационный fallback.

## Учебные задачи команды

- Design: унифицировать формы и spacing, подготовить 3–4 экрана в Figma.
- Frontend: подключить `/api/summary`, добавить полную валидацию и улучшить mobile calendar.
- Backend: расширить расчёт summary, добавить обновление записи и более строгую validation.
