# Celery Startup Guide

## Starting Celery Workers & Beat Scheduler

Celery is required for scheduled tasks and background jobs. You need TWO processes running:

### 1. Celery Worker (Processes Tasks)

**Windows (Development):**
```bash
celery -A fantasy_league_app.celery_app worker --loglevel=info --pool=solo
```

**Linux/Mac (Development):**
```bash
celery -A fantasy_league_app.celery_app worker --loglevel=info
```

**Production (Heroku):**
Already configured in `Procfile` - runs automatically

### 2. Celery Beat (Scheduler)

**Windows/Development:**
```bash
celery -A fantasy_league_app.celery_app beat --loglevel=info
```

**Production (Heroku):**
Already configured in `Procfile` - runs automatically

---

## Quick Start (Local Development)

Open **TWO terminal windows** in your project directory:

### Terminal 1 - Start Worker:
```bash
# Activate virtual environment
source venv/Scripts/activate  # Windows
# OR
source venv/bin/activate      # Mac/Linux

# Start worker
celery -A fantasy_league_app.celery_app worker --loglevel=info --pool=solo
```

### Terminal 2 - Start Beat:
```bash
# Activate virtual environment
source venv/Scripts/activate  # Windows
# OR
source venv/bin/activate      # Mac/Linux

# Start beat scheduler
celery -A fantasy_league_app.celery_app beat --loglevel=info
```

---

## Checking if Celery is Running

### From Admin Dashboard:
1. Go to `/dashboard` (admin dashboard)
2. Click **"Check Status"** in Beat Scheduler Status card
3. Click **"Inspect"** in Task Monitor card

### From Command Line:
```bash
# Check worker status
celery -A fantasy_league_app.celery_app inspect active

# Check scheduled tasks
celery -A fantasy_league_app.celery_app inspect scheduled

# Check registered tasks
celery -A fantasy_league_app.celery_app inspect registered
```

---

## Running Tasks WITHOUT Celery (Synchronous)

If you don't want to start Celery workers, you can run tasks synchronously:

1. Go to `/dashboard` (admin dashboard)
2. Find the task you want to run
3. Click **"Run Now (Sync)"** instead of "Queue Task"
4. Task runs immediately, no Celery required!

**Available for:**
- ✅ Update Player Buckets
- ✅ Schedule Score Updates

---

## Troubleshooting

### Worker won't start:
- Check Redis is running: `redis-cli ping` (should return "PONG")
- Check environment variables in `.env` file
- Try killing any stuck processes: `pkill -f celery`

### Tasks not running:
- Verify both worker AND beat are running
- Check logs for errors
- Verify server time is correct (UTC)
- Check Redis connection

### "Connection refused" errors:
- Make sure Redis is running
- Check `REDIS_URL` in `.env` file
- Default: `redis://localhost:6379/0`

---

## Production (Heroku)

Celery runs automatically via `Procfile`:
```
web: gunicorn fantasy_league_app:create_app()
worker: celery -A fantasy_league_app.celery_app worker --loglevel=info
beat: celery -A fantasy_league_app.celery_app beat --loglevel=info
```

Scale workers:
```bash
heroku ps:scale worker=1 beat=1
```

Check status:
```bash
heroku ps
heroku logs --tail --dyno=worker
heroku logs --tail --dyno=beat
```
