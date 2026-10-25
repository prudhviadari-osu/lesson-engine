# Migrating SQLite → MySQL (production on the Ubuntu VM)

The PRD specifies **MySQL**. This build uses SQLite by default so it runs with
zero dependencies, but all SQL is isolated in two files, so the switch is
small and contained.

## 1. Install the driver

```bash
pip install pymysql        # pure-Python MySQL driver
```

## 2. Create the database

```sql
CREATE DATABASE learnpp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'learnpp'@'localhost' IDENTIFIED BY 'strong-password';
GRANT ALL PRIVILEGES ON learnpp.* TO 'learnpp'@'localhost';
FLUSH PRIVILEGES;
```

## 3. Point the app at MySQL

The data layer (`backend/app/db/database.py`) exposes a single `connect()`
function and a `SCHEMA` string. To use MySQL, replace the SQLite connection
with PyMySQL and adjust the DDL dialect:

- `INTEGER PRIMARY KEY AUTOINCREMENT` → `INT AUTO_INCREMENT PRIMARY KEY`
- `TEXT` → `TEXT` / `VARCHAR(n)` (already sized for key columns)
- `datetime('now')` default → `CURRENT_TIMESTAMP`
- Replace `?` placeholders with `%s` (PyMySQL paramstyle) — or keep a thin
  adapter that rewrites them.

Because every query lives in `repository.py` as a named function, no route or
service code changes. A clean approach is to add a `db/mysql_backend.py` that
mirrors `database.py`'s public surface (`connect`, `query_all`, `query_one`,
`execute`, `init_db`) and select the backend from `settings.DATABASE_URL`.

## 4. Configure

```bash
# backend/.env
DATABASE_URL=mysql+pymysql://learnpp:strong-password@localhost:3306/learnpp
```

## 5. Seed + run

```bash
python -m backend.scripts.seed
python -m backend.app.main
```

> The ORM-style column names and relationships were chosen to map cleanly onto
> MySQL; no schema redesign is needed.
