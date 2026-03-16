"""TDD tests for response_guidance module."""
import pytest

from response_guidance import AlertTier, GuidanceMessage, ResponseGuidance


class TestResponseGuidance:
    """Tests for tier-to-guidance mapping and safety resources."""

    def test_silent_no_guidance(self):
        """tier=SILENT -> empty do_items and do_not_items."""
        rg = ResponseGuidance()
        msg = rg.get_guidance(AlertTier.SILENT)
        assert msg.do_items == []
        assert msg.do_not_items == []

    def test_informational_no_action(self):
        """tier=INFORMATIONAL -> do_items contains 'No action needed'."""
        rg = ResponseGuidance()
        msg = rg.get_guidance(AlertTier.INFORMATIONAL)
        assert any("No action needed" in item for item in msg.do_items)

    def test_notable_vary_route(self):
        """tier=NOTABLE -> do_items mentions varying route, do_not_items mentions 'Do not confront'."""
        rg = ResponseGuidance()
        msg = rg.get_guidance(AlertTier.NOTABLE)
        assert any("vary" in item.lower() or "route" in item.lower() for item in msg.do_items)
        assert any("Do not confront" in item for item in msg.do_not_items)

    def test_elevated_includes_resources(self):
        """tier=ELEVATED -> resources list includes DV hotline."""
        rg = ResponseGuidance()
        msg = rg.get_guidance(AlertTier.ELEVATED)
        resource_names = [r.get("name", "") for r in msg.resources]
        assert any("hotline" in name.lower() or "dv" in name.lower()
                    for name in resource_names)

    def test_review_includes_all_resources(self):
        """tier=REVIEW -> resources list has 4 entries."""
        rg = ResponseGuidance()
        msg = rg.get_guidance(AlertTier.REVIEW)
        assert len(msg.resources) == 4

    def test_custom_resources(self):
        """Custom config adds local resource -> appears in get_resources()."""
        custom = {
            "extra_resources": [
                {"name": "Local DV Shelter", "contact": "555-1234"}
            ]
        }
        rg = ResponseGuidance(config=custom)
        all_resources = rg.get_resources()
        names = [r.get("name", "") for r in all_resources]
        assert "Local DV Shelter" in names
