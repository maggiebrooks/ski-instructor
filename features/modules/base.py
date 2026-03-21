"""Base interface for pluggable feature modules.

Every feature module subclasses ``FeatureModule`` and implements
``compute(turn_df, context) -> dict``.  The pipeline calls each
active module in sequence and merges the returned dicts into a
single per-turn record.
"""


class FeatureModule:
    """Abstract base for feature extraction modules."""

    name = "base"

    def compute(self, turn_df, context):
        """Extract features from a single turn segment.

        Parameters
        ----------
        turn_df : DataFrame
            Rows belonging to one turn (sliced at midpoints between
            detected peaks).  Contains at minimum: ``seconds``,
            ``gyro_z``, ``speed``, ``roll``, ``accel_mag``.
        context : dict
            Run/session-level metadata.  Guaranteed keys:
            ``peak_pos`` (int), ``sample_rate`` (int).
            May also contain ``run_index``, ``schema_version``.

        Returns
        -------
        dict
            Feature-name -> value mapping.  Keys should be
            prefixed with the sensor source when sensor-specific
            (e.g. ``pelvis_turn_angle_deg``).
        """
        raise NotImplementedError
