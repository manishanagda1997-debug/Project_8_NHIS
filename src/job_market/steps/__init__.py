"""Pipeline steps, in execution order.

Each step module exposes ``NAME``, ``DESCRIPTION`` and ``run(settings, context)``.
``run`` returns a ``StepRecord`` with the files it writes and its headline
metrics. Later stages of the project add their steps to ``STEPS``.
"""

from . import categorize, clean, ingest

STEPS = (ingest, clean, categorize)

__all__ = ["STEPS"]
