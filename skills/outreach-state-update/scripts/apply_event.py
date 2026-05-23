#!/usr/bin/env python3
"""Apply a structured event to a canonical validation_state.md outreach log.

Single point of write authority. Aborts before writing if any preservation
check fails (file shrank, ### subsection lost, tail anchor lost, row delta
wrong). Events: NEW_SEND, REPLY_RECEIVED, CLOSE_LOOP, PATTERN_NOTE, CHASE_SENT.

This generalized outreach-starter-kit version tolerates HTML comments between
section headers and their structural content, and tolerates zero existing data
rows / bullets in a fresh template.
"""
import argparse, json, re, sys
from datetime import date, datetime
from pathlib import Path


_OPT_GAP = r"(?:[ \t]*\n|[ \t]*<!--[\s\S]*?-->[ \t]*\n)*"
_SENT_LOG_LOC = re.compile(r"(## Sent Log[^\n]*\n" + _OPT_GAP + r"\|[^\n]*\n\|---[^\n]*\n)")
_SENT_LOG_ROWS = re.compile(r"## Sent Log[^\n]*\n" + _OPT_GAP + r"\|[^\n]*\n\|---[^\n]*\n((?:\|[^\n]*\n)*)")
_ACTIVE_CONV_HEADER = re.compile(r"(## Active Conversations \(\d+\)\s*\n" + _OPT_GAP + r")")


def prose_date(iso):
    d = date.fromisoformat(iso)
    return str(d.month) + "/" + str(d.day)


def day_of_week(iso):
    return date.fromisoformat(iso).strftime("%A")


def _strip_html_comments(text):
    return re.sub(r"<!--[\s\S]*?-->", "", text)


def get_sent_log_rows(text):
    m = _SENT_LOG_ROWS.search(text)
    if not m:
        return []
    return [ln for ln in m.group(1).split("\n") if ln.startswith("|")]


def get_active_conv_bullets(text):
    m = _ACTIVE_CONV_HEADER.search(text)
    if not m:
        return []
    pos = m.end()
    bullets = []
    in_comment = False
    for line in text[pos:].split("\n"):
        stripped = line.strip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        if stripped == "":
            if bullets:
                break
            continue
        if line.startswith("- "):
            bullets.append(line)
            continue
        break
    return bullets


def get_active_conv_count(text):
    m = re.search(r"## Active Conversations \((\d+)\)", text)
    return int(m.group(1)) if m else None


def get_pattern_notes_subsections(text):
    m = re.search(r"## Pattern Notes\s*\n(.*)\Z", text, re.DOTALL)
    if not m:
        return []
    body_clean = _strip_html_comments(m.group(1))
    return re.findall(r"^### .*$", body_clean, re.MULTILINE)


def last_non_empty_line(text):
    for ln in reversed(text.splitlines()):
        if ln.strip():
            return ln
    return ""


def update_header(text, new_iso, signature):
    new_line = "**Stable path. Last updated: " + new_iso + " (" + day_of_week(new_iso) + ") by " + signature + ".**"
    return re.sub(r"\*\*Stable path\. Last updated: [^\n]+\*\*", new_line, text, count=1)


def prepend_sent_log_row(text, new_row):
    if not _SENT_LOG_LOC.search(text):
        raise ValueError("Sent Log table not found (header + column row + separator)")
    return _SENT_LOG_LOC.sub(lambda m: m.group(0) + new_row + "\n", text, count=1)


def adjust_active_conv_count(text, delta):
    m = re.search(r"## Active Conversations \((\d+)\)", text)
    if not m:
        raise ValueError("Active Conversations count not found")
    old_n = int(m.group(1))
    new_n = old_n + delta
    return text.replace(m.group(0), "## Active Conversations (" + str(new_n) + ")", 1), old_n, new_n


def append_active_conv_bullet(text, new_bullet):
    bullets = get_active_conv_bullets(text)
    header_m = _ACTIVE_CONV_HEADER.search(text)
    if not header_m:
        raise ValueError("Active Conversations heading not found")
    if bullets:
        last = bullets[-1]
        return text.replace(last + "\n", last + "\n" + new_bullet + "\n", 1)
    insert_pos = header_m.end()
    return text[:insert_pos] + new_bullet + "\n" + text[insert_pos:]


def _find_person_bullet(bullets, person):
    needle = person.lower().lstrip("@")
    exact = [b for b in bullets if re.match(r"- @?" + re.escape(needle) + r"\b", b, re.IGNORECASE)]
    if exact:
        return exact[0]
    loose = [b for b in bullets if needle in b.lower()]
    return loose[0] if loose else None


def update_active_conv_bullet(text, person, new_bullet):
    old = _find_person_bullet(get_active_conv_bullets(text), person)
    if not old:
        raise ValueError("No Active Conv bullet for " + person)
    return text.replace(old, new_bullet, 1)


