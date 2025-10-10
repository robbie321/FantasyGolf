from flask import current_app
from fantasy_league_app.extensions import cache
import json
import hashlib
from functools import wraps
from datetime import datetime

class CacheManager:
    """Centralized cache management with consistent key naming and timeouts"""

    @staticmethod
    def make_key(*args, prefix=''):
        """Create consistent cache keys"""
        key_parts = [str(arg) for arg in args if arg is not None]
        key = f"{current_app.config['CACHE_KEY_PREFIX']}{prefix}:{'_'.join(key_parts)}"
        return key

    @staticmethod
    def get_timeout(cache_type):
        """Get timeout for specific cache type"""
        return current_app.config['CACHE_TIMEOUTS'].get(cache_type, 300)

    @staticmethod
    def cache_key_for_user_leagues(user_id):
        return CacheManager.make_key('user_leagues', user_id, prefix='user_data')

    @staticmethod
    def cache_key_for_league_entries(league_id):
        return CacheManager.make_key('league_entries', league_id, prefix='league_data')

    @staticmethod
    def cache_key_for_player_scores(tour):
        return CacheManager.make_key('player_scores', tour, prefix='player_scores')

    @staticmethod
    def cache_key_for_leaderboard(league_id):
        return CacheManager.make_key('leaderboard', league_id, prefix='leaderboards')

def cache_result(cache_type, key_func=None, timeout=None):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default key generation
                args_str = '_'.join(str(arg) for arg in args)
                kwargs_str = '_'.join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
                cache_key = CacheManager.make_key(func.__name__, args_str, kwargs_str, prefix=cache_type)

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_timeout = timeout or CacheManager.get_timeout(cache_type)
            cache.set(cache_key, result, timeout=cache_timeout)

            return result
        return wrapper
    return decorator

def get_league_cache_timeout(league):
    """Return different cache timeouts based on league status"""
    if league.is_finalized:
        return 3600 * 24  # 24 hours for finalized leagues
    else:
        return 120  # 2 minutes for live leagues