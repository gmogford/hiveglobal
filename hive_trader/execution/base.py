"""Execution venue interface. Only the loop calls this, and only after RiskManager.pre_trade_check."""
from __future__ import annotations

from typing import Protocol

from ..types import BookUpdate, Fill, Order


class Venue(Protocol):
    name: str

    def submit(self, order: Order, book: BookUpdate) -> list[Fill]:
        """Submit a marketable-limit IOC order. Returns fills (possibly partial, possibly none)."""
        ...


class LiveVenueNotApproved(RuntimeError):
    pass


class LiveVenue:
    """Placeholder for a real venue adapter (Phase 6 / Ship gate).

    Deliberately not implemented: a live adapter must be written against the chosen
    venue's current API docs, tested on its testnet, and pass the G5 gate
    (docs/00_AGENKIT_PHASES.md) before this class may return fills.
    """
    name = "live"

    def submit(self, order: Order, book: BookUpdate) -> list[Fill]:
        raise LiveVenueNotApproved("live execution is not implemented/approved; use PaperVenue")
