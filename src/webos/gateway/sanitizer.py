"""
Deterministic PII regex sanitizer and local data air-gap.
"""

import re
from typing import Tuple, Dict


class PIISanitizer:
    """
    Redacts sensitive personal information (emails, phone numbers, street addresses)
    with deterministic placeholder tokens before sending to external models,
    and accurately rehydrates the original data locally.
    """

    # Email pattern
    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )

    # Phone pattern (International & Domestic formats, e.g., +1 555-0199, (555) 019-9234, +91 9876543210)
    PHONE_PATTERN = re.compile(
        r"(?:\+?\d{1,3}[-.\s]*)?(?:\(?\d{2,4}\)?[-.\s]*)?\d{3,4}[-.\s]*\d{3,4}\b"
    )

    # Street address pattern
    ADDRESS_PATTERN = re.compile(
        r"\b\d{1,5}\s+[A-Za-z0-9\s,.-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Way)\b",
        re.IGNORECASE,
    )

    def redact(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Scrubs PII from the text, returning the sanitized string and a token map.
        Example: 'Contact john@example.com' -> ('Contact <USER_EMAIL_1>', {'<USER_EMAIL_1>': 'john@example.com'})
        """
        token_map: Dict[str, str] = {}
        reverse_map: Dict[str, str] = {}
        counter = {"email": 1, "phone": 1, "address": 1}

        # 1. Redact Emails
        def replace_email(match: re.Match) -> str:
            val = match.group(0)
            if val in reverse_map:
                return reverse_map[val]
            token = f"<USER_EMAIL_{counter['email']}>"
            counter["email"] += 1
            token_map[token] = val
            reverse_map[val] = token
            return token

        sanitized = self.EMAIL_PATTERN.sub(replace_email, text)

        # 2. Redact Phone Numbers
        def replace_phone(match: re.Match) -> str:
            val = match.group(0).strip()
            # Filter out short digit strings that are likely not phone numbers
            digits = re.sub(r"\D", "", val)
            if len(digits) < 7:
                return match.group(0)
            if val in reverse_map:
                return reverse_map[val]
            token = f"<USER_PHONE_{counter['phone']}>"
            counter["phone"] += 1
            token_map[token] = val
            reverse_map[val] = token
            return token

        sanitized = self.PHONE_PATTERN.sub(replace_phone, sanitized)

        # 3. Redact Addresses
        def replace_address(match: re.Match) -> str:
            val = match.group(0).strip()
            if val in reverse_map:
                return reverse_map[val]
            token = f"<USER_ADDRESS_{counter['address']}>"
            counter["address"] += 1
            token_map[token] = val
            reverse_map[val] = token
            return token

        sanitized = self.ADDRESS_PATTERN.sub(replace_address, sanitized)

        return sanitized, token_map

    def rehydrate(self, text: str, token_map: Dict[str, str]) -> str:
        """
        Restores sanitized tokens back to their original values.
        """
        result = text
        for token, original_val in token_map.items():
            result = result.replace(token, original_val)
        return result
