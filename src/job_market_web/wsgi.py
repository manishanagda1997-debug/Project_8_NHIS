"""WSGI entry point for Gunicorn in the Docker app container (decision D-038).

    gunicorn --workers 1 --threads 4 job_market_web.wsgi:app

Importing this module loads and verifies the current build and builds the
search index once (about 20 seconds). One worker process with several threads
keeps a single copy of the large read-only index in memory.
"""

from .app import create_app

app = create_app()
