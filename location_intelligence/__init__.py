"""Automated, evidence-aware location opportunity analysis."""

from .analysis import analyze_categories
from .models import CandidateCategory, SearchRequest, haversine_m
from .providers import FixtureProvider, GooglePlacesProvider, collect_places

__all__ = [
    "CandidateCategory",
    "FixtureProvider",
    "GooglePlacesProvider",
    "SearchRequest",
    "analyze_categories",
    "collect_places",
    "haversine_m",
]