def remove_active_conv_bullet(text, person):
    old = _find_person_bullet(get_active_conv_bullets(text), person)
    if not old:
        raise ValueError("No Active Conv bullet for " + person + " to remove")
    return text.replace(old + "\n", "", 1)


def mark_reply_in_sent_log(text, person, reply_prose, reply_summary=None):
    needle = person.lower().lstrip("@")
    def person_col(row):
        parts = row.split("|")
        return parts[2].strip().lower().lstrip("@") if len(parts) > 2 else ""
    rows = get_sent_log_rows(text)
    candidates = [r for r in rows if person_col(r) == needle]
    if not candidates:
        candidates = [r for r in rows if needle in person_col(r)]
    if not candidates:
        raise ValueError("No Sent Log row for " + person)
    target = candidates[0]
    parts = target.split("|")
    if len(parts) < 7:
        raise ValueError("Sent Log row missing columns")
    parts[5] = " OK " + reply_prose + " "
    if reply_summary:
        existing = parts[6].strip()
        snippet = reply_summary[:80]
        if existing and existing not in ("-", "Awaiting"):
            parts[6] = " " + existing + " | reply: " + snippet + " "
        else:
            parts[6] = " " + snippet + " "
    return text.replace(target, "|".join(parts), 1)


def append_closed_loop_entry(text, person, close_reason, lesson):
    m = re.search(r"(\*\*Closed-loop:\*\* )([^\n]+)", text)
    if not m:
        raise ValueError("No **Closed-loop:** line found")
    existing = m.group(2).rstrip(".")
    new_entry = person + " (" + close_reason + ", " + lesson + " lesson captured)"
    return text.replace(m.group(0), m.group(1) + existing + "; " + new_entry + ".", 1)


def append_archived_entry(text, person):
    m = re.search(r"(\*\*Archived:\*\* )([^\n]+)", text)
    if not m:
        raise ValueError("No **Archived:** line found")
    existing = m.group(2).rstrip(".")
    return text.replace(m.group(0), m.group(1) + existing + ", " + person + ".", 1)


def prepend_pattern_notes_subsection(text, new_subsection):
    subs = get_pattern_notes_subsections(text)
    if not subs:
        return text.replace("## Pattern Notes\n", "## Pattern Notes\n\n" + new_subsection + "\n", 1)
    return text.replace(subs[0], new_subsection + "\n" + subs[0], 1)


def event_new_send(text, p, signature):
    notes = "; ".join(filter(None, [p.get("hook_used", ""), p.get("notes_for_followup", "")])) or "-"
    needle = p["person"].lower().lstrip("@")
    if [r for r in get_sent_log_rows(text) if p["date"] in r and needle in r.lower()]:
        raise ValueError("DUPLICATE: row for " + p["person"] + " on " + p["date"])
    new_row = "| " + p["date"] + " | " + p["person"] + " | " + p["persona"] + " | " + p["channel"] + " | - | " + notes + " |"
    text = prepend_sent_log_row(text, new_row)
    new_bullet = "- " + p["person"] + " - Persona " + p["persona"] + " " + p["channel"] + ", first send " + prose_date(p["date"])
    text = append_active_conv_bullet(text, new_bullet)
    text, old_n, new_n = adjust_active_conv_count(text, +1)
    text = update_header(text, p["date"], signature)
    return text, {"new_row": new_row, "new_bullet": new_bullet, "active_conv": str(old_n) + " -> " + str(new_n)}


def event_reply_received(text, p, signature):
    today = p.get("today") or datetime.now().date().isoformat()
    prose = prose_date(today)
    summary = p.get("reply_summary", "")
    rtype = p.get("reply_type", "")
    snippet = rtype + ": " + summary if summary else None
    text = mark_reply_in_sent_log(text, p["person"], prose, reply_summary=snippet)
    old = _find_person_bullet(get_active_conv_bullets(text), p["person"])
    if old:
        prefix_m = re.match(r"(- [^-]+) -", old)
        prefix = prefix_m.group(1) if prefix_m else "- " + p["person"]
        new_bullet = prefix + " - reply " + prose + " (" + rtype + ", " + summary[:80] + ")"
        text = update_active_conv_bullet(text, p["person"], new_bullet)
    text = update_header(text, today, signature)
    return text, {"reply_marker": "OK " + prose, "today": today}


def event_pattern_note(text, p, signature):
    label = p.get("label", "").strip()
    heading = "### " + p["date"] + " - " + label if label else "### " + p["date"]
    new_sub = (heading + "\n\n" + "**Pattern:** " + p["pattern_observed"] + "\n\n" +
               "**Signal value:** " + p["signal_value"] + "\n\n" +
               "**Implications for next week:** " + p["implications_for_next_week"] + "\n")
    before = get_pattern_notes_subsections(text)
    text = prepend_pattern_notes_subsection(text, new_sub)
    text = update_header(text, p["date"], signature)
    return text, {"new_heading": heading, "preserved_subsections": before}


