#!/usr/bin/env python3
"""Fetch Granola meeting notes and transcripts.

Notes and transcripts both come from the Granola API.
Auth token is stored at ~/.config/granola-api/token.json (captured via Playwright).

Usage:
  python3 fetch_granola.py                  # List recent meetings
  python3 fetch_granola.py <meeting_number> # Show transcript for a meeting
  python3 fetch_granola.py --all            # Show all with transcripts
"""

import gzip
import json
import os
import sys
import time
import urllib.request

TOKEN_PATH = os.path.expanduser("~/.config/granola-api/token.json")


def get_token():
    if not os.path.exists(TOKEN_PATH):
        print("No token found. Run the Playwright auth flow to capture a token.", file=sys.stderr)
        print(f"Expected at: {TOKEN_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(TOKEN_PATH) as f:
        data = json.load(f)
    if data.get("expires_at", 0) < time.time():
        print("Token expired. Re-run the Playwright auth flow to get a fresh token.", file=sys.stderr)
        sys.exit(1)
    return data["access_token"]


def api_request(endpoint, payload, method="POST"):
    token = get_token()
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        f"https://api.granola.ai/{endpoint}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Granola/7.441.6",
            "X-Client-Version": "7.441.6",
        },
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        return json.loads(raw)


def fetch_documents(limit=10, offset=0):
    return api_request("v2/get-documents", {
        "limit": limit,
        "offset": offset,
        "include_last_viewed_panel": True,
    })


def fetch_transcript(document_id):
    try:
        return api_request("v1/get-document-transcript", {"document_id": document_id})
    except urllib.error.HTTPError:
        return None


def extract_text_from_prosemirror(node, depth=0):
    parts = []
    if isinstance(node, dict):
        ntype = node.get("type", "")
        if ntype == "text":
            text = node.get("text", "")
            marks = node.get("marks", [])
            if any(m.get("type") == "bold" for m in marks):
                text = f"**{text}**"
            parts.append(text)
        elif ntype == "heading":
            level = node.get("attrs", {}).get("level", 1)
            children = []
            for c in node.get("content", []):
                children.extend(extract_text_from_prosemirror(c, depth))
            parts.append("\n" + "#" * level + " " + "".join(children) + "\n")
            return parts
        elif ntype in ("bulletList", "orderedList"):
            for c in node.get("content", []):
                parts.extend(extract_text_from_prosemirror(c, depth + 1))
            return parts
        elif ntype == "listItem":
            children = []
            for c in node.get("content", []):
                children.extend(extract_text_from_prosemirror(c, depth))
            text = "".join(children).strip()
            parts.append("  " * depth + "- " + text + "\n")
            return parts
        elif ntype == "paragraph":
            children = []
            for c in node.get("content", []):
                children.extend(extract_text_from_prosemirror(c, depth))
            parts.extend(children)
            parts.append("\n")
            return parts
        for child in node.get("content", []):
            parts.extend(extract_text_from_prosemirror(child, depth))
    return parts


def format_transcript(segments):
    lines = []
    for seg in segments:
        ts = seg["start_timestamp"][11:19]
        source = seg.get("source", "unknown")
        prefix = "You" if source == "microphone" else "Speaker"
        lines.append(f"[{ts}] {prefix}: {seg['text']}")
    return "\n".join(lines)


def get_meeting_title(doc):
    cal_event = doc.get("google_calendar_event") or {}
    event_title = cal_event.get("summary") or cal_event.get("title")
    return event_title or doc.get("title") or "Untitled"


def print_meeting_list(documents):
    for i, doc in enumerate(documents):
        title = get_meeting_title(doc)
        created = doc.get("created_at", "unknown")[:10]
        print(f"  {i+1:>2}. {created}  {title}")
    print()
    print("  Run with a number to see transcript: python3 fetch_granola.py 1")


def print_meeting_detail(doc):
    title = get_meeting_title(doc)
    created = doc.get("created_at", "unknown")
    doc_id = doc.get("id", "")

    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"Date: {created}")
    attendees = (doc.get("people") or {}).get("attendees", [])
    if attendees:
        names = [a.get("name", a.get("email", "?")) for a in attendees]
        print(f"Attendees: {', '.join(names)}")
    print(f"{'='*60}")

    panel = doc.get("last_viewed_panel") or {}
    panel_content = panel.get("content")
    if panel_content:
        if isinstance(panel_content, str):
            try:
                panel_content = json.loads(panel_content)
            except json.JSONDecodeError:
                pass
        if isinstance(panel_content, dict):
            panel_text = "".join(extract_text_from_prosemirror(panel_content)).strip()
            if panel_text:
                print(f"\n--- AI Summary ---\n")
                print(panel_text)

    segments = fetch_transcript(doc_id)
    if segments:
        print(f"\n--- Transcript ({len(segments)} segments) ---\n")
        print(format_transcript(segments))
    else:
        print("\n[No transcript available]")


if __name__ == "__main__":
    result = fetch_documents(limit=15)
    documents = result.get("docs", [])

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--all":
            for doc in documents:
                print_meeting_detail(doc)
        else:
            try:
                idx = int(arg) - 1
                if 0 <= idx < len(documents):
                    print_meeting_detail(documents[idx])
                else:
                    print(f"Invalid number. Choose 1-{len(documents)}")
            except ValueError:
                print(f"Usage: python3 fetch_granola.py [number|--all]")
    else:
        print(f"\nRecent Granola Meetings ({len(documents)}):\n")
        print_meeting_list(documents)
