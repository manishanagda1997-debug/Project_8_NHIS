"""Pipeline steps, in execution order.

Each step module exposes ``NAME``, ``DESCRIPTION`` and ``run(settings, context)``.
``run`` returns a ``StepRecord`` with the files it writes and its headline
metrics. Later stages of the project add their steps to ``STEPS``.
"""

from . import categorize, clean, evaluate, forecast, ingest, monitor, pay, recommend, trends

STEPS = (ingest, clean, categorize, evaluate, pay, trends, forecast, recommend, monitor)

__all__ = ["STEPS"]
