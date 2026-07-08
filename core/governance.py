"""
Constitution Hard Enforcement — FASE 0.

Hard rules block execution. Soft rules score output (future).
Enforced at crew output level before delivery.

Rules are defined in dof.constitution.yml (canonical source) and loaded
at module init. The YAML is merged with the in-code defaults so the
system works even if the YAML file is missing.
"""

import os
import re
import logging
from dataclasses import dataclass

import yaml

logger = logging.getLogger("core.governance")

# ─────────────────────────────────────────────────────────────────────
# YAML loader
# ─────────────────────────────────────────────────────────────────────

_CONSTITUTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dof.constitution.yml",
)


def load_constitution(path: str | None = None) -> dict:
    """Load dof.constitution.yml and return parsed dict. Returns {} on failure."""
    path = path or _CONSTITUTION_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Constitution file not found: {path} — using in-code defaults")
        return {}
    except Exception as e:
        logger.warning(f"Error loading constitution: {e} — using in-code defaults")
        return {}


_CONSTITUTION: dict = load_constitution()


@dataclass
class GovernanceResult:
    """Result of governance check."""
    passed: bool
    score: float  # 0.0 - 1.0
    violations: list[str]
    warnings: list[str]


def _check_no_hallucination(text: str) -> bool:
    """Check that unsubstantiated claims have nearby URLs."""
    claim_phrases = [
        "according to recent studies",
        "statistics show",
        "data confirms",
        "research demonstrates",
        "según estudios recientes",
        "las estadísticas muestran",
        "datos confirman",
        "investigaciones demuestran",
    ]
    text_lower = text.lower()
    has_urls = "http" in text_lower
    for phrase in claim_phrases:
        if phrase in text_lower and not has_urls:
            return False
    return True


def _check_invalid_links(text: str, context: str = "") -> bool:
    """Check if link validation context reports invalid URLs.

    The link_validator pre-check writes results to context:
    - "INVALID_LINKS:<url1>,<url2>" = invalid URLs found
    - "LINKS_VALIDATED:OK" or empty = no issues

    Returns True (pass) if no invalid links.
    """
    if context.startswith("INVALID_LINKS:"):
        return False
    return True


# Known third-party property portals (Indonesian market). Platform-domain rule:
# agent replies must source listings exclusively from the client network
# (e.g. raywhite.co.id), never from external portals — neither as links nor
# as cited "Sources".
_THIRD_PARTY_PORTAL_RE = re.compile(
    r"\b(?:99\.co|rumah123\.com|rumah\.com|lamudi\.co(?:\.id)?|olx\.co\.id|"
    r"propertyguru\.com(?:\.\w+)?|dotproperty\.id|pinhome\.id|travelio\.com|"
    r"brighton\.co\.id)\b",
    re.IGNORECASE,
)


# Hard rules — BLOCK if violated
HARD_RULES = [
    {
        "id": "NO_HALLUCINATION_CLAIM",
        "description": "Must not assert fabricated data without source",
        "check": lambda text: _check_no_hallucination(text),
    },
    {
        "id": "LANGUAGE_COMPLIANCE",
        "description": "Response must be in a supported language (EN, ID, MS, ZH) or structured data",
        "check": lambda text: _check_language(text),
    },
    {
        "id": "NO_EMPTY_OUTPUT",
        "description": "Output cannot be empty or a placeholder",
        "check": lambda text: len(text.strip()) > 50 and text.strip() not in [
            "No output", "Error", "N/A", "TODO", "placeholder",
        ],
    },
    {
        "id": "MAX_LENGTH",
        "description": "Output cannot exceed 50K chars",
        "check": lambda text: len(text) <= 50000,
    },
    {
        "id": "TRANSITION_REPLY_MISUSE",
        "description": "Transition phrase must match the actual reply content",
        "check": lambda text: _check_transition_misuse(text),
    },
    {
        "id": "INVALID_LINKS",
        "description": "Output must not contain dead or fabricated URLs",
        "check": _check_invalid_links,
    },
    {
        "id": "NO_THIRD_PARTY_PORTAL",
        "description": "Must not source or link third-party property portals",
        "check": lambda text: not _THIRD_PARTY_PORTAL_RE.search(text),
    },
]

