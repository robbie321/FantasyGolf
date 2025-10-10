# Geo-Redirect Setup Guide

This guide explains how to set up geo-based domain redirection for Fantasy Fairways, directing UK users to `fantasyfairway.co.uk` and Irish users to `fantasyfairway.ie`.

## Overview

The geo-redirect system automatically detects a user's country and redirects them to the appropriate domain:
- **UK users** (GB) → `fantasyfairway.co.uk`
- **Irish users** (IE) → `fantasyfairway.ie`
- **Other users** → Can access either domain (no redirect)

## How It Works

1. **Country Detection**: Uses CloudFlare's `CF-IPCountry` header or custom headers
2. **Smart Redirect**: Only redirects on GET requests to avoid breaking forms
3. **Loop Prevention**: Sets a cookie after redirect to prevent infinite loops
4. **Path Preservation**: Maintains the full URL path and query parameters during redirect

## Configuration

### Environment Variables

Add these to your production environment (e.g., Heroku Config Vars):

```bash
# Domain Configuration
IE_DOMAIN=fantasyfairway.ie
UK_DOMAIN=fantasyfairway.co.uk

# Enable/Disable Geo-Redirect (default: true)
GEO_REDIRECT_ENABLED=true
```

### Local Development

Geo-redirect is **disabled by default** in development mode to avoid issues with localhost testing.

To test geo-redirect locally, set in your environment:
```bash
GEO_REDIRECT_ENABLED=true
```

## DNS & Domain Setup

### 1. Point Both Domains to Your Server

Both `fantasyfairway.ie` and `fantasyfairway.co.uk` should point to the same server/hosting platform.

#### For Heroku:
```bash
# Add both domains to your Heroku app
heroku domains:add fantasyfairway.ie
heroku domains:add www.fantasyfairway.ie
heroku domains:add fantasyfairway.co.uk
heroku domains:add www.fantasyfairway.co.uk
```

#### DNS Records:
For each domain, create:
- **A Record** or **CNAME** pointing to your server
- **SSL Certificate** for each domain (Heroku handles this automatically)

### 2. CloudFlare Setup (Recommended)

CloudFlare provides the `CF-IPCountry` header which makes geo-detection very accurate.

1. Add both domains to CloudFlare
2. Set up DNS records as proxied (orange cloud)
3. Enable "Always Use HTTPS"
4. The geo-redirect will automatically use CloudFlare's country detection

**CloudFlare Configuration:**
- fantasyfairway.ie → Proxy enabled
- fantasyfairway.co.uk → Proxy enabled

### 3. SSL Certificates

Ensure both domains have valid SSL certificates:
- **Heroku**: Automatic with ACM (Automated Certificate Management)
- **CloudFlare**: Provides free SSL certificates
- **Other hosts**: Use Let's Encrypt or your hosting provider's SSL

## Testing

### Test Geo-Redirect Logic

You can test the redirect by simulating different countries:

**1. Using Browser DevTools:**
```javascript
// In browser console, set a custom header (requires browser extension)
// Or use a VPN to test from different countries
```

**2. Using cURL:**
```bash
# Simulate UK user on .ie domain
curl -H "CF-IPCountry: GB" https://fantasyfairway.ie/

# Simulate IE user on .co.uk domain
curl -H "CF-IPCountry: IE" https://fantasyfairway.co.uk/
```

**3. Using VPN:**
- Connect to UK VPN, visit fantasyfairway.ie → should redirect to .co.uk
- Connect to IE VPN, visit fantasyfairway.co.uk → should redirect to .ie

### Verify Redirect Cookie

After being redirected once, the system sets a `geo_redirected` cookie (valid for 30 days) to prevent redirect loops.

Check in browser DevTools → Application → Cookies

## Skipped Paths

The following paths are **excluded** from geo-redirect:
- `/api/*` - API endpoints
- `/webhook/*` - Webhook handlers
- `/static/*` - Static files
- `/_debug` - Debug endpoints
- `/health` - Health checks
- All POST/PUT/DELETE requests (only GET redirects)

## Advanced Configuration

### Disable Geo-Redirect

To temporarily disable geo-redirect:
```bash
# Set environment variable
GEO_REDIRECT_ENABLED=false
```

### Custom Country Detection

If you're not using CloudFlare, you can add custom geo-detection in `geo_redirect.py`:

```python
def get_user_country(self):
    # Add your custom geo-detection logic
    # Example: MaxMind GeoIP2
    import geoip2.database
    reader = geoip2.database.Reader('/path/to/GeoLite2-Country.mmdb')
    ip = self.get_client_ip()
    response = reader.country(ip)
    return response.country.iso_code
```

### Add More Countries

To redirect users from other countries:

Edit `geo_redirect.py` in the `should_redirect()` method:

```python
def should_redirect(self, country, current_domain):
    # Add more countries
    if country in ['GB', 'UK', 'IM', 'JE', 'GG']:  # UK + Crown Dependencies
        if self.uk_domain not in current_domain:
            return self.uk_domain

    elif country in ['IE']:  # Ireland
        if self.ie_domain not in current_domain:
            return self.ie_domain

    # Add more countries as needed
    # elif country == 'US':
    #     if 'fantasyfairway.com' not in current_domain:
    #         return 'fantasyfairway.com'

    return None
```

## Monitoring & Logging

The system logs all redirects:

```python
logger.info(f"Redirecting {country} user from {current_domain} to {target_domain}")
```

Check your application logs to monitor:
- How many users are being redirected
- Which countries are accessing your site
- Any redirect issues or loops

## Troubleshooting

### Issue: Redirect Loop
**Solution**: Clear the `geo_redirected` cookie and ensure both domains point to the same app

### Issue: Not Detecting Country
**Solutions**:
1. Verify CloudFlare is enabled (orange cloud)
2. Check that `CF-IPCountry` header is present
3. Add fallback geo-detection (GeoIP2)

### Issue: Users on Wrong Domain
**Solution**: The cookie prevents re-redirect for 30 days. Users can manually visit the other domain if needed.

### Issue: Forms Breaking After Redirect
**Solution**: The system only redirects GET requests. If forms are breaking, check that they use POST method.

## Database Considerations

### Shared Database
Both domains should connect to the **same database**. User accounts, leagues, and all data are shared between `.ie` and `.co.uk`.

### Environment Variables
Both domains should use the **same** `DATABASE_URL` environment variable.

## SEO Considerations

### Canonical URLs
Consider adding canonical tags to prevent duplicate content issues:

```html
<!-- On .co.uk pages -->
<link rel="canonical" href="https://fantasyfairway.co.uk/..." />

<!-- On .ie pages -->
<link rel="canonical" href="https://fantasyfairway.ie/..." />
```

### hreflang Tags
Add hreflang tags to help search engines understand geo-targeting:

```html
<link rel="alternate" hreflang="en-gb" href="https://fantasyfairway.co.uk/" />
<link rel="alternate" hreflang="en-ie" href="https://fantasyfairway.ie/" />
```

## Future Enhancements

Consider adding:
1. **User preference**: Allow users to choose their preferred domain
2. **More countries**: Add support for more regions (.com, .eu, etc.)
3. **Language detection**: Redirect based on browser language
4. **A/B testing**: Test redirect effectiveness
5. **Analytics**: Track user location and domain preferences

## Support

If you encounter issues:
1. Check application logs for redirect errors
2. Verify DNS records are correct
3. Test with cURL to see headers
4. Ensure CloudFlare is properly configured
5. Check that SSL certificates are valid for both domains
