"""Data classes for the FOCUS Requirements Model extraction pipeline."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RequirementBullet:
    """A parsed requirement bullet from markdown."""
    text: str
    indent_level: int = 0
    children: list = field(default_factory=list)


@dataclass
class FileTarget:
    """A markdown file to process, with metadata about what it contains."""
    filepath: Path
    entity_type: str        # Column, Dataset, DataModel, Attribute
    artifact_type: str      # C, D, M, A
    dataset_id: str = ""    # e.g. CostAndUsage
    dataset_name: str = ""  # e.g. Cost and Usage
    dataset_prefix: str = "" # e.g. CAU
    headings: dict = field(default_factory=dict)
    applicability_criteria: list = field(default_factory=list)


