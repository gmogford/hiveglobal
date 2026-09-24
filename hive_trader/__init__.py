"""hive_trader: BRAIN/REFLEX crypto trading system.

Layering rule (enforced by structure, checked by tests):
  * state_engine, risk, policy, execution  -> deterministic code, own every number and side effect
  * jev                                     -> scores/classifies only; returns typed answers, never sizes or executes
  * review                                  -> offline; proposes changes, never applies them to the live config
"""

__version__ = "0.1.0"
