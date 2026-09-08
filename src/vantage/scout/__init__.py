"""Phase 3: Gemini-powered scouting agent for Vantage FRC."""

from vantage.scout.agent import VantageScout
from vantage.scout.dossier import ScoutingAgent, TeamDossier
from vantage.scout.hypotheses import HypothesisBuilder, HypothesisSet
from vantage.scout.matchup import MatchupAdvisor, MatchupAnalysis
from vantage.scout.observer import MatchObserver, MatchReview

__all__ = [
    "VantageScout",
    "ScoutingAgent",
    "TeamDossier",
    "MatchupAdvisor",
    "MatchupAnalysis",
    "MatchObserver",
    "MatchReview",
    "HypothesisBuilder",
    "HypothesisSet",
]