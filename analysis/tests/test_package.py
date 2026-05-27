"""Smoke test ensuring the analysis package is importable."""

import vision_agents.plugins.interhuman_analysis as ih_analysis


def test_package_imports():
    assert ih_analysis.__all__ == []
