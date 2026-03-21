"""Unit tests for the MetadataLoader.

Run with:  python -m pytest tests/test_metadata_loader.py -v
"""

from pathlib import Path

import pytest
import yaml

from ski.metadata.metadata_loader import MetadataLoader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def profiles_dir(tmp_path):
    """Create a temporary profiles directory with sample YAML files."""
    skiers = tmp_path / "skiers"
    skiers.mkdir()
    skis = tmp_path / "skis"
    skis.mkdir()

    (skiers / "maggie.yaml").write_text(yaml.dump({
        "skier_id": "maggie",
        "height_cm": 157,
        "weight_kg": 63,
        "ability_level": "advanced",
        "equipment": {"boots": "Lange RX 95"},
        "preferences": {"dominant_side": "right"},
    }))

    (skis / "sheeva10_104_158.yaml").write_text(yaml.dump({
        "ski_id": "sheeva10_104_158",
        "brand": "Blizzard",
        "model": "Sheeva 10",
        "length_cm": 158,
        "waist_mm": 104,
        "type": "all_mountain",
    }))

    return tmp_path


@pytest.fixture()
def session_dir(tmp_path):
    """Create a temporary session directory with a metadata.yaml."""
    meta = {
        "session_id": "test_session_001",
        "skier": "maggie",
        "ski": "sheeva10_104_158",
        "location": "breckenridge",
        "terrain": "groomer",
        "snow": "packed_powder",
        "phone_mount": "jacket_chest",
        "notes": "carving practice",
    }
    (tmp_path / "metadata.yaml").write_text(yaml.dump(meta))
    return tmp_path


# ---------------------------------------------------------------------------
# Skier profile tests
# ---------------------------------------------------------------------------

class TestLoadSkierProfile:
    def test_loads_correctly(self, profiles_dir):
        loader = MetadataLoader(profiles_dir=profiles_dir)
        profile = loader.load_skier_profile("maggie")
        assert profile is not None
        assert profile["skier_id"] == "maggie"
        assert profile["height_cm"] == 157
        assert profile["ability_level"] == "advanced"

    def test_equipment_nested(self, profiles_dir):
        loader = MetadataLoader(profiles_dir=profiles_dir)
        profile = loader.load_skier_profile("maggie")
        assert profile["equipment"]["boots"] == "Lange RX 95"

    def test_missing_returns_none(self, profiles_dir):
        loader = MetadataLoader(profiles_dir=profiles_dir)
        assert loader.load_skier_profile("nonexistent") is None


# ---------------------------------------------------------------------------
# Ski profile tests
# ---------------------------------------------------------------------------

class TestLoadSkiProfile:
    def test_loads_correctly(self, profiles_dir):
        loader = MetadataLoader(profiles_dir=profiles_dir)
        profile = loader.load_ski_profile("sheeva10_104_158")
        assert profile is not None
        assert profile["ski_id"] == "sheeva10_104_158"
        assert profile["brand"] == "Blizzard"
        assert profile["length_cm"] == 158

    def test_missing_returns_none(self, profiles_dir):
        loader = MetadataLoader(profiles_dir=profiles_dir)
        assert loader.load_ski_profile("nonexistent") is None


# ---------------------------------------------------------------------------
# Session metadata tests
# ---------------------------------------------------------------------------

class TestLoadSessionMetadata:
    def test_loads_correctly(self, session_dir):
        loader = MetadataLoader()
        meta = loader.load_session_metadata(session_dir)
        assert meta is not None
        assert meta["session_id"] == "test_session_001"
        assert meta["skier"] == "maggie"
        assert meta["ski"] == "sheeva10_104_158"
        assert meta["location"] == "breckenridge"

    def test_missing_returns_none(self, tmp_path):
        loader = MetadataLoader()
        assert loader.load_session_metadata(tmp_path) is None


# ---------------------------------------------------------------------------
# Real example files (integration)
# ---------------------------------------------------------------------------

class TestRealProfiles:
    def test_real_skier_profile(self):
        loader = MetadataLoader()
        profile = loader.load_skier_profile("maggie")
        assert profile is not None
        assert profile["skier_id"] == "maggie"

    def test_real_ski_profile(self):
        loader = MetadataLoader()
        profile = loader.load_ski_profile("sheeva10_104_158")
        assert profile is not None
        assert profile["ski_id"] == "sheeva10_104_158"

    def test_real_session_metadata(self):
        session_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "Aspen_Highlands-2026-02-26_16-52-11"
        )
        loader = MetadataLoader()
        meta = loader.load_session_metadata(session_path)
        assert meta is not None
        assert meta["skier"] == "maggie"
