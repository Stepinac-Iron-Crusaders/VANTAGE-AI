"""Validation tests for Phase 3: Gemini Scouting Agent."""

import asyncio
import sys


async def validate_imports():
    errors = []

    try:
        from vantage.api.gemini_client import (  # noqa: F401
            GeminiClient,
            GeminiError,
            _extract_json,
            _retry_seconds,
        )
        print("[OK] gemini_client")
    except Exception as e:
        errors.append(f"gemini_client: {e!r}")

    try:
        from vantage.scout import (  # noqa: F401
            HypothesisBuilder,
            MatchObserver,
            MatchupAdvisor,
            ScoutingAgent,
            VantageScout,
        )
        from vantage.scout.data import (  # noqa: F401
            build_event_teams_context,
            build_team_context,
            match_team_numbers,
        )
        from vantage.scout.dossier import TeamDossier, summarize_dossier  # noqa: F401
        from vantage.scout.observer import (  # noqa: F401
            MatchReview,
            filter_observations,
        )
        print("[OK] scout package")
    except Exception as e:
        errors.append(f"scout package: {e!r}")

    try:
        from vantage.models.models import (  # noqa: F401
            Hypothesis,
            MatchObservation,
            ResearchRecord,
        )
        print("[OK] scout models")
    except Exception as e:
        errors.append(f"scout models: {e!r}")

    if errors:
        print("\n[FAIL]:")
        for err in errors:
            print(f"  - {err}")
        return False
    print("\n[PASS] All Phase 3 imports successful")
    return True


async def validate_json_extraction():
    from vantage.api.gemini_client import GeminiError, _extract_json

    ok = _extract_json('{"a": 1}')
    assert ok == {"a": 1}, ok

    plain = _extract_json('{"summary": "hello", "tier": "strong"}')
    assert plain["tier"] == "strong"

    fenced = _extract_json('```json\n{"x": 2}\n```')
    assert fenced == {"x": 2}, fenced

    text = _extract_json('Here you go: {"a": 5} and that is all.')
    assert text == {"a": 5}, text

    broken = _extract_json('{"summary": "Line one\nLine two", "t": "ok"}')
    assert broken["t"] == "ok"
    assert "Line two" in broken["summary"]

    try:
        _extract_json("definitely not json")
        return False
    except GeminiError:
        pass

    try:
        _extract_json('[1, 2, 3]')
        return False
    except GeminiError:
        pass

    print("[OK] _extract_json (fences, trailing text, lenient strings)")
    return True


async def validate_retry_seconds():
    from vantage.api.gemini_client import _retry_seconds

    assert abs(_retry_seconds("Please retry in 45.8s.") - 45.8) < 0.01
    assert _retry_seconds("Please retry in 9999s.") == 60.0
    assert _retry_seconds("no hints here") == 8.0
    print("[OK] _retry_seconds (parses Gemini 429 hints, caps, fallback)")
    return True


async def validate_dossier_parsing():
    from vantage.scout.dossier import TeamDossier, summarize_dossier

    payload = {
        "summary": "Solid teleop team.",
        "strengths": ["Teleop scoring 30 EPA", "Climb reliability"],
        "weaknesses": ["Weak auto"],
        "profile": {"auto": "data unavailable", "teleop": "strong"},
        "tier": "strong",
        "confidence": 0.85,
    }
    d = TeamDossier.from_payload(27, payload)
    assert d.team_number == 27
    assert d.tier == "strong"
    assert d.confidence == 0.85
    assert d.strengths == ["Teleop scoring 30 EPA", "Climb reliability"]
    assert len(d.weaknesses) == 1

    r = d.to_research_dict()
    assert r["confidence"] == 0.85
    assert r["data"]["team_number"] == 27
    assert r["data"]["summary"] == "Solid teleop team."

    empty = TeamDossier.from_payload(999, None)
    assert empty.tier == "unknown"
    assert empty.confidence == 0.0
    assert empty.strengths == []

    text = summarize_dossier(d)
    assert "Team 27" in text and "tier=strong" in text
    assert "Teleop scoring 30 EPA" in text
    print("[OK] TeamDossier parsing + summarize")
    return True


async def validate_hypothesis_builder():
    from vantage.scout.dossier import TeamDossier
    from vantage.scout.hypotheses import HypothesisBuilder

    class FakeClient:
        def __init__(self, payload):
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def complete_json(self, system_prompt="", user_prompt="", **kw):
            return self.payload

    dossier = TeamDossier.from_payload(
        27,
        {
            "summary": "x",
            "profile": {"auto": "low", "teleop": "high"},
            "strengths": ["s"],
            "weaknesses": [],
            "tier": "strong",
            "confidence": 0.8,
        },
    )
    payload = {
        "hypotheses": [
            {
                "category": "teleop",
                "hypothesis": "Team 27 carries scoring in winning matches.",
                "confidence": 0.9,
            },
            {
                "category": "auto",
                "hypothesis": "",
                "confidence": 0.5,
            },
            {"hypothesis": "missing category"},
            "not a dict",
        ]
    }
    builder = HypothesisBuilder(session=None, client=FakeClient(payload))
    result = await builder.build(dossier, persist=False)
    assert result.team_number == 27
    assert result.persisted_count() == 2, result.hypotheses
    assert result.hypotheses[0]["category"] == "teleop"
    assert result.hypotheses[1]["category"] == "drive"  # default fallback
    assert result.hypotheses[1]["confidence"] == 0.3  # default fallback
    print("[OK] HypothesisBuilder parsing + defaults")
    return True


async def validate_observer_filter():
    from vantage.scout.observer import filter_observations

    allowed = {5460, 2137, 4998, 27, 5150, 494}
    raw = [
        {"team_number": 5460, "observation": "Great auto.", "confidence": 0.9},
        {"team_number": 1, "observation": "index junk.", "confidence": 0.8},
        {"team_number": 9999, "observation": "not in lineup.", "confidence": 0.8},
        {"team_number": "27", "observation": "String team ok.", "confidence": 0.7},
        {"team_number": 494, "observation": "   ", "confidence": 0.6},
        {"team_number": "abc", "observation": "bad number.", "confidence": 0.5},
        "not a dict",
    ]
    out = filter_observations(raw, allowed)
    assert len(out) == 2, out
    assert out[0]["team_number"] == 5460
    assert out[1]["team_number"] == 27  # string coerced
    assert out[0]["confidence"] == 0.9
    print("[OK] filter_observations (drops junk/index/empty teams)")
    return True


async def validate_tables():
    from vantage.models.models import Base

    tables = sorted(Base.metadata.tables.keys())
    for expected in [
        "hypotheses",
        "match_observations",
        "research_records",
    ]:
        assert expected in tables, f"{expected} missing"
    print("[OK] Phase 3 tables registered")
    return True


async def main():
    print("=" * 50)
    print("Vantage FRC Phase 3 Validation")
    print("=" * 50)

    checks = [
        await validate_imports(),
        await validate_json_extraction(),
        await validate_retry_seconds(),
        await validate_dossier_parsing(),
        await validate_hypothesis_builder(),
        await validate_observer_filter(),
        await validate_tables(),
    ]

    print("\n" + "=" * 50)
    if all(checks):
        print("Phase 3 validation: PASSED")
        sys.exit(0)
    else:
        print("Phase 3 validation: FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())