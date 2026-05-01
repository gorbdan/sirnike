# Гайд по базе `syrochnik.db`

## Где лежит база

- Локально (Windows): `C:\Users\Аня\OneDrive\Desktop\telegram bots\sirnike\syrochnik.db`
- На bothost обычно: `/app/data/syrochnik.db`

> В коде путь берётся из `DATA_DIR`. Если `DATA_DIR` не задан, база лежит рядом с ботом.

---

## Быстрый старт (Windows PowerShell)

Перейди в папку проекта:

```powershell
cd "C:\Users\Аня\OneDrive\Desktop\telegram bots\sirnike"
```

Показать таблицы:

```powershell
@'
import sqlite3
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print([r[0] for r in cur.fetchall()])
con.close()
'@ | py -
```

---

## Полезные запросы (готовые команды)

### 1) Сколько пользователей

```powershell
@'
import sqlite3
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
cur.execute("SELECT COUNT(*) FROM users")
print("users:", cur.fetchone()[0])
con.close()
'@ | py -
```

### 2) Новые пользователи за 7 дней

```powershell
@'
import sqlite3
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
cur.execute("SELECT COUNT(*) FROM users WHERE datetime(created_at) >= datetime('now','-7 day')")
print("new_7d:", cur.fetchone()[0])
con.close()
'@ | py -
```

### 3) Топ-10 пользователей по успешным генерациям изображений

```powershell
@'
import sqlite3
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
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

### 4) Топ-10 по видео (Seedance)

```powershell
@'
import sqlite3
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
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

### 5) Балансы (топ-20)

```powershell
@'
import sqlite3
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
cur.execute("SELECT user_id, COALESCE(username,''), balance FROM users ORDER BY balance DESC LIMIT 20")
for row in cur.fetchall():
    print(row)
con.close()
'@ | py -
```

### 6) Платежи за 30 дней

```powershell
@'
import sqlite3
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
cur.execute("""
SELECT COUNT(*) AS payments, COALESCE(SUM(amount),0) AS total_izuminki
FROM payments
WHERE datetime(created_at) >= datetime('now','-30 day')
""")
print(cur.fetchone())
con.close()
'@ | py -
```

### 7) История генераций конкретного пользователя

```powershell
@'
import sqlite3
USER_ID = 320423776
con=sqlite3.connect("syrochnik.db")
cur=con.cursor()
cur.execute("""
SELECT id, substr(prompt,1,80), image_url, created_at
FROM generation_history
WHERE user_id=?
ORDER BY id DESC
LIMIT 20
""", (USER_ID,))
for row in cur.fetchall():
    print(row)
con.close()
'@ | py -
```

---

## Проверка базы на bothost

В терминале bothost:

```bash
ls -lah /app/data
find /app -name "syrochnik.db"
```

Если база найдена, можно быстро проверить размер:

```bash
du -h /app/data/syrochnik.db
```

---

## Резервная копия базы

Локально:

```powershell
Copy-Item "syrochnik.db" "syrochnik_backup_$(Get-Date -Format yyyyMMdd_HHmmss).db"
```

На bothost:

```bash
cp /app/data/syrochnik.db /app/data/syrochnik_backup_$(date +%Y%m%d_%H%M%S).db
```

