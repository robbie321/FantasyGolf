# FOUC (Flash of Unstyled Content) Fix Guide

## What Was Fixed

Your site was experiencing FOUC - when pages load without CSS styling for a brief moment, showing unstyled HTML before the CSS loads.

## Changes Made

### 1. **Critical CSS in `<head>`** ✅

Added inline critical CSS to prevent the white flash:

```html
<style>
  /* Critical CSS - Prevents blank page flash */
  html {
    visibility: visible;
    opacity: 1;
  }
  body {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    background-color: #f9fbfb;
    visibility: visible !important;
  }
</style>
```

This ensures users see a styled page immediately.

### 2. **Optimized CSS Loading Order** ✅

**Before:** CSS files loaded in random order
**After:** Main stylesheet (`style.css`) loads FIRST

```html
<!-- Load critical CSS first -->
<link rel="stylesheet" href="css/style.css?v=1.0" />
<!-- Then other CSS -->
<link href="css/fa/css/fontawesome.css?v=1.0" rel="stylesheet" />
```

### 3. **Added Cache Busting** ✅

Added version numbers to all assets:

```html
<link rel="stylesheet" href="css/style.css?v=1.0" />
```

When you update CSS, increment the version:
```bash
heroku config:set ASSET_VERSION=1.1
```

This forces browsers to reload new CSS instead of using cached old versions.

### 4. **Moved JavaScript to Bottom** ✅

