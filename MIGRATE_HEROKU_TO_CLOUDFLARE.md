# Migrating Fantasy Fairways from Heroku to CloudFlare

This guide will help you migrate your Fantasy Fairways Flask application from Heroku to CloudFlare's hosting platform.

## ⚠️ Important Considerations

**Before we start, you need to understand:**

### CloudFlare's Hosting Options:

1. **CloudFlare Pages** - For static sites (HTML/CSS/JS)
   - ❌ **Cannot run Flask/Python directly**
   - Good for: React, Vue, Next.js, static sites

2. **CloudFlare Workers** - For serverless functions (JavaScript/Wasm)
   - ❌ **Cannot run full Flask apps directly**
   - Good for: API endpoints, edge computing, redirects

3. **CloudFlare as CDN + Keep Heroku** - ✅ **Recommended**
   - CloudFlare sits in front of Heroku
   - You get CloudFlare benefits + keep Flask app running
   - This is what most people do!

### The Reality:

**Your Fantasy Fairways app is a Flask/Python application with:**
- Database connections (PostgreSQL)
- Background jobs (Celery)
- Session management (Redis)
- Complex routing
- Real-time features

**CloudFlare cannot directly host this.**

---

## Recommended Approach: CloudFlare + Heroku (Hybrid)

This is the **best solution** - you get CloudFlare's benefits while keeping your Flask app on Heroku.

### What You Get:

✅ CloudFlare's geo-detection (CF-IPCountry header)
✅ Free SSL certificates
✅ DDoS protection
✅ CDN for static assets
✅ Your Flask app keeps running on Heroku
✅ No code changes needed!

### Setup Steps:

**This is already covered in `CLOUDFLARE_SETUP_GUIDE.md`!**

Just follow that guide - you're using CloudFlare as a CDN/proxy in front of Heroku.

---

## Alternative 1: Move to CloudFlare-Compatible Platform

If you truly want to leave Heroku, consider these alternatives:

### Option A: Railway.app (Easiest)
- Similar to Heroku
- Supports Flask/Python
- Can use with CloudFlare
- Migration: ~30 minutes

### Option B: Render.com
- Heroku alternative
- Free tier available
- Direct Heroku migration tool
- Migration: ~1 hour

### Option C: DigitalOcean App Platform
- Heroku-like experience
- More control than Heroku
- Works with CloudFlare
- Migration: ~2 hours

### Option D: AWS/GCP/Azure
- Full control
- More complex setup
- Enterprise-grade
- Migration: Days/weeks

**For all of these, you'd still use CloudFlare as a CDN in front!**

---

## If You Still Want to Move: Railway.app Guide

Railway is the closest Heroku alternative that works seamlessly with CloudFlare.

### Part 1: Prepare for Migration

#### Step 1: Export Heroku Data

**1. Export environment variables:**
```bash
# Install Heroku CLI if you haven't
# Download from: https://devcenter.heroku.com/articles/heroku-cli

# List all your config vars
heroku config --app your-heroku-app-name > heroku-config.txt

# This saves all your environment variables to a file
```

**2. Backup your database:**
```bash
# Get database URL
heroku config:get DATABASE_URL --app your-heroku-app-name

# Create backup
heroku pg:backups:capture --app your-heroku-app-name

# Download backup
heroku pg:backups:download --app your-heroku-app-name
```

**3. List all your Heroku add-ons:**
```bash
heroku addons --app your-heroku-app-name
```

Write down:
- PostgreSQL plan
- Redis plan (if using Heroku Redis)
- Any other add-ons

#### Step 2: Prepare Your Code

**1. Create `railway.json` in your project root:**
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "gunicorn -w 4 -b 0.0.0.0:$PORT 'fantasy_league_app:create_app()'",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**2. Ensure you have these files:**
- `requirements.txt` ✓ (you already have this)
- `Procfile` ✓ (Railway can use this too)
- `runtime.txt` (optional, specifies Python version)

**3. Create `runtime.txt` if you don't have it:**
```
python-3.11.5
```

### Part 2: Set Up Railway

#### Step 3: Sign Up for Railway

1. Go to **https://railway.app**
2. Click **"Sign Up"**
3. Sign up with GitHub (easiest - connects your repos)
4. Verify your email

#### Step 4: Create New Project

1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Authorize Railway to access your GitHub
4. Select your Fantasy Fairways repository
5. Railway will detect it's a Python app automatically

#### Step 5: Add Database (PostgreSQL)

