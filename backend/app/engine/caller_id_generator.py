"""
Dynamic Caller ID Generator — Local Presence Engine

Generates a caller ID that matches the destination number's country code
and area code (NDC), with randomized subscriber digits. This makes every
outbound call appear to originate from the same local region as the person
being called.

Uses Google's `phonenumbers` library exclusively — zero hardcoded country
logic. Works for any country in the world automatically.
"""

import random
import logging
import phonenumbers
from phonenumbers import PhoneNumberType, NumberParseException

logger = logging.getLogger(__name__)


def generate_local_caller_id(destination: str) -> str:
    """
    Generate a local-presence caller ID matching the destination's region.

    Strategy:
        1. Parse destination → extract country code + national number
        2. Determine the NDC (area code) length for that country/region
        3. Keep country code + NDC from destination intact
        4. Randomly generate subscriber digits to fill correct length
        5. Validate with phonenumbers — retry up to 5 times
        6. Fallback: country code + fully random valid-length national number

    Args:
        destination: Phone number in E.164 or dialable format (e.g. "+19142221234")

    Returns:
        E.164 formatted caller ID string (e.g. "+19147384921")
    """
    try:
        parsed = phonenumbers.parse(destination, None)
    except NumberParseException:
        # Try with US default if no country code prefix
        try:
            parsed = phonenumbers.parse(destination, "US")
        except NumberParseException:
            logger.warning(f"Cannot parse destination '{destination}' — returning raw")
            return destination

    country_code = parsed.country_code
    region_code = phonenumbers.region_code_for_number(parsed)
    national_number_str = str(parsed.national_number)

    # ── Determine NDC (area code) length using phonenumbers metadata ─────
    # The library's metadata for each region tells us the expected national
    # number length(s) and, via example numbers, the NDC portion length.
    ndc_length = _get_ndc_length(parsed, region_code)

    if ndc_length <= 0 or ndc_length >= len(national_number_str):
        # Can't determine a meaningful NDC — use the first half as prefix
        ndc_length = max(1, len(national_number_str) // 2)

    ndc = national_number_str[:ndc_length]
    subscriber_length = len(national_number_str) - ndc_length

    if subscriber_length <= 0:
        subscriber_length = 4  # safe minimum

    # ── Generate and validate ────────────────────────────────────────────
    for attempt in range(5):
        subscriber = _random_digits(subscriber_length)
        candidate_national = ndc + subscriber
        candidate_str = f"+{country_code}{candidate_national}"

        try:
            candidate_parsed = phonenumbers.parse(candidate_str, None)
            if phonenumbers.is_valid_number(candidate_parsed):
                logger.debug(
                    f"Dynamic CID generated: {candidate_str} "
                    f"(country={region_code}, NDC={ndc}, attempt={attempt + 1})"
                )
                return phonenumbers.format_number(
                    candidate_parsed,
                    phonenumbers.PhoneNumberFormat.E164
                )
        except NumberParseException:
            continue

    # ── Fallback: country code + fully random valid-length national number
    logger.warning(
        f"All 5 retries failed for destination={destination}, "
        f"falling back to fully random national number"
    )
    return _fallback_random_number(country_code, region_code, len(national_number_str))


def _get_ndc_length(parsed_number, region_code: str) -> int:
    """
    Determine the NDC (area code) length for a given number using the
    phonenumbers library's internal metadata.

    The library provides number_type + format patterns that let us infer
    the NDC boundary without hardcoding any country rules.
    """
    if not region_code:
        return 0

    try:
        # Use phonenumbers' built-in NDC length calculation
        # length_of_geographical_area_code returns the NDC length for
        # fixed-line and mobile numbers with geographical assignment
        ndc_len = phonenumbers.length_of_geographical_area_code(parsed_number)
        if ndc_len > 0:
            return ndc_len

        # For mobile numbers or countries without geographical area codes,
        # use the national destination code length instead
        ndc_len = phonenumbers.length_of_national_destination_code(parsed_number)
        if ndc_len > 0:
            return ndc_len

    except Exception as e:
        logger.debug(f"NDC length detection failed for {region_code}: {e}")

    # Last resort: heuristic based on national number length
    national_str = str(parsed_number.national_number)
    total_len = len(national_str)

    if total_len <= 7:
        return max(1, total_len - 4)
    elif total_len <= 10:
        return max(2, total_len - 7)
    else:
        return max(3, total_len - 8)


def _random_digits(length: int) -> str:
    """Generate a string of random digits of the given length.
    First digit is never 0 to avoid invalid subscriber numbers."""
    if length <= 0:
        return ""
    first = str(random.randint(1, 9))
    rest = "".join(str(random.randint(0, 9)) for _ in range(length - 1))
    return first + rest


def _fallback_random_number(country_code: int, region_code: str, national_length: int) -> str:
    """Generate a fully random national number as last resort."""
    for _ in range(10):
        national = _random_digits(national_length)
        candidate = f"+{country_code}{national}"
        try:
            parsed = phonenumbers.parse(candidate, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except NumberParseException:
            continue

    # Absolute last resort — return the raw string even if not validated
    return f"+{country_code}{_random_digits(national_length)}"
