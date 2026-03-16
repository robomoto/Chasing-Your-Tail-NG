# UX & Safety Hardening: Implementation Plan

Based on specialist reviews (UI, UX, DataViz, Social Psychology).

## New Modules

1. **`response_guidance.py`** — Maps alert tiers to actionable "what to do" guidance with DV/safety resources
2. **`alert_formatter.py`** — Five-tier alert language system (no certainty language, no intent attribution)
3. **`alert_filter.py`** — False positive suppression (threshold, familiar devices, corroboration, baselines)
4. **`data_retention.py`** — Auto-deletion of unflagged data after 48h, flagged after 90d
5. **`stealth_manager.py`** — Encrypted storage, obfuscated filenames, duress password, quick-wipe

## Alert Language Tiers

| Score | Tier | Headline Template |
|-------|------|-------------------|
| 0.0-0.3 | SILENT | (logged only, no user-facing text) |
| 0.3-0.5 | INFORMATIONAL | "A device was observed nearby." |
| 0.5-0.7 | NOTABLE | "A device has been observed at {N} of your locations." |
| 0.7-0.85 | ELEVATED | "A device has been observed at multiple locations over {time}." |
| 0.85-1.0 | REVIEW | "A device has shown a persistent pattern across {N} locations over {time}." |

Rules: No exclamation points. No "WARNING/ALERT/DANGER". No intent attribution. No raw scores shown to users.

## Implementation Order

1. response_guidance.py (zero dependencies)
2. alert_formatter.py (depends on response_guidance)
3. alert_filter.py (depends on fusion_engine, session_db)
4. data_retention.py (depends on session_db)
5. stealth_manager.py (depends on session_db, secure_credentials)
6. Wire into cyt_ng.py
