"""Web interface: the Flask app around the tested recommender (decision D-035).

This package is a presentation layer only. It reads the verified outputs of
the current build and calls ``job_market.recommend``; it never recomputes an
analysis. It lives outside ``job_market`` so that changing the page does not
change the analysis code fingerprint.
"""

from .app import create_app

__all__ = ["create_app"]
