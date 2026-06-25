"""Markdown AST parsing using markdown-it-py.

Handles section splitting, table parsing, requirement bullet parsing,
and section accessors for FOCUS specification markdown files.
"""

import re

from markdown_it import MarkdownIt

from .models import RequirementBullet

# ---------------------------------------------------------------------------
# Shared parser instance and constants
# ---------------------------------------------------------------------------

MD_PARSER = MarkdownIt().enable("table")

BCP14_KEYWORDS = [
    "MUST NOT", "SHALL NOT", "SHOULD NOT",
    "MUST", "SHALL", "SHOULD",
    "NOT RECOMMENDED", "RECOMMENDED",
    "MAY", "OPTIONAL",
]

# Regex: strip markdown links [text](#anchor) -> text
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

# Regex: strip bold/italic markers
EMPHASIS_RE = re.compile(r"(\*{1,2}|_{1,2})")

# Regex: detect a leading "When ..." clause before the BCP14 keyword
WHEN_CLAUSE_RE = re.compile(r"^When\s+.+?,\s+", re.IGNORECASE)

# Regex: extract condition anchor from a markdown link
CONDITION_LINK_RE = re.compile(r"\[.*?\]\(#(conditions\.\w+)\)")


# ---------------------------------------------------------------------------
# Markdown file parsing
# ---------------------------------------------------------------------------

def parse_markdown(filepath):
    """Parse a markdown file into a list of markdown-it tokens."""
    with open(filepath, "r") as f:
        text = f.read()
    return MD_PARSER.parse(text), text


def extract_sections(tokens, logger, filename=""):
    """Split markdown-it tokens by h2 headings into named sections.

    Returns a dict of heading_name -> list[Token].
    Each section contains the tokens between one h2 and the next.
    """
    sections = {}
    current_heading = None
    current_tokens = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "heading_open" and token.tag == "h2":
            # Save previous section
            if current_heading is not None:
                sections[current_heading] = current_tokens

            # Next token is the inline with heading text
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                heading_text = tokens[i + 1].content.strip()
                # Strip <!--SkipTOC--> from heading content
                heading_text = re.sub(r"\s*<!--.*?-->\s*", "", heading_text).strip()
                current_heading = heading_text
                current_tokens = []
                i += 2  # skip inline
                # Skip heading_close
                if i < len(tokens) and tokens[i].type == "heading_close":
                    i += 1
                continue
            else:
                current_heading = None
                current_tokens = []
        elif current_heading is not None:
            current_tokens.append(token)

        i += 1

    # Save last section
    if current_heading is not None:
        sections[current_heading] = current_tokens

    logger.debug(f"Sections in {filename}: {list(sections.keys())}")
    return sections


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def tokens_to_first_line(tokens):
    """Extract the first non-empty inline text from tokens."""
    for t in tokens:
        if t.type == "inline" and t.content and t.content.strip():
            return t.content.strip()
    return ""


def clean_markdown_text(text):
    """Strip markdown links and emphasis from text, leaving plain text."""
    text = LINK_RE.sub(r"\1", text)
    text = EMPHASIS_RE.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Table parsing (via AST)
# ---------------------------------------------------------------------------

def parse_table_tokens(tokens):
    """Parse table tokens into a list of rows, each row a list of cell strings.

    Returns: list[list[str]] — first row is the header.
    """
    rows = []
    current_row = []
    in_row = False

    for t in tokens:
        if t.type == "tr_open":
            in_row = True
            current_row = []
        elif t.type == "tr_close":
            in_row = False
            if current_row:
                rows.append(current_row)
        elif t.type == "inline" and in_row:
            current_row.append(t.content.strip())

    return rows


def parse_table_as_dict(tokens):
    """Parse a two-column table into a dict of key -> value (raw markdown text).

    Expects a table with a header row and key-value data rows.
    """
    rows = parse_table_tokens(tokens)
    result = {}
    for row in rows[1:]:  # skip header
        if len(row) >= 2:
            key = clean_markdown_text(row[0])
            # Keep raw value (with markdown links) for condition extraction
            result[key] = row[1]
    return result


