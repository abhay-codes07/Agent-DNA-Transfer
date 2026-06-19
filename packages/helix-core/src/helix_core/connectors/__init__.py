"""Ingestion connectors (v2 plan §5.6) — distill durable facts from the sources a coding agent
should know about. Local-first by default: connectors read what the user points them at and emit
*facts*, never raw dumps. The GitHub App (webhooks) is the hosted extension of `repo`."""

from __future__ import annotations

__all__ = ["repo"]
