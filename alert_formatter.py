"""Alert formatter — five-tier language system for surveillance alerts."""
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from response_guidance import AlertTier, GuidanceMessage, ResponseGuidance


@dataclass
class AlertMessage:
    tier: AlertTier
    device_id: str
    headline: str
    detail: str
    guidance: GuidanceMessage
    source_types: List[str] = field(default_factory=list)
    score: float = 0.0
    location_count: int = 0
    time_span_hours: float = 0.0
    timestamp: float = 0.0
    corroborated: bool = False


# Tier classification boundaries: [0.3, 0.5, 0.7, 0.85]
_TIER_BOUNDARIES = [
    (0.85, AlertTier.REVIEW),
    (0.70, AlertTier.ELEVATED),
    (0.50, AlertTier.NOTABLE),
    (0.30, AlertTier.INFORMATIONAL),
]


class AlertFormatter:
    FORBIDDEN_WORDS = [
        "WARNING", "ALERT", "DANGER",
        "surveillance", "following", "stalking", "tracked",
    ]

    def __init__(self, config: Optional[dict] = None, guidance: Optional[ResponseGuidance] = None):
        self._config = config or {}
        self._guidance = guidance or ResponseGuidance(config=self._config)

    def classify(self, score: float) -> AlertTier:
        """Map a persistence score to an AlertTier based on defined boundaries."""
        for threshold, tier in _TIER_BOUNDARIES:
            if score >= threshold:
                return tier
        return AlertTier.SILENT

    def format_alert(self, device, fusion_engine=None) -> Optional[AlertMessage]:
        """Produce an AlertMessage for the given device, or None if SILENT."""
        score = device.persistence_score
        tier = self.classify(score)

        if tier == AlertTier.SILENT:
            return None

        location_count = len(device.locations_seen)
        time_span = device.last_seen - device.first_seen
        time_span_hours = time_span.total_seconds() / 3600.0

        # Determine corroboration
        corroborated = False
        source_types: List[str] = []
        if fusion_engine is not None:
            multiplier = fusion_engine.get_score_multiplier(device.mac)
            if multiplier > 1.0:
                corroborated = True
            groups = fusion_engine.get_correlated_groups()
            for gid, members in groups.items():
                if device.mac in members:
                    source_types = list(members)
                    break

        headline = self._build_headline(tier, location_count, time_span_hours)
        detail = self._build_detail(tier, device, corroborated, time_span_hours)
        guidance_msg = self._guidance.get_guidance(tier)

        return AlertMessage(
            tier=tier,
            device_id=device.mac,
            headline=headline,
            detail=detail,
            guidance=guidance_msg,
            source_types=source_types,
            score=score,
            location_count=location_count,
            time_span_hours=round(time_span_hours, 1),
            timestamp=time.time(),
            corroborated=corroborated,
        )

    def _build_headline(self, tier: AlertTier, location_count: int,
                        time_span_hours: float) -> str:
        """Build a tier-appropriate headline. No forbidden words, no exclamation points."""
        hours_str = str(int(round(time_span_hours)))
        if tier == AlertTier.INFORMATIONAL:
            return "A device was observed nearby."
        elif tier == AlertTier.NOTABLE:
            return f"A device has been observed at {location_count} of your locations."
        elif tier == AlertTier.ELEVATED:
            return (f"A device has been observed at multiple locations "
                    f"over {hours_str} hours.")
        elif tier == AlertTier.REVIEW:
            return (f"A device has shown a persistent pattern across "
                    f"{location_count} locations over {hours_str} hours.")
        return ""

    def _build_detail(self, tier: AlertTier, device, corroborated: bool,
                      time_span_hours: float) -> str:
        """Build detail text with appropriate caveats."""
        parts: List[str] = []

        if tier == AlertTier.INFORMATIONAL:
            parts.append(
                "This device was seen briefly. No pattern has been established."
            )
        elif tier == AlertTier.NOTABLE:
            parts.append(
                f"This device has appeared at {len(device.locations_seen)} "
                f"of your recent locations. This may be coincidental."
            )
        elif tier == AlertTier.ELEVATED:
            parts.append(
                f"This device has appeared at {len(device.locations_seen)} "
                f"locations over approximately {int(round(time_span_hours))} hours."
            )
        elif tier == AlertTier.REVIEW:
            parts.append(
                f"This device has shown a persistent pattern across "
                f"{len(device.locations_seen)} locations over approximately "
                f"{int(round(time_span_hours))} hours."
            )

        # Single-source caveat
        if not corroborated:
            parts.append(
                "Note: this detection is based on a single sensor type. "
                "Corroboration from additional sources would increase confidence."
            )

        return " ".join(parts)

    def format_summary_line(self, device) -> str:
        """Return a short one-line summary for list views."""
        tier = self.classify(device.persistence_score)
        if tier == AlertTier.SILENT:
            return ""
        location_count = len(device.locations_seen)
        return f"Device seen at {location_count} location(s) — {tier.name.lower()}"