1. In your Railway project, click **"New"**
2. Select **"Database"** → **"PostgreSQL"**
3. Railway provisions a PostgreSQL database
4. Copy the connection string (you'll need this)

#### Step 6: Add Redis

1. Click **"New"** again
2. Select **"Database"** → **"Redis"**
3. Railway provisions Redis
4. Copy the Redis URL

#### Step 7: Configure Environment Variables

In Railway dashboard:

1. Click on your app service
2. Go to **"Variables"** tab
3. Click **"Raw Editor"**
4. Paste all your Heroku config vars from `heroku-config.txt`

**Update these specific vars:**
```bash
DATABASE_URL=[Railway PostgreSQL URL]
REDIS_URL=[Railway Redis URL]
REDISCLOUD_URL=[Railway Redis URL]
PORT=8080
```

**Make sure these are set:**
```bash
FLASK_ENV=production
SECRET_KEY=your-secret-key
STRIPE_PUBLIC_KEY=pk_xxx
STRIPE_SECRET_KEY=sk_xxx
# ... all your other vars
```

#### Step 8: Deploy

1. Railway automatically deploys when you push to GitHub
2. Or click **"Deploy"** button in Railway dashboard
3. Watch the build logs
4. Once deployed, Railway gives you a URL like: `fantasy-fairways-production.up.railway.app`

### Part 3: Migrate Database

#### Step 9: Restore Database Backup

**Option A: Using pg_restore (if you have PostgreSQL installed locally)**

```bash
# Get Railway database credentials
# In Railway dashboard: PostgreSQL service → Connect → "Connection URL"

# Restore from backup
pg_restore --verbose --no-owner --no-acl -d [RAILWAY_DATABASE_URL] latest.dump
```

**Option B: Use Railway's Database Tools**

1. In Railway, go to your PostgreSQL service
2. Click **"Data"** tab
3. You can import SQL directly or use CLI

**Option C: Keep Heroku Database (Recommended for smooth transition)**

1. Keep using Heroku PostgreSQL temporarily
2. Update Railway's `DATABASE_URL` to point to Heroku database
3. This gives you time to test Railway before full migration

#### Step 10: Migrate Redis Data (if needed)

Redis is typically fine to start fresh (sessions, cache):

```bash
# If you need to copy Redis data
# Not usually necessary - sessions will rebuild
```

### Part 4: Configure Celery Worker

Railway can run multiple services in one project.

#### Step 11: Add Celery Worker Service

1. In Railway project, click **"New"** → **"GitHub Repo"**
2. Select same repository
3. Configure as Celery worker:

**Start Command:**
```bash
celery -A fantasy_league_app.celery_app:celery worker --loglevel=info
```

4. Add all same environment variables as main app

#### Step 12: Add Celery Beat (Scheduler)

1. Add another service from same repo
2. Configure as Celery Beat:

**Start Command:**
```bash
celery -A fantasy_league_app.celery_app:celery beat --loglevel=info
```

### Part 5: Configure Domains

#### Step 13: Add Custom Domains to Railway

1. In Railway, go to your app service
2. Click **"Settings"** tab
3. Scroll to **"Domains"**
4. Click **"Add Domain"**
5. Add both:
   - `fantasyfairway.ie`
   - `fantasyfairway.co.uk`

Railway will give you a CNAME target.

#### Step 14: Update CloudFlare DNS

In CloudFlare for each domain:

1. Go to **DNS** tab
2. Update your `@` record:
   - **Before:** A record pointing to Heroku IP
   - **After:** CNAME record pointing to Railway's CNAME target

**Example:**
```
Type: CNAME
Name: @
Target: fantasy-fairways.up.railway.app
Proxy: 🟠 Proxied
```

3. Do the same for `www`:
```
Type: CNAME
Name: www
Target: fantasy-fairways.up.railway.app
Proxy: 🟠 Proxied
```

### Part 6: Testing

#### Step 15: Test Railway Deployment

**Before updating DNS:**

1. Test using Railway's URL: `https://fantasy-fairways-production.up.railway.app`
2. Check:
   - ✅ Site loads
   - ✅ Login works
   - ✅ Database queries work
   - ✅ Redis sessions work
   - ✅ Celery tasks run
   - ✅ Stripe payments work

**Update `/etc/hosts` for testing (Windows):**
```bash
# Edit C:\Windows\System32\drivers\etc\hosts
# Add this line to test before DNS change:
[RAILWAY_IP] fantasyfairway.ie
```

#### Step 16: Gradual Migration

**To minimize downtime:**

1. Keep both Heroku and Railway running
2. Update DNS for testing subdomain first
3. Monitor Railway for 24-48 hours
4. Switch main domain DNS when confident

### Part 7: Post-Migration

#### Step 17: Monitor Everything

**First 48 Hours:**
- Check Railway logs constantly
- Monitor error rates
- Watch database connections
- Verify Celery tasks running

**Railway Logging:**
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# View logs
railway logs
```

#### Step 18: Optimize Railway

**Set correct resource limits:**

1. Go to **Settings** → **Resources**
2. Adjust:
   - Memory: 2GB minimum (start here)
   - CPU: Shared (upgrade if needed)

**Enable auto-scaling if available on your plan**

#### Step 19: Update Webhooks

Update webhook URLs in:
- Stripe dashboard
- Any third-party services
- OAuth callbacks (if any)

Change from:
- `https://your-app.herokuapp.com/webhook/...`

To:
- `https://fantasyfairway.ie/webhook/...`

#### Step 20: Decommission Heroku

**Only after Railway is stable (1-2 weeks):**

1. Download final Heroku logs:
```bash
heroku logs --tail --app your-app > heroku-final-logs.txt
```

2. Take final database backup

3. Scale down Heroku dynos:
```bash
heroku ps:scale web=0 worker=0 --app your-app
```

4. Cancel Heroku add-ons (or keep as backup for a month)

5. Eventually delete Heroku app

---

## Cost Comparison

### Heroku (Current):
- Hobby Dynos: $7/month × 2 = $14/month
- Postgres: $9/month
- Redis: $15/month
- **Total: ~$38/month**

### Railway (New):
- Starter Plan: $5/month (base)
- Usage-based after free tier
- PostgreSQL: Included
- Redis: Included
- **Estimated: $10-20/month** (depends on usage)

### CloudFlare:
- Free plan: $0/month
- (You still use CloudFlare either way!)

---

## Pros and Cons

### Railway Pros:
✅ Cheaper than Heroku
✅ Modern dashboard
✅ Faster deployments
✅ Better pricing model
✅ PostgreSQL and Redis included
✅ Easy GitHub integration

### Railway Cons:
❌ Smaller community
❌ Less mature than Heroku
❌ Fewer add-ons/integrations
❌ Less documentation

### Keeping Heroku Pros:
✅ Proven, stable platform
✅ Massive ecosystem
✅ Excellent documentation
✅ Your app already works there
✅ Easy to manage

### Keeping Heroku Cons:
❌ More expensive
❌ Slower than competitors
❌ Salesforce ownership concerns
❌ Free tier removed

---

## Alternative: Stay on Heroku

**Honestly, if money isn't a huge issue:**

### Just Use CloudFlare + Heroku

This setup gives you:
- ✅ All CloudFlare benefits (geo-detection, SSL, DDoS)
- ✅ Stable Heroku hosting
- ✅ No migration risk
- ✅ No downtime
- ✅ Everything keeps working

**You already set this up in `CLOUDFLARE_SETUP_GUIDE.md`!**

### Optimize Heroku Costs:

1. **Consolidate dynos:**
   ```bash
   # Use fewer, larger dynos instead of many small ones
   heroku ps:scale web=1:standard-1x
   ```

2. **Use Heroku Postgres mini instead of basic:**
   - Downgrade if you don't need the resources

3. **Consider Heroku annual commitment** (20% discount)

4. **Remove unused add-ons**

---

## My Recommendation

### For Fantasy Fairways Specifically:

**Stick with Heroku + CloudFlare** because:

1. Your app is production-ready on Heroku
2. Users are actively using it
3. Migration risk isn't worth the $15-20/month savings
4. You'll spend hours migrating and testing
5. CloudFlare already gives you 90% of the benefits

**BUT if you want to migrate anyway:**
- Railway.app is the best Heroku alternative
- Migration time: 1-2 days for full setup
- Risk level: Medium
- Cost savings: ~$20/month

---

## Decision Matrix

| Scenario | Recommendation |
|----------|---------------|
| App is profitable | Stay on Heroku + CloudFlare |
| App is side project | Migrate to Railway |
| Want learning experience | Migrate to Railway |
| Can't afford downtime | Stay on Heroku + CloudFlare |
| Have time for migration | Migrate to Railway |
| Need enterprise features | Stay on Heroku |
| Budget is very tight | Migrate to Railway or DigitalOcean |

---

## Support Resources

### Railway:
- Docs: https://docs.railway.app
- Discord: https://discord.gg/railway
- Status: https://status.railway.app

### Heroku:
- Docs: https://devcenter.heroku.com
- Support: https://help.heroku.com

### CloudFlare:
- Docs: https://developers.cloudflare.com
- Community: https://community.cloudflare.com

---

## Quick Start: Stay with Heroku + CloudFlare

**If you decide to stick with Heroku (recommended):**

1. ✅ You already have the code for geo-redirect
2. ✅ Just follow `CLOUDFLARE_SETUP_GUIDE.md`
3. ✅ Point both domains to Heroku through CloudFlare
4. ✅ Enable geo-redirect in production:
   ```bash
   heroku config:set GEO_REDIRECT_ENABLED=true
   ```
5. ✅ Done! No migration needed.

---

## Need Help?

If you want to migrate to Railway, I can:
1. Help you with the specific Railway configuration
2. Create migration scripts for your database
3. Set up CI/CD pipelines
4. Monitor the migration process

Just let me know! But seriously, consider staying on Heroku with CloudFlare - it's the safe, proven approach.
