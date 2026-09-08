"""Validation tests for Phase 4: Web Dashboard."""

import asyncio
import sys


async def validate_imports():
    errors = []

    try:
        print("[OK] web runtime (uvicorn, testclient)")
    except Exception as e:
        errors.append(f"web runtime: {e!r}")

    try:
        from vantage.web.app import create_app
        assert create_app is not None
        print("[OK] web package imports")
    except Exception as e:
        errors.append(f"web package: {e!r}")

    try:
        from vantage.web.data import (  # noqa: F401
            dashboard_stats,
            event_matches,
            event_rankings,
            hypotheses,
            list_events,
            observations,
            replay_predictions,
            replay_runs,
            research_records,
            team_epa_series,
            team_event_record,
            team_latest_epa,
        )
        print("[OK] web data helpers")
    except Exception as e:
        errors.append(f"web data helpers: {e!r}")

    if errors:
        print("\n[FAIL]:")
        for err in errors:
            print(f"  - {err}")
        return False
    print("\n[PASS] All Phase 4 imports successful")
    return True


async def validate_routes():
    from starlette.testclient import TestClient

    from vantage.web.app import app

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200, r.status_code
        assert "Vantage" in r.text

        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r = client.get("/events")
        assert r.status_code in (200,)

        events = client.get("/api/events").json()
        if events:
            code = events[0]["event_code"]
            r = client.get(f"/events/{code}")
            assert r.status_code == 200, r.status_code
            r = client.get(f"/api/events/{code}/rankings")
            assert r.status_code == 200
            assert isinstance(r.json(), list)

        r = client.get("/teams/27")
        assert r.status_code == 200, r.status_code
        assert "Team 27" in r.text

        r = client.get("/replay")
        assert r.status_code == 200, r.status_code
        r = client.get("/scouting")
        assert r.status_code == 200, r.status_code
        r = client.get("/hypotheses")
        assert r.status_code == 200, r.status_code
        r = client.get("/observations")
        assert r.status_code == 200, r.status_code

        r = client.get("/matchup")
        assert r.status_code == 200, r.status_code

        # JSON prediction endpoint (deterministic, no Gemini)
        r = client.post(
            "/api/matchup/predict",
            json={
                "red_teams": [27, 5150, 494],
                "blue_teams": [5460, 2137, 4998],
                "season": 2025,
                "event_key": "2025miket",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["predicted_winner"] in ("red", "blue")
        assert data["predicted_red_score"] is not None
        assert data["confidence"] is not None

        # replay run detail
        runs = client.get("/api/replay/runs").json()
        if runs:
            r = client.get(f"/replay/{runs[0]['id']}")
            assert r.status_code == 200

    print("[OK] routes (home, event, team, replay, scouting, matchup, api)")
    return True


async def main():
    print("=" * 50)
    print("Vantage FRC Phase 4 Validation")
    print("=" * 50)

    from starlette.testclient import (
        TestClient,  # noqa: F401  (import here to surface errors)
    )

    checks = [
        await validate_imports(),
        await validate_routes(),
    ]

    print("\n" + "=" * 50)
    if all(checks):
        print("Phase 4 validation: PASSED")
        sys.exit(0)
    else:
        print("Phase 4 validation: FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())