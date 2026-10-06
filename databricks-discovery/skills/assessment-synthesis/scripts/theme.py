"""KMS look for the generated deliverables — the one place colour, type and header wording live.

Palette and face come from the KMS brand system (kms-deck-branding): Electric Blue #006AFE, Sky
Blue #62CCFE, Magenta #FE006A, Purple #6A26F1, Teal #02CCB3, Poppins. The brand colours carry
MEANING here (severity, status, disposition), never decoration. Fonts are named, not embedded: a
machine without Poppins falls back to its default sans and the sheet still reads.

Header wording: registers keep their snake_case field names — the Review tab keys on them — and
only the workbook's visible header row is translated. Unknown fields fall back to Title Case.
"""

FONT = "Poppins"

BLUE = "006AFE"
SKY = "62CCFE"
MAGENTA = "FE006A"
PURPLE = "6A26F1"
TEAL = "02CCB3"
INK = "0F172A"
MUTED = "64748B"
ZEBRA = "F4F7FB"
LINE = "DCE3EE"
WHITE = "FFFFFF"

#: text colour on a chip of the given fill
ON_DARK = WHITE
ON_LIGHT = INK

SEVERITY = {"critical": (MAGENTA, ON_DARK), "high": (PURPLE, ON_DARK), "medium": (SKY, ON_LIGHT), "low": (TEAL, ON_LIGHT)}
STATUS = {"extracted": ("E2E8F0", ON_LIGHT), "reviewed": (SKY, ON_LIGHT), "confirmed": (TEAL, ON_LIGHT),
          "deferred": ("FDE68A", ON_LIGHT), "rejected": (MAGENTA, ON_DARK), "open": ("E2E8F0", ON_LIGHT),
          "answered": (TEAL, ON_LIGHT)}
DISPOSITION = {"migrate": (TEAL, ON_LIGHT), "modernize": (BLUE, ON_DARK), "retire": (MAGENTA, ON_DARK),
               "defer": ("FDE68A", ON_LIGHT), "undecided": ("E2E8F0", ON_LIGHT)}
RULE_STATUS = {"VERIFIED": (TEAL, ON_LIGHT), "CONFLICT": (MAGENTA, ON_DARK), "CODE-ONLY": (PURPLE, ON_DARK),
               "DOC-ONLY": (SKY, ON_LIGHT), "CONFIG-ONLY": (SKY, ON_LIGHT), "DEAD": ("E2E8F0", ON_LIGHT),
               "UNRESOLVED": ("FDE68A", ON_LIGHT)}
MIGRATION = {"resolved-by-target": (TEAL, ON_LIGHT), "carried": (MAGENTA, ON_DARK), "redesign": (PURPLE, ON_DARK),
             "NOT SET": ("E2E8F0", ON_LIGHT)}

#: header -> which chip map colours its cells
CHIP_COLUMNS = {"severity": SEVERITY, "status": STATUS, "disposition": DISPOSITION, "rule_status": RULE_STATUS,
                "rule_status_max": RULE_STATUS, "when migrated": MIGRATION}

HEADERS = {
    "id": "ID", "object_id": "Object ID", "name": "Name", "title": "Title", "kind": "Kind", "type": "Type",
    "question": "Question", "why": "Why it matters", "ask": "Who to ask", "default": "Default if unanswered",
    "impact_if_wrong": "Impact if wrong", "blocking": "Blocks", "evidence": "Evidence", "evidence kind": "Evidence kind",
    "dimension": "Dimension", "score": "Score (1–5)", "counted": "Counts toward overall", "basis": "Basis",
    "rationale": "Rationale", "needs": "Needs", "status": "Review status",
    "disposition": "Disposition", "wave": "Wave", "used": "In use", "usage_window_days": "Usage window (days)",
    "covers_month_end": "Covers month-end", "complexity": "Complexity", "complexity_source": "Complexity source",
    "on_critical_path": "On critical path", "rule_status_max": "Riskiest rule", "owner_agreed": "Owner agreed",
    "target_component": "Target component", "notes": "Notes",
    "severity": "Severity", "category": "Category", "layer": "Layer", "impact": "Impact", "detail": "Detail",
    "when migrated": "When migrated", "requirements_raised": "Requirements raised", "questions_raised": "Questions raised",
    "rule_status": "Rule status", "logic": "Logic", "plain": "In plain words", "anchor": "Anchor (object · hash)",
    "config_driven": "Config-driven", "in_spec": "In the spec", "requirements": "Requirements", "open_questions": "Open questions",
    "locator": "Locator", "priority": "Priority", "statement": "Statement", "domain": "Domain", "inferred": "Inferred",
    "confidence": "Confidence", "conflicts": "Conflicts", "target_layer": "Target layer", "target_object": "Target object",
    "owner": "Owner", "layer_guess": "Layer (best guess)", "row_estimate": "Rows (est.)", "size_gb": "Size (GB)",
    "schedule": "Schedule", "avg_runtime_min": "Avg runtime (min)", "run_as": "Runs as", "reads": "Reads", "writes": "Writes",
    "readers": "Read by", "writers": "Written by", "consumers": "Consumers", "exec_count_90d": "Runs (90 days)",
    "last_exec_at": "Last run", "last_read_at": "Last read", "last_write_at": "Last write", "orphan": "Orphan",
    "holds_pii": "Holds PII", "erasure_reaches": "Erasure reaches it", "pii_candidates": "PII candidates",
    "email_draft": "Email draft", "requirement": "Requirement", "rules": "Rules", "source_objects": "Source objects",
    "from": "From", "to": "To",
}


def header_label(field: str) -> str:
    return HEADERS.get(field) or field.replace("_", " ").strip().capitalize()


def chip(column: str, value) -> tuple[str, str] | None:
    """(fill, text) for a value in a chip column, or None when the value has no chip."""
    table = CHIP_COLUMNS.get(column)
    if not table or value is None:
        return None
    return table.get(str(value)) or table.get(str(value).lower())
