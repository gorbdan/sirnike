# Гайд по базе `syrochnik.db`

## Где база

- Локально (Windows): `C:\Users\Аня\OneDrive\Desktop\telegram bots\sirnike\syrochnik.db`
- На bothost: `/app/data/syrochnik.db`

Важно:
- Рабочая база на сервере должна быть именно в `/app/data`.
- Файл `/app/syrochnik.db` может быть старым (его не копируем поверх `/app/data/syrochnik.db`).

## Быстрая проверка на bothost

```bash
ls -lah /app/data/syrochnik.db
ls -lah /app/syrochnik.db
```

## Проверка таблиц локально (PowerShell)

```powershell
cd "C:\Users\Аня\OneDrive\Desktop\telegram bots\sirnike"
@'
import sqlite3
con = sqlite3.connect("syrochnik.db")
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print([r[0] for r in cur.fetchall()])
con.close()
'@ | py -
```

## Полезные команды локально

Сколько пользователей:

```powershell
@'
import sqlite3
con = sqlite3.connect("syrochnik.db")
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM users")
print("users:", cur.fetchone()[0])
con.close()
'@ | py -
```

Новые за 7 дней:

```powershell
@'
import sqlite3
con = sqlite3.connect("syrochnik.db")
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM users WHERE datetime(created_at) >= datetime('now','-7 day')")
print("new_7d:", cur.fetchone()[0])
con.close()
'@ | py -
```

Топ-10 по успешным генерациям картинок:

```powershell
@'
import sqlite3
con = sqlite3.connect("syrochnik.db")
cur = con.cursor()
cur.execute("""
SELECT ge.user_id, COALESCE(u.username,''), COUNT(*) AS cnt
FROM generation_events ge
LEFT JOIN users u ON u.user_id = ge.user_id
WHERE ge.kind='image' AND ge.status='success'
GROUP BY ge.user_id, u.username
ORDER BY cnt DESC
LIMIT 10
""")
for row in cur.fetchall():
    print(row)
con.close()
'@ | py -
```

Топ-10 по успешным видео:

```powershell
@'
import sqlite3
con = sqlite3.connect("syrochnik.db")
cur = con.cursor()
cur.execute("""
SELECT ge.user_id, COALESCE(u.username,''), COUNT(*) AS cnt
FROM generation_events ge
LEFT JOIN users u ON u.user_id = ge.user_id
WHERE ge.kind='video' AND ge.status='success'
GROUP BY ge.user_id, u.username
ORDER BY cnt DESC
LIMIT 10
""")
for row in cur.fetchall():
    print(row)
con.close()
'@ | py -
```

## Резервная копия

Локально:

```powershell
Copy-Item "syrochnik.db" "syrochnik_backup_$(Get-Date -Format yyyyMMdd_HHmmss).db"
```

На bothost:

```bash
cp /app/data/syrochnik.db /app/data/syrochnik_backup_$(date +%Y%m%d_%H%M%S).db
```
