"""Backend core — auth, config, fetch, parser, store, export."""

from .parser import DutyEntry, ParseError, parse_roster

__all__ = ["DutyEntry", "ParseError", "parse_roster"]
