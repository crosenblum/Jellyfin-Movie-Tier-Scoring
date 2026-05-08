Jellyfin Media Tier Scoring

Overview
This script scans a Jellyfin movie library and assigns each movie folder to a quality tier from A to F based on metadata completeness and stream integrity.

It is designed for:

Large movie libraries
Cross-platform use (Windows/Linux)
Jellyfin-only environments (no filesystem or ffprobe dependency)

The output is a tiered audit showing library health and the most common issues per tier.

Features

Connects directly to Jellyfin API
Evaluates each movie using consistent rules
Assigns tiers A (best) to F (worst)
Identifies top metadata issues per tier
Provides library-wide overview
Provides per-tier drilldown view

Requirements

Python 3.8+
requests library

Install dependency:
pip install requests

Configuration

Edit these values in the script:

JELLYFIN_SERVER
Example: http://192.168.1.6:8096

JELLYFIN_API_KEY
Your Jellyfin API token

JELLYFIN_USER_ID
Optional depending on server setup (can be empty if using global Items endpoint)

Usage

Full library scan:
python script.py

Tier drilldown:
python script.py --tier B

Valid tiers:
A, B, C, D, E, F

Output format

Overview mode shows:

Tier A count: X
top issues: none

Tier B count: X
top issues:

issue_name (count, percentage)

Tiers with zero items are not displayed.

Scoring system

Each movie is evaluated across 5 categories:

Video integrity
Audio stream language and default track
Subtitle availability and language tags
NFO metadata presence
Artwork presence

Each category contributes to a total score which determines tier assignment.

Tier mapping:
A = highest completeness
F = lowest or corrupt/missing data

Design notes

No caching
No persistent database
No external media server dependencies beyond Jellyfin
Deterministic evaluation logic
Optimized for single-pass scanning

Limitations

NFO detection depends on Jellyfin metadata availability
Language detection depends on embedded stream tags
Artwork detection depends on Jellyfin image metadata
No repair functionality included (read-only tool)
