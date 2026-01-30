import os 
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# 1. SETUP PATHS FOR PHOENIX STRUCTURE
# __file__ is project_root/alembic/env.py
# PHOENIX_ROOT is project_root/
PHOENIX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# BACKEND_PATH is project_root/backend/
BACKEND_PATH = os.path.join(PHOENIX_ROOT, "backend")

# Inject these into Python's search path
sys.path.insert(0, PHOENIX_ROOT)
sys.path.insert(0, BACKEND_PATH)

# 2. NOW IMPORTS WILL WORK
# Python looks in 'backend' and finds the 'app' folder
from app.models import User, Automation, DMLog, Referral, WebhookLog, RateLimitTracker
from app.database import Base 
from app.config import settings

# 3. ALEMBIC CONFIG
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the URL from your settings (Supabase URL)
config.set_main_option("sqlalchemy.url", settings.DIRECT_DATABASE_URL)

target_metadata = Base.metadata

# ... rest of the standard run_migrations_offline/online functions ...

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            compare_type=True 
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
