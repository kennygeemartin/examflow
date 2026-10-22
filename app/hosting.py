"""Initialize shared durable storage for serverless deployments."""
import os
import threading

from domain import Store

_lock = threading.Lock()


def hosted_store():
    url = os.environ.get('DATABASE_URL', '')
    if not url.startswith(('postgres://', 'postgresql://')):
        raise ValueError('Connect a PostgreSQL database in Vercel Storage and configure DATABASE_URL, then redeploy.')
    with _lock:
        store = Store(url)
        if os.environ.get('EXAMFLOW_DEMO') == 'true':
            from seed import seed
            seed(store)
        else:
            with store.db() as db:
                if not db.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                    password = os.environ.get('EXAMFLOW_ADMIN_PASSWORD', '')
                    if len(password) < 10:
                        raise ValueError('Set EXAMFLOW_ADMIN_PASSWORD to a unique password of at least 10 characters, then redeploy.')
                    store.add_user(db, os.environ.get('EXAMFLOW_ADMIN_ID', 'admin'), os.environ.get('EXAMFLOW_ADMIN_NAME', 'Administrator'), 'administrator', password)
        return store
