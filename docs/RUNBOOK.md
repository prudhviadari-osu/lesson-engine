# Runbook — Ubuntu VM deployment

This is the production target from the PRD: **backend on an Ubuntu VM (on a
Mac), UI served on localhost.**

## 1. Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip mysql-server
python3 --version   # 3.10+
```

## 2. Get the code + config

```bash
git clone <this-repo> learnpp && cd learnpp
cp .env.example backend/.env
# edit backend/.env: set GEMINI_API_KEY, SECRET_KEY, DATABASE_URL, USE_MOCK_INTEGRATIONS=0
```

## 3. Optional production extras

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pymysql playwright          # MySQL + Canvas scraping
playwright install chromium
```

- MySQL: follow `docs/MIGRATION.md`.
- Canvas/OSU: implement the `_real_*` / `_playwright_scrape` methods in
  `backend/app/integrations/` against live OSU endpoints, then set
  `USE_MOCK_INTEGRATIONS=0`.

## 4. Seed (first run only) and launch

```bash
python -m backend.scripts.seed
python -m backend.app.main
# UI + API at http://127.0.0.1:8000  (set HOST/PORT in .env)
```

## 5. Run as a service (systemd)

```ini
# /etc/systemd/system/learnpp.service
[Unit]
Description=Learn++
After=network.target mysql.service

[Service]
WorkingDirectory=/home/you/learnpp
EnvironmentFile=/home/you/learnpp/backend/.env
ExecStart=/home/you/learnpp/.venv/bin/python -m backend.app.main
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now learnpp
```

## 6. Auto-generate lessons on a schedule

Mini-lessons auto-generate on student signup. To keep lessons fresh as new
assignments enter the 7-day window, run the job periodically:

```bash
# crontab -e  — every hour
0 * * * * cd /home/you/learnpp && .venv/bin/python -c "from backend.app.services.lesson_service import autogenerate_due_soon; from backend.app.db.database import init_db; init_db(); autogenerate_due_soon()"
```

## 7. Health check

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","app":"Learn++","mock_integrations":false,"database":"mysql"}
```
