"""Read-only loader for skier profiles, ski equipment profiles, and session metadata.

All data is stored as YAML files.  This module is completely independent of
the processing pipeline -- it performs no writes and has no side effects.

Usage::

    from ski.metadata.metadata_loader import MetadataLoader
    loader = MetadataLoader()
    skier  = loader.load_skier_profile("maggie")
    ski    = loader.load_ski_profile("sheeva10_104_158")
    meta   = loader.load_session_metadata(Path("data/Aspen_Highlands-..."))
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class MetadataLoader:
    """Load skier/ski profiles and per-session metadata from YAML files."""

    def __init__(self, profiles_dir: Path | None = None):
        self.profiles_dir = (
            profiles_dir
            or Path(__file__).resolve().parents[1] / "profiles"
        )

    def _load_yaml(self, path: Path) -> dict | None:
        if not path.is_file():
            return None
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def load_skier_profile(self, skier_id: str) -> dict | None:
        """Load a skier profile by ID.

        Returns the parsed dict, or ``None`` if the file does not exist.
        """
        return self._load_yaml(
            Path(self.profiles_dir) / "skiers" / f"{skier_id}.yaml"
        )

    def load_ski_profile(self, ski_id: str) -> dict | None:
        """Load a ski equipment profile by ID.

        Returns the parsed dict, or ``None`` if the file does not exist.
        """
        return self._load_yaml(
            Path(self.profiles_dir) / "skis" / f"{ski_id}.yaml"
        )

    def load_session_metadata(self, session_path: Path) -> dict | None:
        """Load session metadata from a session directory.

        Looks for ``metadata.yaml`` inside *session_path*.
        Returns the parsed dict, or ``None`` if the file does not exist.
        """
        return self._load_yaml(Path(session_path) / "metadata.yaml")
