"""
Geo-based domain redirection middleware for Fantasy Fairways.
Redirects UK users to .co.uk domain and IE users to .ie domain.
"""

from flask import request, redirect
import logging

logger = logging.getLogger(__name__)


class GeoRedirectMiddleware:
    """
    Middleware to redirect users to the appropriate domain based on their location.

    Uses CloudFlare headers or other geo-location headers to determine user location.
    Falls back to IP-based detection if headers are not available.
    """

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the middleware with Flask app"""
        self.app = app

        # Domain configuration
        self.ie_domain = app.config.get('IE_DOMAIN', 'fantasyfairway.ie')
        self.uk_domain = app.config.get('UK_DOMAIN', 'fantasyfairway.co.uk')
        self.redirect_enabled = app.config.get('GEO_REDIRECT_ENABLED', True)

        # Register before_request handler
        app.before_request(self.check_geo_redirect)

    def get_user_country(self):
        """
        Detect user's country from request headers.

        Priority order:
        1. CloudFlare CF-IPCountry header
        2. Custom X-Country header (if set by load balancer)
        3. GeoIP lookup (if implemented)
        4. Default to None
        """
        # CloudFlare provides CF-IPCountry header
        country = request.headers.get('CF-IPCountry')

        if country:
            logger.debug(f"Country detected from CF-IPCountry: {country}")
            return country.upper()

        # Check for custom header (if you set one in your infrastructure)
        country = request.headers.get('X-Country')
        if country:
            logger.debug(f"Country detected from X-Country: {country}")
            return country.upper()

        # You can add additional geo-location methods here
        # For example, using a GeoIP library like geoip2:
        # ip = self.get_client_ip()
        # country = self.lookup_country_by_ip(ip)

        logger.debug("No country detected from headers")
        return None

    def get_client_ip(self):
        """Get the real client IP, accounting for proxies"""
        # Check X-Forwarded-For header (set by proxies)
        if request.headers.get('X-Forwarded-For'):
            # Get the first IP in the chain (client's real IP)
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()

        # Check CF-Connecting-IP (CloudFlare)
        if request.headers.get('CF-Connecting-IP'):
            return request.headers.get('CF-Connecting-IP')

        # Fallback to remote_addr
        return request.remote_addr

    def get_current_domain(self):
        """Get the current domain from the request"""
        return request.host.lower()

    def should_redirect(self, country, current_domain):
        """
        Determine if user should be redirected based on their country and current domain.

        Rules:
        - UK users should be on .co.uk
        - IE users should be on .ie
        - Other users can access either (no redirect)
        """
        if not country:
            return None

        # UK users should be on .co.uk domain
        if country == 'GB' or country == 'UK':
            if self.uk_domain not in current_domain:
                return self.uk_domain

        # IE users should be on .ie domain
        elif country == 'IE':
            if self.ie_domain not in current_domain:
                return self.ie_domain

        # No redirect needed
        return None

    def check_geo_redirect(self):
        """
        Check if geo-redirect is needed and perform redirect if necessary.
        This is called before every request.
        """
        # Skip if geo-redirect is disabled
        if not self.redirect_enabled:
            return None

        # Skip redirect for certain paths (API endpoints, webhooks, static files)
        skip_paths = [
            '/api/',
            '/webhook/',
            '/static/',
            '/_debug',
            '/health',
        ]

        if any(request.path.startswith(path) for path in skip_paths):
            return None

        # Skip redirect for POST requests (to avoid breaking forms)
        if request.method != 'GET':
            return None

        # Check if user has already been redirected (to prevent redirect loops)
        if request.cookies.get('geo_redirected'):
            return None

        # Get user's country
        country = self.get_user_country()

        # Get current domain
        current_domain = self.get_current_domain()

        # Check if redirect is needed
        target_domain = self.should_redirect(country, current_domain)

        if target_domain:
            # Build redirect URL
            scheme = request.scheme
            path = request.full_path if request.query_string else request.path
            redirect_url = f"{scheme}://{target_domain}{path}"

            logger.info(f"Redirecting {country} user from {current_domain} to {target_domain}")

            # Create response with redirect
            response = redirect(redirect_url, code=302)

            # Set cookie to prevent redirect loop (expires in 30 days)
            response.set_cookie(
                'geo_redirected',
                '1',
                max_age=30*24*60*60,  # 30 days
                domain=f'.{target_domain.split(".")[-2]}.{target_domain.split(".")[-1]}',  # Set for all subdomains
                secure=request.is_secure,
                httponly=True,
                samesite='Lax'
            )

            return response

        return None


def init_geo_redirect(app):
    """Initialize geo-redirect middleware"""
    GeoRedirectMiddleware(app)
