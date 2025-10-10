# CloudFlare Setup Guide for Hosting Ireland Domains

This guide will walk you through moving your `fantasyfairways.ie` and `fantasyfairways.co.uk` domains from Hosting Ireland to CloudFlare for geo-detection and CDN benefits.

## Overview

**What we're doing:**
- Adding your domains to CloudFlare (free plan is sufficient)
- Keeping your domain registration with Hosting Ireland
- Pointing your domains' nameservers to CloudFlare
- Enabling CloudFlare proxy for geo-detection headers

**Benefits:**
- Automatic geo-detection (CF-IPCountry header)
- Free SSL certificates
- DDoS protection
- CDN (faster site loading worldwide)
- Analytics and insights

---

## Part 1: Sign Up for CloudFlare

### Step 1: Create CloudFlare Account

1. Go to **https://cloudflare.com**
2. Click **"Sign Up"** (top right)
3. Enter your email and create a password
4. Verify your email address
5. Log in to CloudFlare dashboard

---

## Part 2: Add Your First Domain (fantasyfairways.ie)

### Step 2: Add Site to CloudFlare

1. In CloudFlare dashboard, click **"Add a Site"**
2. Enter your domain: `fantasyfairways.ie`
3. Click **"Add Site"**
4. Select the **"Free"** plan (€0/month)
5. Click **"Continue"**

### Step 3: DNS Records Scan

CloudFlare will now scan your existing DNS records from Hosting Ireland.

1. Wait for the scan to complete (30-60 seconds)
2. CloudFlare will show you a list of DNS records it found
3. **Review the records carefully**

**Common records you should see:**
- `A` record for `@` (root domain) pointing to your server IP
- `A` or `CNAME` record for `www` pointing to your server
- `MX` records (if you have email)
- `TXT` records (for domain verification, SPF, etc.)

### Step 4: Configure DNS Records

For each DNS record shown:

**✅ Records to PROXY (Orange Cloud):**
- `A` record for `@` (fantasyfairways.ie) → Click to enable **orange cloud** ☁️
- `A` record for `www` (www.fantasyfairways.ie) → Click to enable **orange cloud** ☁️

**⚠️ Records to NOT proxy (Grey Cloud):**
- `MX` records (email) → Keep **grey cloud** ☁️
- `TXT` records → Keep **grey cloud** ☁️
- Any mail-related subdomains → Keep **grey cloud** ☁️

**What the colors mean:**
- 🟠 **Orange cloud** = Proxied through CloudFlare (enables geo-detection, SSL, DDoS protection)
- ⚪ **Grey cloud** = DNS only (bypasses CloudFlare, goes directly to your server)

**Example of correct setup:**

| Type | Name | Content | Proxy Status |
|------|------|---------|-------------|
| A | @ | 54.123.45.67 | 🟠 Proxied |
| A | www | 54.123.45.67 | 🟠 Proxied |
| MX | @ | mail.hostingireland.ie | ⚪ DNS only |
| TXT | @ | "v=spf1..." | ⚪ DNS only |

### Step 5: Missing DNS Records?

If CloudFlare didn't detect all your records:

1. Log in to **Hosting Ireland control panel**
2. Go to **DNS Management** for fantasyfairways.ie
3. Write down ALL your DNS records
4. In CloudFlare, click **"Add Record"** to manually add any missing ones

**Example: Adding an A record**
- Type: `A`
- Name: `@` (for root) or `www` (for www subdomain)
- IPv4 address: Your server IP (get from Hosting Ireland)
- Proxy status: 🟠 Proxied
- TTL: Auto

### Step 6: Get CloudFlare Nameservers

After reviewing DNS records, click **"Continue"**

CloudFlare will show you two nameservers that look like:
```
alan.ns.cloudflare.com
erin.ns.cloudflare.com
```

**📝 Write these down! You'll need them for the next part.**

⚠️ **DON'T CLOSE THIS WINDOW YET** - Keep it open while you update Hosting Ireland

---

## Part 3: Update Nameservers at Hosting Ireland

### Step 7: Log in to Hosting Ireland

1. Go to **https://www.hostingireland.ie**
2. Click **"Login"** (top right)
3. Enter your customer login credentials
4. You should see your control panel/dashboard

### Step 8: Navigate to Domain Management

The exact steps vary depending on your control panel type:

**Option A: cPanel/WHM**
1. Go to **"Domains"** or **"Domain Management"**
2. Find `fantasyfairways.ie`
3. Click **"Manage"** or **"DNS"**

**Option B: Hosting Ireland Custom Panel**
1. Go to **"My Domains"**
2. Click on `fantasyfairways.ie`
3. Look for **"Nameservers"** or **"DNS Settings"**

**Option C: Email/Phone Support**
If you can't find it:
- Call Hosting Ireland: +353 1 820 2580
- Email: support@hostingireland.ie
- Say: "I need to update the nameservers for fantasyfairways.ie"

### Step 9: Change Nameservers

