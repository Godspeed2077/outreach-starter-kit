"""
Parses an outreach validation_state.md Sent Log into structured Python.

Two-pass parse:
  1. Pull every row into SentEntry objects.
  2. Backfill the `email` field for follow-up rows (reply #2, chase #1,
     close-out) by looking up the email used on the same person's earliest row.

State file path is read from the OUTREACH_STATE_FILE environment variable.
The kit's setup README explains how to set this (per-session env var, or
permanent via shell profile).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


_STATE_FILE_ENV = "OUTREACH_STATE_FILE"


def _resolve_state_file() -> Path:
    raw = os.environ.get(_STATE_FILE_ENV)
    if not raw:
        raise RuntimeError(
            f"{_STATE_FILE_ENV} environment variable is not set. "
            "Set it to the absolute path of your validation_state.md."
        )
    return Path(raw)


CLOSED_MARKERS = ("CLOSED", "BOUNCED", "ARCHIVED", "SOFT-ARCHIVED", "DROPPED")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_REPLY_SUFFIX_RE = re.compile(
    r"\s*[—\-]\s*(reply\s*#?\d+|chase\s*#?\d+|close[\-\s]*out)\s*$",
    re.IGNORECASE,
)


@dataclass
class SentEntry:
    date: str
    person: str
    persona: str
    channel: str
    reply_status: str
    notes: str
    email: str | None
    is_awaiting: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _split_concatenated_row(line: str) -> list[str]:
    raw_segments = [seg for seg in line.split("||") if seg.strip()]
    if len(raw_segments) <= 1:
        return raw_segments
    fixed: list[str] = []
    for i, seg in enumerate(raw_segments):
        s = seg
        if i > 0 and not s.lstrip().startswith("|"):
            s = "|" + s.lstrip()
        if i < len(raw_segments) - 1 and not s.rstrip().endswith("|"):
            s = s.rstrip() + "|"
        fixed.append(s)
    return fixed


def _normalize_row(row: str) -> list[str] | None:
    row = row.strip()
    if not row.startswith("|") or not row.endswith("|"):
        return None
    cells = [c.strip() for c in row.strip("|").split("|")]
    if len(cells) != 6:
        return None
    if cells[0].lower() == "date" or set(cells[0]) <= set("-: "):
        return None
    return cells


def _is_closed(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in CLOSED_MARKERS)


def _is_awaiting(reply_status: str, notes: str) -> bool:
    if _is_closed(reply_status) or _is_closed(notes):
        return False
    return reply_status.strip() in ("—", "-", "")


def _extract_email(*candidates: str) -> str | None:
    for c in candidates:
        m = EMAIL_RE.search(c)
        if m:
            return m.group(0)
    return None


def _canonical_person(person: str) -> str:
    return _REPLY_SUFFIX_RE.sub("", person).strip().lower()


def parse_sent_log(state_md_text: str) -> list[SentEntry]:
    # Anchor to start-of-line so we don't match "## Sent Log" mentioned in prose.
    header_match = re.search(r"^## Sent Log", state_md_text, re.MULTILINE)
    if not header_match:
        raise ValueError("Sent Log section not found in state file.")
    start = header_match.end()

    rest = state_md_text[start:]
    next_section_idx = rest.find("\n## ")
    table_text = rest if next_section_idx == -1 else rest[:next_section_idx]

    entries: list[SentEntry] = []
    for raw_line in table_text.splitlines():
        for segment in _split_concatenated_row(raw_line):
            cells = _normalize_row(segment)
            if cells is None:
                continue
            date, person, persona, channel, reply_status, notes = cells
            email = _extract_email(channel, notes)
            entries.append(
                SentEntry(
                    date=date,
                    person=person,
                    persona=persona,
                    channel=channel,
                    reply_status=reply_status,
                    notes=notes,
                    email=email,
                    is_awaiting=_is_awaiting(reply_status, notes),
                )
            )

    canonical_to_email: dict[str, str] = {}
    for e in entries:
        if e.email:
            key = _canonical_person(e.person)
            canonical_to_email.setdefault(key, e.email)
    for e in entries:
        if not e.email:
            key = _canonical_person(e.person)
            if key in canonical_to_email:
                e.email = canonical_to_email[key]

    return entries


def awaiting_email_entries(entries: Iterable[SentEntry]) -> list[SentEntry]:
    return [e for e in entries if e.is_awaiting and e.email]


def load_from_disk() -> list[SentEntry]:
    state_file = _resolve_state_file()
    text = state_file.read_text(encoding="utf-8")
    return parse_sent_log(text)


def _main() -> None:
    all_entries = load_from_disk()
    awaiting = awaiting_email_entries(all_entries)
    print("Total Sent Log entries:", len(all_entries))
    print("Awaiting reply with usable email:", len(awaiting))
    print()
    print("Awaiting watch-list:")
    for e in awaiting:
        print("  ", e.date.ljust(20), e.person[:48].ljust(48), e.email)


if __name__ == "__main__":
    _main()
