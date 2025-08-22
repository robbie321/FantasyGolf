import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_change_in_production'
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'a-different-super-secret-key'

    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = database_url or \
                              'postgresql://postgres:4bover2A!@localhost:5432/fantasy_league_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'uploads' # Still needed for the initial player CSV upload
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


    # NEW: Stripe API Keys (use test keys for development)
    # You would get these from your Stripe Dashboard
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY') or 'pk_test_51Rt4YFAAtiw6IkD3q6QEunjHZZIlhDBfKvpefcbEHafQqqKV0En2Eu5QJaxomlGgk4CYA8Jk9nBH9hQu3Amsstf800E0bzTL1S'
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY') or 'sk_test_51Rt4YFAAtiw6IkD3N2CNruve7zbaafKruqfMuJNeudIYNoL0eljrySxsoN9J2TGRDcYRCQFsRrz94roJF9hiaxXy00NwhqsECS'
    # For a real integration, you'd also need a webhook secret
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET') or 'whsec_YOUR_STRIPE_WEBHOOK_SECRET'

    # Data Golf API
    DATA_GOLF_API_KEY = os.environ.get('DATA_GOLF_API_KEY') or '6194d71ab637acf3eb7800202456'

    SPORTRADAR_API_KEY = os.environ.get('SPORTRADAR_API_KEY') or 'svKy6tuJCkFOnKfLcDokEHXT9hIEOrAE4U4Uwokx'


     # --- Email Server Configuration ---
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME','robmalone7@gmail.com') # Your email address
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'wehh kfob ejkj isfm') # Your email app password
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)


    # --- Redis and Caching Configuration ---
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CACHE_DEFAULT_TIMEOUT = 300 # Default cache timeout in seconds (5 minutes)

    TESTING_MODE_FLAG = 'testing_mode.flag'