1. Find the **"Nameservers"** section
2. You'll see current nameservers (probably like `ns1.hostingireland.ie`)
3. Select **"Custom Nameservers"** or **"Use Custom Nameservers"**
4. Replace with CloudFlare's nameservers:
   ```
   Nameserver 1: alan.ns.cloudflare.com
   Nameserver 2: erin.ns.cloudflare.com
   ```
   *(Replace with the actual nameservers CloudFlare gave you)*
5. Click **"Save"** or **"Update Nameservers"**

**⏱️ This change takes 2-48 hours to fully propagate**, but usually happens within 2-6 hours.

### Step 10: Verify in CloudFlare

1. Go back to CloudFlare tab
2. Click **"Done, check nameservers"**
3. CloudFlare will check if nameservers are updated

**If successful:**
- ✅ You'll see: "Great news! CloudFlare is now protecting your site"

**If pending:**
- ⏳ You'll see: "We're checking your nameservers..."
- CloudFlare will email you when it's active (can take up to 24 hours)
- You can continue to Part 4 in the meantime

---

## Part 4: Add Your Second Domain (fantasyfairways.co.uk)

### Step 11: Add Second Site to CloudFlare

Now repeat the process for your UK domain:

1. In CloudFlare dashboard, click **"Add a Site"** again
2. Enter: `fantasyfairways.co.uk`
3. Click **"Add Site"**
4. Select **"Free"** plan
5. Click **"Continue"**

### Step 12: Repeat DNS Configuration

Follow the same steps as above:
- Review DNS records CloudFlare found
- Enable **orange cloud** 🟠 for `@` and `www` A records
- Keep **grey cloud** ⚪ for email/TXT records
- Add any missing records manually
- Get CloudFlare nameservers (will be different ones!)

### Step 13: Update Nameservers at Hosting Ireland (Second Domain)

1. Log in to Hosting Ireland again
2. Go to **"My Domains"**
3. Find `fantasyfairways.co.uk`
4. Update nameservers to the new CloudFlare ones
   ```
   Nameserver 1: [New CloudFlare NS for .co.uk]
   Nameserver 2: [New CloudFlare NS for .co.uk]
   ```
5. Save changes

---

## Part 5: Configure CloudFlare Settings (Both Domains)

### Step 14: Enable SSL/TLS

**For fantasyfairways.ie:**

1. In CloudFlare dashboard, select `fantasyfairways.ie`
2. Go to **SSL/TLS** (left sidebar)
3. Set mode to **"Full (strict)"** if you have SSL on your server
   - OR **"Flexible"** if you don't have SSL yet
4. Scroll down to **"Edge Certificates"**
5. Enable:
   - ✅ **Always Use HTTPS**
   - ✅ **Automatic HTTPS Rewrites**
   - ✅ **HTTP Strict Transport Security (HSTS)** *(optional but recommended)*

**Repeat for fantasyfairways.co.uk**

### Step 15: Verify Proxy is Enabled

**For both domains:**

1. Go to **DNS** (left sidebar)
2. Verify these records have **orange cloud** 🟠:
   - `@` (root domain)
   - `www`

If any show grey cloud ⚪, click to toggle to orange 🟠

### Step 16: Test Geo-Detection Header

Once nameservers are active, test that CloudFlare is providing geo headers:

**Using cURL:**
```bash
curl -I https://fantasyfairways.ie
```

Look for:
```
cf-ray: 123456789abcdef-DUB
cf-ipcountry: IE
```

If you see `cf-ipcountry`, it's working! ✅

---

## Part 6: Configure Your Server/Heroku

### Step 17: Update Server Configuration

**If using Heroku:**

1. Add both domains to your Heroku app:
   ```bash
   heroku domains:add fantasyfairways.ie
   heroku domains:add www.fantasyfairways.ie
   heroku domains:add fantasyfairways.co.uk
   heroku domains:add www.fantasyfairways.co.uk
   ```

2. Get the DNS target Heroku provides (looks like `xyz.herokudns.com`)

3. In CloudFlare DNS settings for each domain:
   - Update the `@` A record to point to Heroku's IP
   - OR use a CNAME record pointing to `xyz.herokudns.com`

**If using another host:**
- Make sure your server is configured to accept requests from both domains
- Update virtual host configuration if needed

### Step 18: Enable SSL on Heroku

If using Heroku with CloudFlare:

1. Heroku will automatically provision SSL certificates
2. In CloudFlare SSL/TLS settings, use **"Full (strict)"** mode
3. This ensures end-to-end encryption

---

## Part 7: Enable Geo-Redirect in Your App

### Step 19: Set Environment Variables

In your production environment (Heroku):

```bash
heroku config:set GEO_REDIRECT_ENABLED=true
heroku config:set IE_DOMAIN=fantasyfairways.ie
heroku config:set UK_DOMAIN=fantasyfairways.co.uk
```

### Step 20: Deploy and Test

1. Deploy your app with the geo-redirect middleware
2. Visit `https://yourdomain.com/geo-redirect-test` as admin
3. Check that `CF-IPCountry` header is detected

---

## Testing Your Setup

