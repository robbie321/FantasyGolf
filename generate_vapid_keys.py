# generate_vapid_keys.py
# Run this script to generate new VAPID keys in the correct format

import base64
import os

def generate_vapid_keys_with_cryptography():
    """Generate VAPID keys using cryptography library"""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        print("Generating new VAPID keys using cryptography...")
        print("=" * 50)

        # Generate P-256 private key
        private_key = ec.generate_private_key(ec.SECP256R1())

        # Get private key as raw bytes (32 bytes for P-256)
        private_numbers = private_key.private_numbers()
        private_key_bytes = private_numbers.private_value.to_bytes(32, byteorder='big')

        # Get public key as uncompressed point (65 bytes: 0x04 + 32 bytes x + 32 bytes y)
        public_key = private_key.public_key()
        public_numbers = public_key.public_numbers()

        # Convert to uncompressed point format
        x_bytes = public_numbers.x.to_bytes(32, byteorder='big')
        y_bytes = public_numbers.y.to_bytes(32, byteorder='big')
        public_key_bytes = b'\x04' + x_bytes + y_bytes

        # Encode to base64url (without padding)
        private_key_b64 = base64.urlsafe_b64encode(private_key_bytes).decode('utf-8').rstrip('=')
        public_key_b64 = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')

        print("✅ New VAPID keys generated successfully!")
        print("\nReplace these in your config.py:")
        print("=" * 50)
        print(f"VAPID_PRIVATE_KEY = '{private_key_b64}'")
        print(f"VAPID_PUBLIC_KEY = '{public_key_b64}'")
        print("=" * 50)

        # Verify the keys are in the right format
        print(f"\nKey Details:")
        print(f"Private key length: {len(private_key_b64)} characters")
        print(f"Public key length: {len(public_key_b64)} characters")
        print(f"Private key bytes: {len(private_key_bytes)} bytes")
        print(f"Public key bytes: {len(public_key_bytes)} bytes")

        print(f"\n✅ Keys are in base64url format (correct for pywebpush)")

        return private_key_b64, public_key_b64

    except ImportError:
        print("❌ cryptography library not installed. Install it with:")
        print("pip install cryptography")
        return None, None
    except Exception as e:
        print(f"❌ Error generating keys with cryptography: {e}")
        return None, None

def generate_vapid_keys_simple():
    """Generate VAPID keys using simple random bytes"""
    print("Generating VAPID keys using random bytes...")
    print("=" * 50)

    # Generate 32 random bytes for private key
    private_key_bytes = os.urandom(32)

    # For public key, we'll use a placeholder since generating a proper EC public key
    # requires the cryptography library. This is just for testing.
    # Note: This won't work for actual push notifications, just for format reference
    public_key_bytes = b'\x04' + os.urandom(64)  # 0x04 + 64 random bytes

    # Encode to base64url
    private_key_b64 = base64.urlsafe_b64encode(private_key_bytes).decode('utf-8').rstrip('=')
    public_key_b64 = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')

    print("⚠️  WARNING: These are random keys for format reference only!")
    print("⚠️  They won't work for actual push notifications!")
    print("⚠️  Use the cryptography method or web-push CLI for real keys.")
    print("\nFormat example:")
    print("=" * 50)
    print(f"VAPID_PRIVATE_KEY = '{private_key_b64}'")
    print(f"VAPID_PUBLIC_KEY = '{public_key_b64}'")
    print("=" * 50)

    return private_key_b64, public_key_b64

def try_pywebpush():
    """Try to use pywebpush if available"""
    try:
        import pywebpush

        print("Trying pywebpush methods...")

        # Try different possible methods
        methods_to_try = [
            'generate_vapid_keys',
            'vapid_keys_generate',
            'VapidKey.generate',
        ]

        for method_name in methods_to_try:
            try:
                if hasattr(pywebpush, method_name):
                    method = getattr(pywebpush, method_name)
                    result = method()
                    print(f"✅ Found working method: {method_name}")
                    return result
            except Exception as e:
                continue

        # If no direct method found, check for VapidKey class
        if hasattr(pywebpush, 'VapidKey'):
            try:
                vapid = pywebpush.VapidKey()
                vapid.generate_key()

                private_key = vapid.private_key
                public_key = vapid.public_key

                print("✅ Generated keys using VapidKey class")
                print("=" * 50)
                print(f"VAPID_PRIVATE_KEY = '{private_key}'")
                print(f"VAPID_PUBLIC_KEY = '{public_key}'")
                print("=" * 50)

                return {'private_key': private_key, 'public_key': public_key}

            except Exception as e:
                print(f"VapidKey method failed: {e}")

        print("❌ No working VAPID key generation method found in pywebpush")
        return None

    except ImportError:
        print("pywebpush not available")
        return None

if __name__ == "__main__":
    print("VAPID Key Generator")
    print("=" * 50)

    # Try pywebpush first
    result = try_pywebpush()
    if result:
        print("\n📝 Update your config.py with the keys above")
        exit()

    # Try cryptography library
    private, public = generate_vapid_keys_with_cryptography()
    if private and public:
        print("\n📝 Update your config.py:")
        print("1. Replace VAPID_PRIVATE_KEY with the new private key")
        print("2. Replace VAPID_PUBLIC_KEY with the new public key")
        print("3. Keep your existing VAPID_CLAIM_EMAIL")
        print("4. Restart your Flask server")
        print("5. Re-subscribe to push notifications in your browser")
        exit()

    # Fallback to simple method (for format reference only)
    print("\nFalling back to format example...")
    generate_vapid_keys_simple()

    print("\n" + "=" * 50)
    print("RECOMMENDED: Install web-push CLI tool:")
    print("npm install -g web-push")
    print("web-push generate-vapid-keys")