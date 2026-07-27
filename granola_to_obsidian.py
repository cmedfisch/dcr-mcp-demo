#!/usr/bin/env python3
"""Export Granola meeting notes and transcripts to Obsidian vault.

Runs standalone - reads auth token from ~/.config/granola-api/token.json
(captured via Playwright), fetches recent meetings and transcripts via API,
and writes markdown files to the Obsidian vault.
Skips meetings that have already been exported (by granola_id in frontmatter).
"""

import gzip
import json
import os
import re
import sys
import time
import urllib.request

TOKEN_PATH = os.path.expanduser("~/.config/granola-api/token.json")
OUT_DIR = "/Users/medfisch/Library/Mobile Documents/iCloud~md~obsidian/Documents/My Vault/📥 INBOX/Meeting Summaries"
FETCH_LIMIT = 15


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


def api_request(endpoint, payload):
    token = get_token()
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.granola.ai/{endpoint}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Granola/7.441.6",
            "X-Client-Version": "7.441.6",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw)


def fetch_documents(limit=FETCH_LIMIT):
    return api_request("v2/get-documents", {
        "limit": limit,
        "offset": 0,
        "include_last_viewed_panel": True,
    })


def fetch_transcript(document_id):
    try:
        return api_request("v1/get-document-transcript", {"document_id": document_id})
    except urllib.error.HTTPError:
        return None


def extract_text(node, depth=0):
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
                children.extend(extract_text(c, depth))
            parts.append("\n" + "#" * level + " " + "".join(children) + "\n")
            return parts
        elif ntype in ("bulletList", "orderedList"):
            for c in node.get("content", []):
                parts.extend(extract_text(c, depth + 1))
            return parts
        elif ntype == "listItem":
            children = []
            for c in node.get("content", []):
                children.extend(extract_text(c, depth))
            text = "".join(children).strip()
            parts.append("  " * depth + "- " + text + "\n")
            return parts
        elif ntype == "paragraph":
            children = []
            for c in node.get("content", []):
                children.extend(extract_text(c, depth))
            parts.extend(children)
            parts.append("\n")
            return parts
        for child in node.get("content", []):
            parts.extend(extract_text(child, depth))
    return parts


def safe_filename(s):
    s = re.sub(r'[/:*?"<>|]', "", s)
    return s[:80].strip()


def get_existing_granola_ids(out_dir):
    """Scan existing files for granola_id in frontmatter to avoid duplicates."""
    ids = set()
    if not os.path.exists(out_dir):
        return ids
    for fname in os.listdir(out_dir):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(out_dir, fname)
        try:
            with open(filepath) as f:
                for line in f:
                    if line.startswith("granola_id:"):
                        ids.add(line.split(":", 1)[1].strip())
                        break
                    if line.strip() == "---" and len(ids) == 0:
                        continue
                    if not line.startswith(("---", "date:", "type:", "source:", "granola_id:")):
                        break
        except Exception:
            continue
    return ids


def build_markdown(doc, transcript_segments):
    cal_event = doc.get("google_calendar_event") or {}
    title = cal_event.get("summary") or cal_event.get("title") or doc.get("title") or "Untitled"
    created = doc.get("created_at", "")[:10]
    doc_id = doc.get("id", "")

    lines = [
        "---",
        f"date: {created}",
        "type: meeting",
        "source: granola",
        f"granola_id: {doc_id}",
        "---",
        "",
        f"# {title}",
        "",
        f"**Date:** {created}",
    ]

    attendees = (doc.get("people") or {}).get("attendees", [])
    if attendees:
        names = [a.get("name", a.get("email", "?")) for a in attendees]
        lines.append(f"**Attendees:** {', '.join(names)}")
    lines.append("")

    panel = doc.get("last_viewed_panel") or {}
    panel_content = panel.get("content")
    if panel_content:
        if isinstance(panel_content, str):
            try:
                panel_content = json.loads(panel_content)
            except json.JSONDecodeError:
                pass
        if isinstance(panel_content, dict):
            panel_text = "".join(extract_text(panel_content)).strip()
            if panel_text:
                lines.extend(["## Summary", "", panel_text, ""])

    md = (doc.get("notes_markdown") or "").strip()
    plain = (doc.get("notes_plain") or "").strip()
    if md:
        lines.extend(["## Notes", "", md, ""])
    elif plain:
        lines.extend(["## Notes", "", plain, ""])

    if transcript_segments:
        lines.append(f"## Transcript ({len(transcript_segments)} segments)")
        lines.append("")
        for seg in transcript_segments:
            ts = seg["start_timestamp"][11:19]
            source = seg.get("source", "unknown")
            prefix = "You" if source == "microphone" else "Speaker"
            lines.append(f"[{ts}] {prefix}: {seg['text']}")
        lines.append("")

    return title, "\n".join(lines)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    existing_ids = get_existing_granola_ids(OUT_DIR)
    result = fetch_documents()
    documents = result.get("docs", [])

    new_count = 0
    updated_count = 0

    for doc in documents:
        doc_id = doc.get("id", "")
        created = doc.get("created_at", "")[:10]

        transcript_segments = fetch_transcript(doc_id)

        title, content = build_markdown(doc, transcript_segments)
        filename = f"{created} {safe_filename(title)}.md"
        filepath = os.path.join(OUT_DIR, filename)

        if doc_id in existing_ids:
            try:
                with open(filepath) as f:
                    old = f.read()
                if old != content:
                    with open(filepath, "w") as f:
                        f.write(content)
                    updated_count += 1
                    print(f"Updated: {filename}")
            except FileNotFoundError:
                with open(filepath, "w") as f:
                    f.write(content)
                updated_count += 1
                print(f"Updated (renamed): {filename}")
        else:
            with open(filepath, "w") as f:
                f.write(content)
            new_count += 1
            print(f"New: {filename}")

    if new_count == 0 and updated_count == 0:
        print("No new or updated meetings.")
    else:
        print(f"\nDone: {new_count} new, {updated_count} updated")


if __name__ == "__main__":
    main()
