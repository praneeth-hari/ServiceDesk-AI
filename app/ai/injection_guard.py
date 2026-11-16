"""
Prompt-injection guard for AI-assisted IT ticket triage.

A transparent, deterministic heuristic detector that screens ticket text
before it reaches LLM triage prompts. Normalises obfuscations (Unicode, zero-width,
letter-spaced tokens) and detects adversarial manipulation patterns:
- Instruction override directives
- Role / system / agent impersonation headers
- Simulated triage output and reference-ticket formatting
- Direct category / priority assignment commands (including polite variants)
- Social-engineering executive priority inflation

Crucially, it is tuned to NOT flag benign tickets that innocently use words like
'urgent', 'ignore', 'system', or 'priority'.
Returns structured evaluation metadata with matched rule identifiers, NEVER raw text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

from app.ai.llm_triage import CATEGORIES, PRIORITIES

CATS_PATTERN = "|".join(CATEGORIES)
PRIOS_PATTERN = "|".join(PRIORITIES)


def _seq(*stages: str) -> str:
    """
    Regex source for "stage 1, then stage 2, ... in order, with anything in between".

    The obvious way to write this is `stage1.*?stage2.*?stage3`. If the text has no match, that
    form retries every combination of positions, so the time grows with the square or cube of
    the text length: a few hundred characters can take seconds and 10,000 characters minutes,
    and a regex search holds the interpreter lock, so it stalls the whole server.

    Here each `.*?` plus its stage sits in an atomic group `(?>...)`. Once a stage has matched at
    its earliest position the engine never goes back to look for a later one. That cannot change
    the result: the earliest match of a stage leaves the most text for the stages after it, so
    if any ordered match exists, the earliest-first one does too. Run from the start of a line
    (see `_lines`) it reads each line a constant number of times, so the time grows linearly.
    """
    return "".join(f"(?>.*?{stage})" for stage in stages)


def _lines(*sequences: str) -> re.Pattern[str]:
    """Match any of the `_seq` sequences within a single line (`.` does not cross newlines)."""
    return re.compile("^(?:" + "|".join(sequences) + ")", re.I | re.M)


@dataclass(frozen=True)
class InjectionGuardResult:
    """Detection result returned by the injection guard."""

    is_injection: bool
    confidence_score: float
    matched_rules: list[str] = field(default_factory=list)


def normalize_text_for_guard(text: str) -> str:
    """
    Normalise text to defeat common evasion and obfuscation strategies:
    1. Unicode NFKC normalisation (combines decomposed characters, maps stylistic variants).
    2. Strips invisible / zero-width characters.
    3. Lowercases text.
    4. Collapses letter-spaced words (e.g. 'u r g e n t' -> 'urgent', 'c-a-t-e-g-o-r-y' -> 'category').
    """
    if not text:
        return ""

    # 1. Unicode NFKC normalisation
    norm = unicodedata.normalize("NFKC", text)

    # 2. Strip zero-width & non-printable formatting characters
    norm = re.sub(r"[\u200b-\u200f\u2028-\u202f\ufeff\x00-\x08\x0b\x0c\x0e-\x1f]", "", norm)

    # 3. Lowercase
    norm = norm.lower()

    # 4. Collapse letter-spaced sequences: sequence of single letters separated by space, dash, or underscore
    # e.g. "u r g e n t", "c - a - t - e - g - o - r - y", "s_o_f_t_w_a_r_e"
    norm = re.sub(
        r"\b[a-z](?:\s*[-_]\s*[a-z]|\s+[a-z]){2,}\b",
        lambda m: re.sub(r"[\s\-_]+", "", m.group(0)),
        norm,
    )

    return norm


# ============================================================================
# Heuristic Pattern Definitions
# ============================================================================

GUARD_RULES: list[tuple[str, re.Pattern[str]]] = [
    # 1. Delimiter, reference block, and structural escaping
    (
        "fake_reference_block",
        re.compile(r"---\s*reference\s*ticket\b", re.I),
    ),
    (
        "xml_delimiter_tag",
        re.compile(r"</?(?:ticket_data|reference_ticket)>", re.I),
    ),
    (
        "fake_triage_result_block",
        re.compile(
            r"\b(?:previous\s*triage\s*result|automated\s*classification\s*history|triage\s*engine\s*(?:v\d+)?\s*output)\b",
            re.I,
        ),
    ),
    (
        "json_code_block_classification",
        # `.` also matches newlines here, so anchor once at the start of the text
        re.compile(r"\A" + _seq(r"```json\s*\{", r"(?:category|priority)"), re.I | re.S),
    ),
    (
        "raw_json_classification_payload",
        re.compile(
            rf'\{{\s*["\'](?:category|priority)["\']\s*:\s*["\'](?:{CATS_PATTERN}|{PRIOS_PATTERN})["\']',
            re.I,
        ),
    ),
    # 2. Fake label lines (e.g. Category: hardware, Priority: urgent as isolated lines or sentences)
    (
        "fake_label_line",
        re.compile(
            rf"(?:^|\n|[\r\n;\|\.])\s*(?:category|priority)\s*:\s*(?:{CATS_PATTERN}|{PRIOS_PATTERN})\b",
            re.I,
        ),
    ),
    # 3. Instruction overrides & meta-prompts
    (
        "instruction_override",
        _lines(
            _seq(
                r"\b(?:ignore|disregard|forget|override)\b",
                r"\b(?:instructions|prompt|rules|guidance|guidelines|criteria)\b",
            )
        ),
    ),
    (
        "system_instruction_override",
        _lines(
            _seq(
                r"\b(?:system\s*instruction|system\s*prompt|system\s*message)\b",
                r"(?::|override|redirect|rules|guidelines)",
            )
        ),
    ),
    (
        "prompt_reset_directive",
        re.compile(
            r"\b(?:system\s*prompt\s*reset|disregard\s*earlier\s*guidance|forget\s*all\s*rules|override\s*prompt)\b",
            re.I,
        ),
    ),
    (
        "negative_triage_constraint",
        _lines(
            _seq(
                r"\b(?:do\s*not\s*follow|regardless\s*of)\b",
                r"\b(?:regular|standard|earlier)?\s*(?:triage|categorization|text|guidelines)\b",
            )
        ),
    ),
    # 4. Role impersonation / System and agent headers
    (
        "role_impersonation",
        re.compile(
            r"(?:^|\n|[\r\n;\|\[])\s*(?:system|system\s*message|system\s*notification|system\s*instruction|admin\s*bot|server\s*root\s*daemon|system\s*audit\s*log|it\s*helpdesk\s*supervisor|dispatch\s*automation\s*bot|assigned\s*agent|agent\s*triage\s*note|vip\s*escalation)\s*(?::|\]|###|\-\->|override|rule|enforce|redirect|verified)",
            re.I,
        ),
    ),
    # 5. Direct classification commands (set/mark/classify/route category/priority to/as target)
    (
        "classification_command",
        # A command verb, then a link word ("to", "as", "under", or "category ... level"), then a
        # category or priority value. (The original also allowed "category ... as/to/under" as the
        # link, but that always contains a plain "as/to/under" after the verb, so it adds nothing.)
        _lines(
            _seq(
                r"\b(?:set|mark|classify|categorize|categorise|assign|reclassify|route|override)\b",
                r"\b(?:as|to|under)\b",
                rf"\b(?:{CATS_PATTERN}|{PRIOS_PATTERN}|maximum)\b",
            ),
            _seq(
                r"\b(?:set|mark|classify|categorize|categorise|assign|reclassify|route|override)\b",
                r"\b(?:category|priority|urgency)\b",
                r"\blevel\b",
                rf"\b(?:{CATS_PATTERN}|{PRIOS_PATTERN}|maximum)\b",
            ),
        ),
    ),
    (
        "polite_or_imperative_request",
        _lines(
            _seq(
                r"\b(?:please|kindly|could\s*you|would\s*you)\b",
                r"\b(?:set|mark|classify|assign|route)\b",
                r"\b(?:as|to|under)\b",
                rf"\b(?:{CATS_PATTERN}|{PRIOS_PATTERN})\b",
            )
        ),
    ),
    (
        "foreign_classification_command",
        _lines(
            _seq(
                r"(?:veuillez|clasifique|kategorisieren|kategorie-zuordnung)",
                rf"\b(?:{CATS_PATTERN}|{PRIOS_PATTERN})\b",
            )
        ),
    ),
    # 6. Priority inflation / Executive escalation commands
    (
        "executive_priority_inflation",
        _lines(
            _seq(
                r"\b(?:ceo|cfo|coo|board(?:\s*of\s*directors)?|executive|leadership|site\s*director)\b",
                r"\b(?:mandate|orders?|escalation|instructed|requires?|requested)\b",
                r"\b(?:urgent|priority\s*(?:must\s*be\s*)?urgent|mark\s*urgent)\b",
            )
        ),
    ),
]


def inspect_ticket(text: str) -> InjectionGuardResult:
    """
    Scan ticket text for prompt-injection attacks.

    Args:
        text: Raw combined problem text (title + description).

    Returns:
        InjectionGuardResult with boolean flag, confidence score (0.0 or 1.0),
        and list of matched rule identifiers. NEVER includes raw ticket text.
    """
    if not text or not text.strip():
        return InjectionGuardResult(is_injection=False, confidence_score=0.0, matched_rules=[])

    normalized = normalize_text_for_guard(text)
    matched_rules: list[str] = []

    for rule_name, rule_regex in GUARD_RULES:
        # Check both normalized text and original text
        if rule_regex.search(normalized) or rule_regex.search(text):
            matched_rules.append(rule_name)

    is_detected = len(matched_rules) > 0
    score = 1.0 if is_detected else 0.0

    return InjectionGuardResult(
        is_injection=is_detected,
        confidence_score=score,
        matched_rules=matched_rules,
    )