def event_close_loop(text, p, signature):
    today = p.get("today") or datetime.now().date().isoformat()
    text = remove_active_conv_bullet(text, p["person"])
    text, old_n, new_n = adjust_active_conv_count(text, -1)
    text = append_closed_loop_entry(text, p["person"], p["close_reason"], p["lesson_captured"])
    text = append_archived_entry(text, p["person"])
    text = update_header(text, today, signature)
    return text, {"active_conv": str(old_n) + " -> " + str(new_n), "today": today}


def event_chase_sent(text, p, signature):
    needle = p["person"].lower().lstrip("@")
    rows = get_sent_log_rows(text)
    matching = [r for r in rows if needle in r.lower()]
    chase_n = sum(1 for r in matching if "chase" in r.lower()) + 1
    if matching:
        parts = matching[-1].split("|")
        persona = parts[3].strip() if len(parts) > 3 else "?"
        channel = parts[4].strip() if len(parts) > 4 else "unknown"
    else:
        persona, channel = "?", "unknown"
    new_row = "| " + p["chase_date"] + " | " + p["person"] + " | " + persona + " | " + channel + " chase #" + str(chase_n) + " | - | Fresh hook: " + p["fresh_hook_used"][:100] + " |"
    text = prepend_sent_log_row(text, new_row)
    new_bullet = "- " + p["person"] + " - Persona " + persona + " " + channel + ", chase #" + str(chase_n) + " sent " + prose_date(p["chase_date"])
    try:
        text = update_active_conv_bullet(text, p["person"], new_bullet)
    except ValueError:
        pass
    text = update_header(text, p["chase_date"], signature)
    return text, {"new_row": new_row, "chase_number": chase_n}


HANDLERS = {"NEW_SEND": event_new_send, "REPLY_RECEIVED": event_reply_received,
            "CLOSE_LOOP": event_close_loop, "PATTERN_NOTE": event_pattern_note,
            "CHASE_SENT": event_chase_sent}
SL_DELTA = {"NEW_SEND": 1, "CHASE_SENT": 1, "REPLY_RECEIVED": 0, "CLOSE_LOOP": 0, "PATTERN_NOTE": 0}
AC_DELTA = {"NEW_SEND": 1, "CLOSE_LOOP": -1}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True)
    ap.add_argument("--signature", required=True)
    ap.add_argument("--event", required=True, choices=list(HANDLERS.keys()))
    ap.add_argument("--payload", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print("ERROR: File not found: " + str(path), file=sys.stderr)
        sys.exit(2)

    original = path.read_text(encoding="utf-8")
    payload = json.loads(args.payload)
    pn_before = get_pattern_notes_subsections(original)
    sl_before = len(get_sent_log_rows(original))
    ac_before = get_active_conv_count(original)
    tail_before = last_non_empty_line(original)
    len_before = len(original)

    try:
        new_text, summary = HANDLERS[args.event](original, payload, args.signature)
    except Exception as e:
        print("ERROR applying event: " + str(e), file=sys.stderr)
        sys.exit(3)

    pn_after = get_pattern_notes_subsections(new_text)
    sl_after = len(get_sent_log_rows(new_text))
    ac_after = get_active_conv_count(new_text)
    len_after = len(new_text)

    issues = []
    if sl_after - sl_before != SL_DELTA[args.event]:
        issues.append("Sent Log delta wrong: " + str(sl_before) + " -> " + str(sl_after))
    for sub in pn_before:
        if sub not in new_text:
            issues.append("Pattern Notes subsection LOST: " + sub)
    if tail_before and tail_before not in new_text:
        issues.append("Tail anchor LOST: " + tail_before[:80])
    if args.event == "CLOSE_LOOP":
        if len_after < len_before - 500:
            issues.append("File shrank too much for CLOSE_LOOP")
    else:
        if len_after <= len_before:
            issues.append("File did not grow (append-only event)")
    if ac_before is not None and ac_after is not None:
        expected = AC_DELTA.get(args.event, 0)
        if ac_after - ac_before != expected:
            issues.append("Active Conv delta wrong: " + str(ac_before) + " -> " + str(ac_after))

    if issues:
        print("ABORT - preservation checks failed:", file=sys.stderr)
        for i in issues:
            print("  - " + i, file=sys.stderr)
        sys.exit(4)

    if args.dry_run:
        print("DRY RUN - " + args.event + " would apply cleanly.")
        print("  bytes: " + str(len_before) + " -> " + str(len_after))
        print(json.dumps(summary, indent=2))
        return

    path.write_text(new_text, encoding="utf-8")
    print("OK " + args.event + " applied to " + path.name)
    for k, v in summary.items():
        print("  " + k + ": " + str(v))
    print("  bytes: " + str(len_before) + " -> " + str(len_after))


if __name__ == "__main__":
    main()
