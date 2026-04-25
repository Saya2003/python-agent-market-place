"""Safely generate Circle entity secret ciphertext from .env values."""

import re
import sys

from circle.web3 import utils
from dotenv import dotenv_values


RAW_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def main() -> int:
    """Validate env values and print ciphertext once."""
    values = dotenv_values(".env")
    api_key = (values.get("CIRCLE_API_KEY") or "").strip()
    entity_secret = (values.get("CIRCLE_ENTITY_SECRET") or "").strip()

    if not api_key:
        print("ERROR: CIRCLE_API_KEY is missing in .env")
        return 1

    if not entity_secret:
        print("ERROR: CIRCLE_ENTITY_SECRET is missing in .env")
        return 1

    if not RAW_HEX_PATTERN.fullmatch(entity_secret):
        print("ERROR: CIRCLE_ENTITY_SECRET is not a raw 64-char hex value.")
        print("It looks like ciphertext already, or is malformed.")
        print("Use a fresh raw entity secret to generate ciphertext.")
        return 1

    try:
        ciphertext = utils.generate_entity_secret_ciphertext(api_key, entity_secret)
    except Exception as exc:
        print("ERROR: Failed to generate ciphertext from Circle SDK.")
        print("Check that CIRCLE_API_KEY uses the new 3-part format:")
        print("  TEST_API_KEY:<key_id>:<key_secret>")
        print(f"Details: {exc}")
        return 1

    print("\n" + "=" * 64)
    print("COPY THIS CIPHERTEXT INTO CIRCLE CONSOLE (Entity Secret Ciphertext)")
    print("=" * 64)
    print(ciphertext)
    print("=" * 64)
    print("Next: Replace CIRCLE_ENTITY_SECRET in .env with this ciphertext.")
    print("=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())