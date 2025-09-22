# Create a file called test_redis.py and run it to test Redis connection

import redis
import os

def test_redis_connection():
    redis_urls_to_try = [
        'redis://localhost:6379/0',
        'redis://127.0.0.1:6379/0',
        'redis://localhost:6379',
        'redis://127.0.0.1:6379'
    ]

    for url in redis_urls_to_try:
        try:
            print(f"Trying to connect to: {url}")
            r = redis.from_url(url)
            r.ping()
            print(f"✅ SUCCESS: Connected to {url}")

            # Test basic operations
            r.set('test_key', 'test_value')
            value = r.get('test_key')
            r.delete('test_key')

            print(f"✅ Read/Write test passed: {value}")
            return True

        except Exception as e:
            print(f"❌ FAILED: {url} - {e}")
            continue

    print("❌ No Redis connection found")
    return False

if __name__ == "__main__":
    print("Testing Redis connections...")
    print("=" * 40)

    if test_redis_connection():
        print("\n🎉 Redis is working! You can use Celery with Redis.")
        print("Run your Celery commands as normal.")
    else:
        print("\n⚠️  Redis is not available.")
        print("Options:")
        print("1. Install Redis for Windows from: https://github.com/microsoftarchive/redis/releases")
        print("2. Use Docker: docker run -d -p 6379:6379 redis:alpine")
        print("3. Switch to memory broker for development (loses tasks on restart)")
        print("4. Work on Heroku where Redis is available")