def parse_content_constraints(section_tokens):
    """Parse the Content Constraints section tokens into a dict."""
    table_tokens = []
    in_table = False
    for t in section_tokens:
        if t.type == "table_open":
            in_table = True
        if in_table:
            table_tokens.append(t)
        if t.type == "table_close":
            in_table = False
            break

    if not table_tokens:
        return {}

    return parse_table_as_dict(table_tokens)


# ---------------------------------------------------------------------------
# Requirement bullet parsing (via AST)
# ---------------------------------------------------------------------------

def parse_requirements_from_tokens(section_tokens):
    """Parse a Requirements section's tokens into an anchor phrase and bullet tree.

    Returns: (anchor_phrase, list[RequirementBullet])
    """
    anchor_phrase = ""

    bullet_list_start = None
    for i, t in enumerate(section_tokens):
        if t.type == "bullet_list_open":
            bullet_list_start = i
            break
        if t.type == "inline" and t.content.strip():
            anchor_phrase = t.content.strip()

    anchor_phrase = clean_markdown_text(anchor_phrase)

    if bullet_list_start is None:
        return anchor_phrase, []

    bullets = _parse_bullet_list(section_tokens, bullet_list_start)
    return anchor_phrase, bullets


def _parse_bullet_list(tokens, start_idx):
    """Parse a bullet_list starting at start_idx into RequirementBullet objects.

    Recursively handles nested bullet_list tokens within list_items.
    """
    bullets = []
    i = start_idx + 1  # skip the bullet_list_open
    depth = 1

    current_text_parts = []
    current_bullet = None

    while i < len(tokens) and depth > 0:
        t = tokens[i]

        if t.type == "bullet_list_open":
            # Nested bullet list — recursively parse as children of current bullet
            if current_bullet is not None:
                nested_bullets = _parse_bullet_list(tokens, i)
                current_bullet.children.extend(nested_bullets)
                # Skip past the nested bullet list
                nest_depth = 1
                i += 1
                while i < len(tokens) and nest_depth > 0:
                    if tokens[i].type == "bullet_list_open":
                        nest_depth += 1
                    elif tokens[i].type == "bullet_list_close":
                        nest_depth -= 1
                    i += 1
                continue
            else:
                depth += 1

        elif t.type == "bullet_list_close":
            depth -= 1
            if depth == 0:
                if current_text_parts:
                    text = clean_markdown_text(" ".join(current_text_parts))
                    if current_bullet is None:
                        current_bullet = RequirementBullet(text=text)
                    else:
                        current_bullet.text = text
                    bullets.append(current_bullet)
                break

        elif t.type == "list_item_open":
            # Start of a new list item — finalize previous
            if current_bullet is not None:
                if current_text_parts:
                    current_bullet.text = clean_markdown_text(" ".join(current_text_parts))
                bullets.append(current_bullet)
            current_text_parts = []
            current_bullet = RequirementBullet(text="")

        elif t.type == "list_item_close":
            pass  # handled by next list_item_open or bullet_list_close

        elif t.type == "inline" and t.content:
            current_text_parts.append(t.content.strip())

        i += 1

    return bullets


# ---------------------------------------------------------------------------
# Section accessors
# ---------------------------------------------------------------------------

def get_section_value(sections, headings, key, default=""):
    """Extract the first non-empty inline text from a named heading section."""
    heading = headings.get(key, default)
    if not heading or heading not in sections:
        return ""
    return tokens_to_first_line(sections[heading])


def get_feature_level(sections, headings, contract):
    """Extract the feature level (M/C/O) from Content Constraints table."""
    cc_heading = headings.get("ContentConstraints", "Content Constraints")
    if cc_heading not in sections:
        return None
    constraints = parse_content_constraints(sections[cc_heading])
    raw_level = clean_markdown_text(constraints.get("Feature level", ""))
    feature_map = contract.get("FeatureLevelMap", {})
    return feature_map.get(raw_level, None)


# ---------------------------------------------------------------------------
# BCP14 keyword extraction
# ---------------------------------------------------------------------------

def extract_bcp14_keyword(text):
    """Find the first BCP14 keyword in text. Returns the keyword or None."""
    for kw in BCP14_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            return kw
    return None
