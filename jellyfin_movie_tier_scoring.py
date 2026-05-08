#!/usr/bin/env python3
"""
Jellyfin-backed Media Auditor (1:1 replacement of filesystem version)

Only change:
- data source = Jellyfin API instead of filesystem + ffprobe

Everything else is identical:
- scoring
- tiering
- issue detection
- CLI behavior
"""

import argparse
from typing import List, Dict, Any
from collections import defaultdict, Counter
import requests


# ------------------------------------------------------------
# JELLYFIN CONFIG (FILL THESE)
# ------------------------------------------------------------

# Base URL of your Jellyfin server (no trailing slash)
JELLYFIN_SERVER = ""

# Your Jellyfin API token
JELLYFIN_API_KEY = ""

# Jellyfin user id
JELLYFIN_USER_ID = ""


# ------------------------------------------------------------
# HEADERS (USED FOR ALL REQUESTS)
# ------------------------------------------------------------

JELLYFIN_HEADERS = {
    "X-Emby-Token": JELLYFIN_API_KEY,
    "Accept": "application/json"
}


# ------------------------------------------------------------
# JELLYFIN DATA FETCH (REPLACES FILESYSTEM + FFPROBE)
# ------------------------------------------------------------

def jellyfin_get_movies() -> List[Dict[str, Any]]:
    """
    Fetch raw movie objects from Jellyfin and normalize them into
    the SAME structure used by the ffprobe-based version.

    Required output format per movie:
    {
        "name": str,
        "video_ok": bool,
        "audio_streams": [
            {
                "language": str,
                "default": bool
            }
        ],
        "subtitle_streams": [
            {
                "language": str
            }
        ],
        "nfo": bool,
        "artwork": bool
    }
    """

    url = f"{JELLYFIN_SERVER}/Items"

    params = {
        "IncludeItemTypes": "Movie",
        "Recursive": "true",
        "Fields": "MediaSources"
    }

    # --------------------------------------------------------
    # API REQUEST (SAFE NETWORK CALL)
    # --------------------------------------------------------
    r = requests.get(
        url,
        headers=JELLYFIN_HEADERS,
        params=params,
        timeout=30
    )

    r.raise_for_status()
    data = r.json()

    items = data.get("Items", [])

    results = []

    # --------------------------------------------------------
    # NORMALIZATION LAYER (IMPORTANT: matches ffprobe model)
    # --------------------------------------------------------
    for item in items:

        # ---------------- VIDEO OK CHECK ----------------
        video_ok = item.get("MediaSources") is not None and len(item.get("MediaSources", [])) > 0

        audio_streams = []
        subtitle_streams = []

        # Jellyfin stores streams inside MediaStreams
        for src in item.get("MediaSources", []):
            for stream in src.get("MediaStreams", []):

                # AUDIO STREAMS
                if stream.get("Type") == "Audio":
                    audio_streams.append({
                        "language": stream.get("Language", "") or "",
                        "default": stream.get("IsDefault", False)
                    })

                # SUBTITLE STREAMS
                if stream.get("Type") == "Subtitle":
                    subtitle_streams.append({
                        "language": stream.get("Language", "") or ""
                    })

        # ---------------- NFO (best-effort flag) ----------------
        # Jellyfin does not guarantee explicit NFO flag;
        # treat external metadata presence as proxy.
        nfo = item.get("HasNfo", False)

        # ---------------- ARTWORK ----------------
        # Jellyfin uses ImageTags to indicate artwork availability
        artwork = bool(item.get("ImageTags"))

        results.append({
            "name": item.get("Name", "unknown"),
            "video_ok": video_ok,
            "audio_streams": audio_streams,
            "subtitle_streams": subtitle_streams,
            "nfo": nfo,
            "artwork": artwork
        })

    return results


# ------------------------------------------------------------
# CORE EVALUATION (IDENTICAL LOGIC TO ORIGINAL SCRIPT)
# ------------------------------------------------------------

def evaluate_movie(movie: Dict[str, Any]) -> Dict[str, Any]:
    """
    Same logic as filesystem version.
    """

    score = 0
    issues = []

    # ---------------- VIDEO ----------------
    if not movie.get("video_ok", False):
        return {
            "tier": "F",
            "score": 0,
            "issues": ["video_corrupt"],
            "name": movie["name"]
        }

    score += 2

    # ---------------- AUDIO ----------------
    audio = movie.get("audio_streams", [])

    if not audio:
        issues.append("audio_missing")
    else:
        bad = any(a.get("language", "") in ["", "und"] for a in audio)

        if bad:
            issues.append("audio_und_lang")
        else:
            score += 1

        if not any(a.get("default", False) for a in audio):
            issues.append("audio_no_default")

    # ---------------- SUBTITLES ----------------
    subs = movie.get("subtitle_streams", [])

    if not subs:
        issues.append("subs_missing")
    else:
        bad = any(s.get("language", "") in ["", "und"] for s in subs)

        if bad:
            issues.append("subs_bad_tags")
        else:
            score += 1

    # ---------------- NFO ----------------
    if not movie.get("nfo", False):
        issues.append("nfo_missing")
    else:
        score += 1

    # ---------------- ARTWORK ----------------
    if not movie.get("artwork", False):
        issues.append("art_missing")

    # ---------------- TIERING ----------------
    if score == 5:
        tier = "A"
    elif score == 4:
        tier = "B"
    elif score == 3:
        tier = "C"
    elif score == 2:
        tier = "D"
    elif score == 1:
        tier = "E"
    else:
        tier = "F"

    return {
        "name": movie["name"],
        "tier": tier,
        "score": score,
        "issues": issues
    }


# ------------------------------------------------------------
# AGGREGATION (UNCHANGED)
# ------------------------------------------------------------

def aggregate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build tier summary + top issues.
    """

    tiers = defaultdict(list)

    for r in results:
        tiers[r["tier"]].append(r)

    summary = {}

    for t in ["A", "B", "C", "D", "E", "F"]:
        items = tiers.get(t, [])

        counter = Counter()
        for i in items:
            counter.update(i["issues"])

        summary[t] = {
            "count": len(items),
            "top_issues": counter.most_common(5)
        }

    return summary


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def scan_library():
    movies = jellyfin_get_movies()
    return [evaluate_movie(m) for m in movies]

def main():
    """
    Main CLI entry point.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--tier")
    args = parser.parse_args()

    results = scan_library()
    summary = aggregate(results)

    # ----------------------------
    # DRILLDOWN MODE
    # ----------------------------
    if args.tier:
        t = args.tier.upper()

        for r in results:
            if r["tier"] == t:
                print(r["name"], r["score"], r["issues"])

        return

    # ----------------------------
    # OVERVIEW MODE
    # ----------------------------
    for t in ["A", "B", "C", "D", "E", "F"]:

        data = summary.get(t, {"count": 0, "top_issues": []})
        count = data["count"]

        # skip empty tiers entirely
        if count == 0:
            continue

        # tier header with aligned count
        print(f"\nTier {t:<2}    count: {count}")

        # add linebreak for display improvement
        print("")

        top_issues = data["top_issues"]

        if not top_issues:
            print("top issues: none")
            continue

        print("top issues:")

        for issue_name, issue_count in top_issues:

            percentage = (issue_count / count) * 100 if count else 0.0

            print(f"- {issue_name} ({issue_count}, {percentage:.1f}%)")
            
if __name__ == "__main__":
    main()