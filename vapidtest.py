# Run this in your Flask shell or as a temporary script
import base64

def quick_test_keys():
    current_private = 'MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgJEK++bJ3qsf4NV4jkIHX/RHFlzs0ZlaBe7AK8F865T6hRANCAAQyKR43hjnqpSX00q1vq++d4mz7QELsN8pcmUJAYJjbepEqXm4lLfpzdJYmpVW+/p6j7mu+Cc05vxG/V1Qpx0Rl'

    try:
        der_bytes = base64.b64decode(current_private)
        print(f"DER bytes length: {len(der_bytes)}")
        print(f"DER bytes (first 20): {[hex(b) for b in der_bytes[:20]]}")

        # The private key should be 32 bytes embedded in this structure
        # For PKCS#8 DER format, it's typically around byte 36-68
        private_key_candidate = der_bytes[36:68]
        print(f"Extracted private key length: {len(private_key_candidate)}")
        print(f"Private key (first 10 bytes): {[hex(b) for b in private_key_candidate[:10]]}")

        if len(private_key_candidate) == 32:
            print("✅ Successfully extracted 32-byte private key")
            return True
        else:
            print("❌ Private key extraction failed")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False

quick_test_keys()