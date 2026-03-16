"""Response guidance — maps alert tiers to actionable next steps."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class AlertTier(Enum):
    SILENT = 1
    INFORMATIONAL = 2
    NOTABLE = 3
    ELEVATED = 4
    REVIEW = 5


@dataclass
class GuidanceMessage:
    do_items: List[str] = field(default_factory=list)
    do_not_items: List[str] = field(default_factory=list)
    resources: List[dict] = field(default_factory=list)
    summary: str = ""


# Default safety resources
_DEFAULT_RESOURCES: List[dict] = [
    {
        "name": "National DV Hotline",
        "contact": "1-800-799-7233",
        "url": "https://www.thehotline.org",
    },
    {
        "name": "NNEDV Safety Net",
        "contact": "https://www.techsafety.org",
        "url": "https://www.techsafety.org",
    },
    {
        "name": "Crisis Text Line",
        "contact": "Text HOME to 741741",
        "url": "https://www.crisistextline.org",
    },
    {
        "name": "RAINN",
        "contact": "1-800-656-4673",
        "url": "https://www.rainn.org",
    },
]

# Tier-specific guidance definitions
_TIER_GUIDANCE = {
    AlertTier.SILENT: GuidanceMessage(
        do_items=[],
        do_not_items=[],
        resources=[],
        summary="",
    ),
    AlertTier.INFORMATIONAL: GuidanceMessage(
        do_items=["No action needed. This is for your awareness only."],
        do_not_items=[],
        resources=[],
        summary="A device was briefly observed nearby. This is common and usually benign.",
    ),
    AlertTier.NOTABLE: GuidanceMessage(
        do_items=[
            "Consider varying your route or schedule over the next few days.",
            "Note the time and place if you see this notification again.",
        ],
        do_not_items=[
            "Do not confront anyone or any device.",
            "Do not assume intent based on proximity alone.",
        ],
        resources=[],
        summary="A device has appeared at more than one of your locations. "
                "This could be coincidence.",
    ),
    AlertTier.ELEVATED: GuidanceMessage(
        do_items=[
            "Consider varying your route and schedule.",
            "Tell a trusted person about the pattern you are seeing.",
            "Review the resources below if you feel unsafe.",
        ],
        do_not_items=[
            "Do not confront anyone or any device.",
            "Do not assume intent based on device proximity.",
            "Do not share raw data publicly.",
        ],
        resources=list(_DEFAULT_RESOURCES),
        summary="A device has appeared at multiple locations over an extended period. "
                "Safety resources are available below.",
    ),
    AlertTier.REVIEW: GuidanceMessage(
        do_items=[
            "Consider varying your route and schedule immediately.",
            "Tell a trusted person about the pattern.",
            "Contact a safety resource below if you feel unsafe.",
            "Consider consulting with law enforcement or a DV advocate.",
        ],
        do_not_items=[
            "Do not confront anyone or any device.",
            "Do not assume intent based on device proximity.",
            "Do not share raw data publicly.",
            "Do not attempt to locate or disable unknown devices yourself.",
        ],
        resources=list(_DEFAULT_RESOURCES),
        summary="A device has shown a persistent pattern across multiple locations. "
                "Please review the resources and guidance below.",
    ),
}


class ResponseGuidance:
    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}
        self._extra_resources: List[dict] = self._config.get("extra_resources", [])

    def get_guidance(self, tier: AlertTier) -> GuidanceMessage:
        """Return guidance appropriate for the given alert tier."""
        base = _TIER_GUIDANCE.get(tier, _TIER_GUIDANCE[AlertTier.SILENT])
        # Build a copy so callers don't mutate the template
        resources = list(base.resources)
        # Append extra resources for tiers that include resources
        if tier in (AlertTier.ELEVATED, AlertTier.REVIEW) and self._extra_resources:
            resources.extend(self._extra_resources)
        return GuidanceMessage(
            do_items=list(base.do_items),
            do_not_items=list(base.do_not_items),
            resources=resources,
            summary=base.summary,
        )

    def get_resources(self) -> List[dict]:
        """Return the full list of safety resources (default + custom)."""
        return list(_DEFAULT_RESOURCES) + list(self._extra_resources)