# Soft rules — WARN but don't block
SOFT_RULES = [
    {
        "id": "HAS_SOURCES",
        "description": "Should include source URLs",
        "check": lambda text: bool(re.search(r'https?://', text)),
        "weight": 0.3,
    },
    {
        "id": "STRUCTURED_OUTPUT",
        "description": "Should have clear structure (headers, bullets)",
        "check": lambda text: any(marker in text for marker in ["##", "- ", "* ", "1.", "•"]),
        "weight": 0.2,
    },
    {
        "id": "CONCISENESS",
        "description": "Should not have repetitive paragraphs",
        "check": lambda text: _check_no_repetition(text),
        "weight": 0.2,
    },
    {
        "id": "ACTIONABLE",
        "description": "Should include actionable steps or recommendations",
        "check": lambda text: any(
            kw in text.lower()
            for kw in ["recommend", "next step", "action", "implement", "recomend", "siguiente paso"]
        ),
        "weight": 0.3,
    },
]


def _sync_rules_from_yaml(constitution: dict) -> None:
    """Ensure every rule_key in dof.constitution.yml has a matching entry in
    HARD_RULES / SOFT_RULES.  Logs warnings for YAML-only rules that have no
    in-code check function (they cannot be enforced without code).
    This guarantees the YAML is the canonical *registry* while Python remains
    the enforcement engine.
    """
    if not constitution:
        return

    rules_section = constitution.get("rules", {})
    hard_ids = {r["id"] for r in HARD_RULES}
    soft_ids = {r["id"] for r in SOFT_RULES}

    for yaml_rule in rules_section.get("hard", []):
        key = yaml_rule.get("rule_key", "")
        if key and key not in hard_ids:
            logger.info(f"YAML hard rule '{key}' has no in-code check — registry-only")

    for yaml_rule in rules_section.get("soft", []):
        key = yaml_rule.get("rule_key", "")
        if key and key not in soft_ids:
            logger.info(f"YAML soft rule '{key}' has no in-code check — registry-only")


_sync_rules_from_yaml(_CONSTITUTION)


def _check_language(text: str) -> bool:
    """Check if text is in a supported language (EN, ID, MS, ZH) or structured data."""
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return True

    # Mandarin: CJK Unified Ideographs
    cjk_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if len(text) > 0 and cjk_chars / len(text) > 0.10:
        return True

    # Word-based detection for EN, ID, MS
    words = text.lower().split()[:200]
    if not words:
        return False

    _LANGUAGE_MARKERS = {
        "en": {"the", "is", "and", "of", "to", "in", "for", "with", "that", "this",
               "are", "was", "has", "have", "from", "by", "an", "be", "as", "on"},
        "id": {"yang", "dan", "di", "ini", "itu", "untuk", "dengan", "dari", "ada",
               "tidak", "akan", "bisa", "sudah", "juga", "atau", "saya", "kami",
               "mereka", "seperti", "pada"},
        "ms": {"yang", "dan", "di", "ini", "itu", "untuk", "dengan", "dari", "ada",
               "tidak", "akan", "boleh", "sudah", "juga", "atau", "saya", "kami",
               "mereka", "seperti", "pada"},
    }

    for markers in _LANGUAGE_MARKERS.values():
        count = sum(1 for w in words if w in markers)
        if count / len(words) > 0.05:
            return True

    return False


# ── Transition reply misuse detection ────────────────────────────────

_TRANSITION_CATEGORIES: dict[str, dict] = {
    "search_listing": {
        "transitions": [
            "sedang mencari properti", "searching for properties",
            "正在搜索房产", "sedang mencari hartanah",
            "mencari listing", "looking for listings",
            "sedang cari properti",
        ],
        "content_keywords": [
            "harga", "bedroom", "kamar tidur", "luas", "sqm", "listing",
            "properti", "price", "rumah", "apartemen", "ruko", "tanah",
            "价格", "房产", "卧室", "面积", "平方米",
            "bilik tidur", "hartanah",
        ],
    },
    "contact_inquiry": {
        "transitions": [
            "saya catat dulu", "let me note that down",
            "我先记录一下", "saya catatkan dahulu",
            "saya catat ya", "noted, let me",
        ],
        "content_keywords": [
            "hubungi", "kontak", "telepon", "whatsapp", "email", "agent",
            "nama", "contact", "call", "phone", "reach",
            "联系", "电话", "邮件", "经纪人",
            "hubungi", "ejen",
        ],
    },
    "general_info": {
        "transitions": [
            "saya cek dulu", "let me check", "让我查一下",
            "saya semak dahulu", "saya lihat dulu", "checking",
        ],
        "content_keywords": [],
    },
}


