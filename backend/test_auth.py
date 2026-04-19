"""Test auth module — JWT + bcrypt roundtrip."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Set test env vars BEFORE importing auth module
os.environ['AUTH_USERNAME'] = 'admin'
os.environ['JWT_SECRET'] = 'test_secret_123'
os.environ['TOTP_SECRET'] = ''
os.environ['EMERGENCY_BYPASS_CODE'] = 'bypass123'

import bcrypt
# Generate a fresh hash for testing
test_pw = 'admin'
test_hash = bcrypt.hashpw(test_pw.encode(), bcrypt.gensalt()).decode()
os.environ['AUTH_PASSWORD_HASH'] = test_hash

from app.auth import verify_password, create_access_token, verify_token

# Test 1: Password verification
assert verify_password('admin', test_hash), "FAIL: correct password should verify"
assert not verify_password('wrong', test_hash), "FAIL: wrong password should not verify"
print("PASS: Password verification works")

# Test 2: JWT roundtrip
token, exp = create_access_token('admin')
payload = verify_token(token)
assert payload['sub'] == 'admin', f"FAIL: expected 'admin', got {payload['sub']}"
print("PASS: JWT roundtrip works")

# Test 3: Invalid JWT
try:
    verify_token("invalid.token.here")
    assert False, "FAIL: invalid token should raise"
except Exception:
    print("PASS: Invalid JWT rejected")

print("\nALL AUTH TESTS PASSED")
