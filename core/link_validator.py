"""Link Validator — pre-governance check for fabricated URLs.

Extracts URLs from bot output, validates them via HTTP HEAD,
and detects dead links or homepage redirects (non-existent listings).
"""

import re
import logging
from dataclasses import dataclass, field

import requests

logger = logging.getLogger("core.link_validator")

_SAFE_DOMAINS = {
    "wa.me",
    "maps.google.com",
    "maps.app.goo.gl",
    "t.me",
    "mailto:",
    "tel:",
}

_URL_PATTERN = re.compile(r"https?://[^\s\)\]\}\"'<>,]+")

_DEFAULT_HOMEPAGE = "https://www.raywhite.co.id"
_HEAD_TIMEOUT_S = 10


@dataclass
class LinkValidationResult:
    """Result of link validation."""
    valid: bool
    urls_checked: list[str] = field(default_factory=list)
    invalid_urls: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)


def _extract_urls(text: str) -> list[str]:
    """Extract URLs from text, excluding safe-listed domains."""
    raw_urls = _URL_PATTERN.findall(text)
    filtered: list[str] = []
    for url in raw_urls:
        url = url.rstrip(".,;:!?)")
        if any(safe in url for safe in _SAFE_DOMAINS):
            continue
        filtered.append(url)
    return filtered


def _normalize_homepage(url: str) -> str:
    """Normalize homepage URL for comparison."""
    return url.rstrip("/").lower()


def validate_links(
    text: str,
    homepage_url: str = _DEFAULT_HOMEPAGE,
) -> LinkValidationResult:
    """Validate all URLs in text.

    A URL is invalid if:
    - HTTP HEAD returns 404, 410, or 5xx
    - Connection error or timeout
    - Final URL after redirects matches homepage (listing doesn't exist)

    Args:
        text: Bot output text containing potential URLs.
        homepage_url: The office homepage URL. Redirects here = invalid listing.

    Returns:
        LinkValidationResult with valid=True if all links are good.
    """
    urls = _extract_urls(text)
    if not urls:
        return LinkValidationResult(valid=True)

    invalid_urls: list[str] = []
    reasons: dict[str, str] = {}
    normalized_homepage = _normalize_homepage(homepage_url)

    for url in urls:
        try:
            resp = requests.head(
                url,
                timeout=_HEAD_TIMEOUT_S,
                allow_redirects=True,
                headers={"User-Agent": "DOF-LinkValidator/1.0"},
            )

            if resp.status_code in (404, 410) or resp.status_code >= 500:
                invalid_urls.append(url)
                reasons[url] = f"HTTP {resp.status_code}"
                continue

            final_url = _normalize_homepage(resp.url)
            if final_url == normalized_homepage:
                invalid_urls.append(url)
                reasons[url] = "redirected to homepage (listing does not exist)"
                continue

        except requests.Timeout:
            invalid_urls.append(url)
            reasons[url] = "connection timeout"
        except requests.ConnectionError:
            invalid_urls.append(url)
            reasons[url] = "connection error"
        except requests.RequestException as e:
            invalid_urls.append(url)
            reasons[url] = f"request error: {e}"

    result = LinkValidationResult(
        valid=len(invalid_urls) == 0,
        urls_checked=urls,
        invalid_urls=invalid_urls,
        reasons=reasons,
    )

    if invalid_urls:
        logger.warning(f"Invalid links detected: {reasons}")

    return result
