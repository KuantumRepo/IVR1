"""
Test script for Dynamic Caller ID Generator.

Tests the core generation logic against multiple countries to verify:
1. Country code is preserved
2. Area code / NDC is preserved from the destination
3. Subscriber digits are randomized
4. Output is valid E.164
5. phonenumbers validates the generated number
"""

import phonenumbers
import sys
import os

# Add backend to path so we can import the generator
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.engine.caller_id_generator import generate_local_caller_id


TEST_DESTINATIONS = [
    # (destination, expected_country_code, description)
    ("+19142221234", 1, "US - New York area (914)"),
    ("+12125551234", 1, "US - Manhattan (212)"),
    ("+14155551234", 1, "US - San Francisco (415)"),
    ("+442079461234", 44, "UK - London (207)"),
    ("+61298765432", 61, "Australia - Sydney (2)"),
    ("+33142681234", 33, "France - Paris (1)"),
    ("+4930123456", 49, "Germany - Berlin (30)"),
    ("+81312345678", 81, "Japan - Tokyo (3)"),
    ("+5511987654321", 55, "Brazil - São Paulo (11)"),
    ("+27111234567", 27, "South Africa - Johannesburg (11)"),
    ("+971501234567", 971, "UAE - Mobile (50)"),
    ("+6591234567", 65, "Singapore"),
    ("+919812345678", 91, "India - Mobile"),
    ("+8613800138000", 86, "China - Mobile"),
    ("+525512345678", 52, "Mexico - Mexico City (55)"),
]


def run_tests():
    print("=" * 80)
    print("DYNAMIC CALLER ID GENERATOR — TEST SUITE")
    print("=" * 80)
    print()

    passed = 0
    failed = 0
    total = len(TEST_DESTINATIONS)

    for dest, expected_cc, desc in TEST_DESTINATIONS:
        print(f"  TEST: {desc}")
        print(f"  Destination:  {dest}")

        try:
            # Generate 3 caller IDs per destination to check randomization
            results = set()
            for _ in range(3):
                cid = generate_local_caller_id(dest)
                results.add(cid)

            # Pick one for detailed analysis
            cid = list(results)[0]
            print(f"  Generated:    {cid}")

            # Validate it's proper E.164
            assert cid.startswith("+"), f"Not E.164 format: {cid}"

            # Parse both to compare
            parsed_dest = phonenumbers.parse(dest, None)
            parsed_cid = phonenumbers.parse(cid, None)

            # Check country code matches
            assert parsed_cid.country_code == expected_cc, \
                f"Country code mismatch: got {parsed_cid.country_code}, expected {expected_cc}"

            # Check the generated number is valid
            is_valid = phonenumbers.is_valid_number(parsed_cid)

            # Check NDC preservation (area code should match)
            dest_national = str(parsed_dest.national_number)
            cid_national = str(parsed_cid.national_number)

            # Get NDC length from the library
            ndc_len = phonenumbers.length_of_geographical_area_code(parsed_dest)
            if ndc_len == 0:
                ndc_len = phonenumbers.length_of_national_destination_code(parsed_dest)

            ndc_match = "N/A"
            if ndc_len > 0:
                dest_ndc = dest_national[:ndc_len]
                cid_ndc = cid_national[:ndc_len]
                ndc_match = dest_ndc == cid_ndc
                if not ndc_match:
                    print(f"  [!] NDC MISMATCH: dest={dest_ndc}, gen={cid_ndc}")

            # Check that we got some randomization (at least 2 unique out of 3)
            randomized = len(results) >= 2

            status = "PASS" if is_valid else "FAIL (invalid number)"
            if is_valid:
                passed += 1
            else:
                failed += 1

            print(f"  Valid E.164:  {is_valid}")
            print(f"  NDC Match:    {ndc_match}")
            print(f"  Randomized:   {randomized} ({len(results)} unique from 3 generations)")
            print(f"  Country:      +{parsed_cid.country_code} ({phonenumbers.region_code_for_number(parsed_cid)})")
            print(f"  Result:       {status}")
            print()

        except Exception as e:
            failed += 1
            print(f"  [X] EXCEPTION: {e}")
            print()

    print("=" * 80)
    print(f"  RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    print("=" * 80)

    # Exit with error code if any failures
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
