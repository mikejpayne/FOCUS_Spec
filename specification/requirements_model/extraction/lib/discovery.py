"""File discovery — walks the FOCUS spec tree and builds FileTarget objects."""

import re
from pathlib import Path

from .models import FileTarget
def discover_files(contract, spec_root, logger):
    """Walk the spec directory and return FileTarget objects for all parseable files."""
    targets = []
    spec_root = Path(spec_root)
    dataset_types = contract["DatasetTypes"]

    # 1. Data Model (single file)
    dm_config = contract["DataModel"]
    dm_path = spec_root / dm_config["Location"]
    if dm_path.exists():
        targets.append(FileTarget(
            filepath=dm_path,
            entity_type=dm_config["EntityType"],
            artifact_type=dm_config["ArtifactType"],
            headings=dm_config["Headings"],
        ))
        logger.info(f"Discovered DataModel: {dm_path}")

    # 2. Datasets
    ds_config = contract["Datasets"]
    ds_base = spec_root / ds_config["Location"]
    if ds_base.exists():
        for subdir in sorted(ds_base.iterdir()):
            if not subdir.is_dir():
                continue
            dataset_md = subdir / "dataset.md"
            if not dataset_md.exists():
                continue
            dataset_id = folder_to_id(subdir.name)
            dataset_prefix = dataset_types.get(dataset_id, "")
            if not dataset_prefix:
                logger.warning(f"No DatasetType prefix for {dataset_id}, skipping dataset")
                continue

            targets.append(FileTarget(
                filepath=dataset_md,
                entity_type=ds_config["EntityType"],
                artifact_type=ds_config["ArtifactType"],
                dataset_id=dataset_id,
                dataset_name=id_to_display_name(dataset_id),
                dataset_prefix=dataset_prefix,
                headings=ds_config["Headings"],
            ))
            logger.info(f"Discovered Dataset: {dataset_md} ({dataset_prefix})")

    logger.info(f"Total files discovered: {len(targets)}")
    return targets



def folder_to_id(folder_name):
    """Convert folder name to PascalCase ID: cost_and_usage -> CostAndUsage."""
    return "".join(word.capitalize() for word in folder_name.split("_"))


def id_to_display_name(entity_id):
    """Convert PascalCase ID to display name: CostAndUsage -> Cost and Usage."""
    words = re.findall(r"[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)", entity_id)
    if not words:
        return entity_id
    connectors = {"and", "or", "of", "the", "a", "an", "in", "on", "for", "to", "by"}
    result = [words[0]]
    for w in words[1:]:
        if w.lower() in connectors:
            result.append(w.lower())
        else:
            result.append(w)
    return " ".join(result)


def id_to_folder(entity_id):
    """Convert PascalCase ID to folder name: CostAndUsage -> cost_and_usage."""
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", entity_id)
    return s.lower()
