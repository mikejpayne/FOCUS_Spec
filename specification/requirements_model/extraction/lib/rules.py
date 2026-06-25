"""Rule generation — converts parsed markdown into Requirements Model JSON rules."""

import re

from .discovery import id_to_display_name
from .parsing import (
    WHEN_CLAUSE_RE,
    extract_bcp14_keyword,
    get_feature_level,
    get_section_value,
    parse_requirements_from_tokens,
)


def derive_feature_level(keyword, text):
    """Derive the feature level suffix for a rule ID from BCP14 keyword and text content."""
    if not keyword:
        return "M"

    has_condition = bool(WHEN_CLAUSE_RE.match(text)) or " when " in text.lower()

    if keyword in ("MUST", "MUST NOT", "SHALL", "SHALL NOT"):
        return "C" if has_condition else "M"
    elif keyword in ("SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED"):
        return "C" if has_condition else "O"
    elif keyword in ("MAY", "OPTIONAL"):
        return "O"
    return "M"



def classify_verb(text, verb_map):
    """Look up the requirement verb in the contract's RequirementVerbs map.

    Returns the classification string, or None if no known verb matches.
    """
    lower = text.lower()
    for verb, classification in verb_map.items():
        if re.search(r"\b" + re.escape(verb) + r"\b", lower):
            return classification
    return None



INCLUDE_COLUMN_RE = re.compile(r"\binclude\s+([A-Z][a-zA-Z]+)\b")
CONFORM_ATTR_RE = re.compile(r"\bconform to\s+([A-Z][a-zA-Z]+)\s+requirements\b")


def extract_requirement_check(text, function):
    """Extract a structured check from the requirement text, if the pattern is clean."""
    if function == "ColumnPresence":
        m = INCLUDE_COLUMN_RE.search(text)
        if m:
            return {"CheckFunction": "ColumnPresent", "ColumnName": m.group(1)}
    elif function == "AttributeConformance":
        m = CONFORM_ATTR_RE.search(text)
        if m:
            return {"CheckFunction": "AttributeConformance", "AttributeName": m.group(1)}
    return None


def generate_rule_id(prefix, entity_id, artifact_type, seq, feature_level):
    """Build a rule ID string."""
    if prefix:
        return f"{prefix}-{entity_id}-{artifact_type}-{seq:03d}-{feature_level}"
    else:
        return f"{entity_id}-{artifact_type}-{seq:03d}-{feature_level}"


def generate_rules(target, sections, contract, model_version, logger):
    """Generate RM JSON rules from parsed markdown sections.

    Returns (rules_dict, skipped_list).
    """
    headings = target.headings
    entity_id = get_section_value(sections, headings, "Id")
    display_name = get_section_value(sections, headings, "DisplayName", "Display Name")
    version_introduced = get_section_value(sections, headings, "VersionIntroduced", "Version Introduced")

    if not entity_id:
        logger.warning(f"No entity ID found in {target.filepath}, skipping")
        return {}, []

    req_heading = headings.get("Requirements", "Requirements")
    req_tokens = sections.get(req_heading, [])
    if not req_tokens:
        logger.warning(f"No Requirements section in {target.filepath}, skipping")
        return {}, []

    anchor_phrase, bullets = parse_requirements_from_tokens(req_tokens)
    if not bullets:
        logger.warning(f"No requirement bullets found in {target.filepath}")
        return {}, []

    # Determine feature level for composite rule
    composite_feature_level = get_feature_level(sections, headings, contract)
    # If ApplicabilityCriteria is set, force C on the composite
    if target.applicability_criteria:
        composite_feature_level = "C"
    elif composite_feature_level is None:
        anchor_kw = extract_bcp14_keyword(anchor_phrase)
        composite_feature_level = derive_feature_level(anchor_kw, anchor_phrase) if anchor_kw else "M"

    prefix = target.dataset_prefix

    shared = {
        "EntityType": target.entity_type,
        "EntityName": display_name or id_to_display_name(entity_id),
        "EntityId": entity_id,
        "Reference": entity_id,
        "Notes": "",
        "ModelVersionIntroduced": model_version or version_introduced or "",
        "Status": "Active",
        "ApplicabilityCriteria": [],
    }

    if target.dataset_id:
        shared["DatasetType"] = target.dataset_prefix
        shared["DatasetId"] = target.dataset_id
        shared["DatasetName"] = target.dataset_name

    verb_map = contract.get("RequirementVerbs", {})

    rules = {}
    child_ids = []
    skipped = []
    seq = 0

    def process_bullet(bullet):
        nonlocal seq

        function = classify_verb(bullet.text, verb_map)
        if function is None:
            skipped.append(bullet.text)
            return None

        seq += 1
        keyword = extract_bcp14_keyword(bullet.text)
        fl = derive_feature_level(keyword, bullet.text) if keyword else composite_feature_level

        rule_id = generate_rule_id(prefix, entity_id, target.artifact_type, seq, fl)

        rule = {
            **shared,
            "Function": function,
            "Type": "Static",
            "ValidationCriteria": {
                "MustSatisfy": bullet.text,
                "Keyword": keyword or "MUST",
                "Requirement": extract_requirement_check(bullet.text, function) or {},
                "Condition": {},
                "Dependencies": [],
            },
        }

        if bullet.children:
            sub_child_ids = []
            for child in bullet.children:
                child_id = process_bullet(child)
                if child_id:
                    sub_child_ids.append(child_id)
            if sub_child_ids:
                rule["ValidationCriteria"]["Requirement"] = {
                    "CheckFunction": "AND",
                    "Items": [
                        {"CheckFunction": "CheckModelRule", "ModelRuleId": cid}
                        for cid in sub_child_ids
                    ],
                }
                rule["ValidationCriteria"]["Dependencies"] = list(sub_child_ids)

        rules[rule_id] = rule
        return rule_id

    for bullet in bullets:
        child_id = process_bullet(bullet)
        if child_id:
            child_ids.append(child_id)

    # Create composite -000- rule
    composite_function = classify_verb(anchor_phrase, verb_map)
    if composite_function is None:
        logger.warning(f"No known verb in anchor phrase for {entity_id}, skipping file")
        return {}, skipped

    composite_id = generate_rule_id(prefix, entity_id, target.artifact_type, 0, composite_feature_level)
    composite_rule = {
        **shared,
        "Function": composite_function,
        "Type": "Static",
        "ValidationCriteria": {
            "MustSatisfy": anchor_phrase,
            "Keyword": extract_bcp14_keyword(anchor_phrase) or "MUST",
            "Requirement": {
                "CheckFunction": "AND",
                "Items": [
                    {"CheckFunction": "CheckModelRule", "ModelRuleId": cid}
                    for cid in child_ids
                ],
            },
            "Condition": {},
            "Dependencies": list(child_ids),
        },
    }

    # ApplicabilityCriteria only goes on the composite rule, not children
    if target.applicability_criteria:
        composite_rule["ApplicabilityCriteria"] = list(target.applicability_criteria)

    ordered_rules = {composite_id: composite_rule}
    ordered_rules.update(rules)

    logger.info(f"Generated {len(ordered_rules)} rules for {entity_id} ({len(skipped)} bullets skipped)")
    return ordered_rules, skipped