def _check_transition_misuse(text: str) -> bool:
    """Check that transition phrases match the actual reply content.

    Returns True (pass) if no misuse detected.
    Returns False (violation) if transition category doesn't match content.
    """
    text_lower = text.lower()

    matched_category: str | None = None
    for category, config in _TRANSITION_CATEGORIES.items():
        for phrase in config["transitions"]:
            if phrase in text_lower:
                matched_category = category
                break
        if matched_category:
            break

    if matched_category is None:
        return True

    if matched_category == "general_info":
        return True

    scores: dict[str, int] = {}
    for category, config in _TRANSITION_CATEGORIES.items():
        if category == "general_info":
            continue
        keywords = config["content_keywords"]
        scores[category] = sum(1 for kw in keywords if kw in text_lower)

    if not scores:
        return True

    matched_score = scores.get(matched_category, 0)
    max_score = max(scores.values())

    if matched_score == 0 and max_score > 0:
        return False

    if matched_score < max_score:
        return False

    return True


def _check_no_repetition(text: str) -> bool:
    """Check for excessive paragraph repetition."""
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
    if len(paragraphs) < 3:
        return True
    seen = set()
    duplicates = 0
    for p in paragraphs:
        normalized = p[:100].lower()
        if normalized in seen:
            duplicates += 1
        seen.add(normalized)
    return duplicates < len(paragraphs) * 0.3


def get_constitution() -> dict:
    """Return the loaded constitution dict (from dof.constitution.yml)."""
    return _CONSTITUTION


def _extract_python_blocks(text: str) -> list[str]:
    """Extract Python code blocks from markdown-formatted output."""
    blocks = []
    pattern = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)
    for match in pattern.finditer(text):
        code = match.group(1).strip()
        if code:
            blocks.append(code)
    return blocks


class ConstitutionEnforcer:
    """Enforces governance rules on agent output."""

    def __init__(self):
        from core.ast_verifier import ASTVerifier
        self._ast_verifier = ASTVerifier()

    def check(self, output: str, context: str = "") -> GovernanceResult:
        """Run all governance checks on output.

        Returns GovernanceResult with pass/fail, score, violations, warnings.
        """
        violations = []
        warnings = []

        # AST verification on embedded code blocks
        code_blocks = _extract_python_blocks(output)
        for i, block in enumerate(code_blocks):
            ast_result = self._ast_verifier.verify(block)
            for v in ast_result.violations:
                label = f"[AST_VERIFY] Block {i+1}, line {v['line_number']}: {v['message']}"
                if v["severity"] == "block":
                    violations.append(label)
                else:
                    warnings.append(label)

        # Hard rules — any violation = fail
        for rule in HARD_RULES:
            try:
                check_fn = rule["check"]
                import inspect
                params = inspect.signature(check_fn).parameters
                if len(params) >= 2:
                    passed_check = check_fn(output, context)
                else:
                    passed_check = check_fn(output)
                if not passed_check:
                    violations.append(f"[{rule['id']}] {rule['description']}")
            except Exception as e:
                logger.warning(f"Hard rule '{rule['id']}' check error: {e}")

        # Soft rules — calculate score
        soft_score = 0.0
        total_weight = 0.0
        for rule in SOFT_RULES:
            weight = rule.get("weight", 0.25)
            total_weight += weight
            try:
                if rule["check"](output):
                    soft_score += weight
                else:
                    warnings.append(f"[{rule['id']}] {rule['description']}")
            except Exception as e:
                logger.warning(f"Soft rule '{rule['id']}' check error: {e}")

        normalized_score = soft_score / total_weight if total_weight > 0 else 0.0
        passed = len(violations) == 0

        if violations:
            logger.warning(f"Governance FAILED: {violations}")
        if warnings:
            logger.info(f"Governance warnings: {[w.split(']')[0] + ']' for w in warnings]}")

        return GovernanceResult(
            passed=passed,
            score=round(normalized_score, 2),
            violations=violations,
            warnings=warnings,
        )

    def enforce(self, output: str, context: str = "") -> tuple[bool, str]:
        """Check and return (passed, message).

        Use this for simple pass/fail enforcement.
        """
        result = self.check(output, context)
        if result.passed:
            return True, f"OK (score={result.score})"
        return False, f"BLOCKED: {'; '.join(result.violations)}"