### Test 1: Check DNS Propagation

```bash
# Check if nameservers are updated (on Windows)
nslookup -type=ns fantasyfairways.ie

# Should show CloudFlare nameservers
```

### Test 2: Check SSL

Visit both domains in browser:
- https://fantasyfairways.ie
- https://fantasyfairways.co.uk

Both should show:
- 🔒 Padlock icon (secure)
- Valid SSL certificate
- "Cloudflare Inc ECC CA-3" in certificate details

### Test 3: Check Geo-Headers

```bash
# Test IE domain
curl -I https://fantasyfairways.ie

# Test UK domain
curl -I https://fantasyfairways.co.uk
```

Both should return `cf-ipcountry` header.

### Test 4: Test Geo-Redirect

**Using VPN:**
1. Connect to UK VPN
2. Visit `https://fantasyfairways.ie`
3. Should redirect to `https://fantasyfairways.co.uk`

**Using cURL:**
```bash
# Simulate UK user visiting .ie domain
curl -H "CF-IPCountry: GB" -L https://fantasyfairways.ie

# Should redirect to .co.uk
```

---

## Troubleshooting

### Issue: Nameservers not updating

**Solution:**
- Wait 24-48 hours (DNS propagation can be slow)
- Contact Hosting Ireland support to verify change went through
- Check for domain lock status

### Issue: "Too many redirects" error

**Solutions:**
1. In CloudFlare, go to SSL/TLS
2. Change mode to **"Full"** instead of "Flexible"
3. Clear browser cache and cookies

### Issue: CloudFlare not detecting country

**Solutions:**
1. Verify orange cloud 🟠 is enabled for `@` and `www` records
2. Check SSL/TLS mode is set correctly
3. Wait 5-10 minutes after enabling proxy
4. Test from different device/network

### Issue: Site not loading at all

**Solutions:**
1. Check DNS records in CloudFlare are correct
2. Verify server IP is correct
3. Check CloudFlare isn't in "Under Attack" mode
4. Try grey cloud ⚪ temporarily to bypass CloudFlare

### Issue: Email stopped working

**Solution:**
- Make sure MX records have **grey cloud** ⚪ (DNS only)
- MX records should point to Hosting Ireland's mail servers
- Don't proxy email records!

---

## Important Notes

### ⚠️ Before Making Changes

1. **Backup current DNS records** - Write down ALL your current DNS settings from Hosting Ireland
2. **Note server IP** - You'll need this for CloudFlare DNS
3. **Check email settings** - Make sure you have MX records documented

### 📧 Email Configuration

**DO NOT proxy email records!**
- MX records → Grey cloud ⚪
- mail.yourdomain.com → Grey cloud ⚪

Email must go direct to Hosting Ireland, not through CloudFlare.

### 🕐 Propagation Time

- **Nameserver changes**: 2-48 hours (usually 4-6 hours)
- **DNS record changes**: 5 minutes to 24 hours
- **SSL certificate**: Instant to 24 hours

### 💰 Costs

- CloudFlare Free plan: **€0/month** (sufficient for your needs)
- Hosting Ireland: **No change** (keep your existing hosting)
- Domain registration: **Stay with Hosting Ireland** (no transfer needed)

---

## Quick Reference: Contact Information

**CloudFlare Support:**
- Help Center: https://support.cloudflare.com
- Community: https://community.cloudflare.com

**Hosting Ireland Support:**
- Phone: +353 1 820 2580
- Email: support@hostingireland.ie
- Website: https://www.hostingireland.ie

---

## Summary Checklist

- [ ] Sign up for CloudFlare account
- [ ] Add fantasyfairways.ie to CloudFlare
- [ ] Review and configure DNS records (.ie)
- [ ] Enable orange cloud for @ and www (.ie)
- [ ] Get CloudFlare nameservers (.ie)
- [ ] Update nameservers in Hosting Ireland (.ie)
- [ ] Add fantasyfairways.co.uk to CloudFlare
- [ ] Review and configure DNS records (.co.uk)
- [ ] Enable orange cloud for @ and www (.co.uk)
- [ ] Get CloudFlare nameservers (.co.uk)
- [ ] Update nameservers in Hosting Ireland (.co.uk)
- [ ] Enable SSL/TLS settings (both domains)
- [ ] Verify Always Use HTTPS is enabled
- [ ] Update Heroku domains (if applicable)
- [ ] Set GEO_REDIRECT_ENABLED=true in production
- [ ] Test geo-detection headers
- [ ] Test redirect with VPN
- [ ] Verify both domains load correctly
- [ ] Check email is still working

---

## Next Steps After Setup

Once CloudFlare is active and geo-redirect is working:

1. **Monitor Analytics** - CloudFlare provides traffic analytics
2. **Set up Page Rules** - Add custom caching rules (optional)
3. **Configure Firewall** - Set up security rules if needed
4. **Add Workers** - Use CloudFlare Workers for advanced features (optional)
5. **Enable Argo** - Speed up dynamic content (paid feature)

Your geo-redirect should now be fully operational! 🎉