**Before:** JavaScript in `<head>` (blocks rendering)
**After:** JavaScript before `</body>` (doesn't block CSS)

This allows CSS to load and render before JavaScript executes.

### 5. **Added Preconnect** ✅

Added preconnect hints for external resources:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
```

This tells the browser to start connecting to Google Fonts early.

### 6. **Async Loading for Non-Critical CSS** ✅

Flag icons now load without blocking:

```html
<link
  rel="stylesheet"
  href="https://cdn.jsdelivr.net/gh/lipis/flag-icons@7.2.3/css/flag-icons.min.css"
  media="print"
  onload="this.media='all'"
/>
```

### 7. **Added Cache Headers** ✅

Static files now cache properly in browsers:

```python
@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response
```

Static files cache for 1 year, speeding up repeat visits.

---

## How to Test

### 1. **Clear Browser Cache**

**Chrome/Edge:**
- Press `Ctrl + Shift + Delete`
- Select "Cached images and files"
- Click "Clear data"

**Firefox:**
- Press `Ctrl + Shift + Delete`
- Check "Cache"
- Click "Clear Now"

### 2. **Test Loading Speed**

1. Open Chrome DevTools (`F12`)
2. Go to **Network** tab
3. Check "Disable cache"
4. Reload page (`Ctrl + F5`)
5. Watch the waterfall - CSS should load before page renders

### 3. **Test on Slow Connection**

In Chrome DevTools:
1. Go to **Network** tab
2. Change throttling to "Slow 3G"
3. Reload page
4. You should still see styled content (no white flash)

### 4. **Mobile Testing**

Test on actual mobile device:
- Clear browser cache
- Visit your site
- Should load styled (no white flash)

---

## Deployment Steps

### Step 1: Deploy Changes to Heroku

```bash
# Commit changes
git add .
git commit -m "Fix FOUC - optimize CSS loading"

# Push to Heroku
git push heroku main
```

### Step 2: Set Asset Version

```bash
# Set initial version
heroku config:set ASSET_VERSION=1.0
```

### Step 3: Verify on Production

1. Visit your production site
2. Open DevTools → Network tab
3. Check that CSS files have `?v=1.0` in URL
4. Verify no FOUC occurs

### Step 4: Clear CloudFlare Cache (if using)

If you're using CloudFlare:

1. Log in to CloudFlare
2. Go to **Caching** → **Configuration**
3. Click **"Purge Everything"**
4. Wait 30 seconds
5. Test your site again

---

## When You Update CSS/JS in the Future

### Step 1: Make Your Changes

Edit your CSS files as normal.

### Step 2: Increment Version Number

```bash
# Increment version to force browser reload
heroku config:set ASSET_VERSION=1.1

# Or for major changes:
heroku config:set ASSET_VERSION=2.0
```

### Step 3: Clear CloudFlare Cache (if applicable)

Purge CloudFlare cache as described above.

### Step 4: Test

- Clear your browser cache
- Visit site
- Verify new styles are loaded

---

## Troubleshooting

### Issue: Still Seeing FOUC

**Solutions:**

1. **Hard refresh browser:**
   - Chrome/Firefox: `Ctrl + Shift + R`
   - Safari: `Cmd + Shift + R`

2. **Check CSS file is loading:**
   - Open DevTools → Network tab
   - Look for `style.css`
   - Status should be `200` (not `404`)

3. **Verify version number:**
   ```bash
   heroku config:get ASSET_VERSION
   ```

4. **Check file paths:**
   - Make sure `static/css/style.css` exists
   - Check file permissions

### Issue: Old CSS Still Showing

**Solutions:**

1. **Increment version number:**
   ```bash
   heroku config:set ASSET_VERSION=1.1
   ```

2. **Clear CloudFlare cache**

3. **Clear browser cache completely**

4. **Test in incognito/private mode**

### Issue: CSS Loads But Fonts Don't

**Solution:**

Check Google Fonts connection:
```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link
  href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap"
  rel="stylesheet"
/>
```

The `&display=swap` parameter tells browsers to show fallback fonts immediately.

### Issue: Slow First Load

**Solutions:**

1. **Enable CloudFlare (if not already):**
   - CloudFlare caches CSS files globally
   - Much faster for users worldwide

2. **Minify CSS files:**
   ```bash
   # Install cssmin
   pip install cssmin

   # Minify your CSS
   cssmin < static/css/style.css > static/css/style.min.css
   ```

   Then update base.html to use `style.min.css`

3. **Enable gzip compression on Heroku:**
   - Heroku enables this by default
   - Verify with DevTools → Network → Headers → `Content-Encoding: gzip`

---

## Performance Improvements Made

### Before:
- ❌ CSS loaded after JavaScript
- ❌ No cache headers
- ❌ No version numbers (browser caches old CSS)
- ❌ External resources not preconnected
- ❌ FOUC visible on slow connections

### After:
- ✅ CSS loads first
- ✅ Cache headers set (1 year for static files)
- ✅ Version numbers for cache busting
- ✅ Preconnect to external resources
- ✅ Critical CSS inline
- ✅ JavaScript at bottom
- ✅ No FOUC on any connection speed

---

## Monitoring Page Load Performance

### Using Chrome DevTools

1. Open DevTools (`F12`)
2. Go to **Lighthouse** tab
3. Click **"Generate report"**
4. Check **Performance** score

**Target:** 90+ performance score

### Using WebPageTest

1. Go to https://www.webpagetest.org
2. Enter your URL
3. Click **"Start Test"**
4. Review:
   - **First Contentful Paint** (should be < 1.5s)
   - **Largest Contentful Paint** (should be < 2.5s)
   - **Cumulative Layout Shift** (should be < 0.1)

### Using GTmetrix

1. Go to https://gtmetrix.com
2. Enter your URL
3. Check:
   - **Page Load Time**
   - **Total Page Size**
   - **Number of Requests**

---

## Additional Optimizations (Optional)

### 1. Lazy Load Images

For images below the fold:

```html
<img src="image.jpg" loading="lazy" alt="Description" />
```

### 2. Use WebP Images

Convert images to WebP for smaller file sizes:

```html
<picture>
  <source srcset="image.webp" type="image/webp">
  <img src="image.jpg" alt="Description">
</picture>
```

### 3. Minify CSS

Use a CSS minifier to reduce file sizes:

```bash
# Install
pip install rcssmin

# Minify
python -m rcssmin < style.css > style.min.css
```

### 4. Enable HTTP/2

Heroku supports HTTP/2 by default with SSL.

Verify:
```bash
curl -I --http2 https://fantasyfairway.ie
```

Look for: `HTTP/2 200`

### 5. Use a Service Worker

Cache CSS in service worker for instant loading:

```javascript
// In service-worker.js
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open('v1').then((cache) => {
      return cache.addAll([
        '/static/css/style.css',
        '/static/css/fa/css/fontawesome.css',
        // etc.
      ]);
    })
  );
});
```

---

## Summary of Files Changed

1. **`templates/base.html`**
   - Added critical inline CSS
   - Reorganized CSS loading order
   - Added preconnect hints
   - Added version numbers to assets
   - Moved JavaScript to bottom

2. **`fantasy_league_app/__init__.py`**
   - Added cache headers for static files

3. **`fantasy_league_app/config.py`**
   - Added `ASSET_VERSION` configuration

---

## Checklist for Future Updates

When updating CSS/JS:

- [ ] Make your changes to CSS/JS files
- [ ] Test locally
- [ ] Increment `ASSET_VERSION` before deploying
- [ ] Deploy to Heroku
- [ ] Clear CloudFlare cache (if using)
- [ ] Test in production
- [ ] Clear browser cache and test
- [ ] Test on mobile devices

---

## Questions?

If FOUC persists:
1. Check browser console for errors
2. Verify all CSS files exist in `/static/css/`
3. Check Network tab to see if CSS is loading
4. Test in incognito mode
5. Try different browsers

The changes should eliminate FOUC completely! 🎉
