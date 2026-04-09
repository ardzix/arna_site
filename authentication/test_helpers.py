from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
import datetime

def generate_rsa_keypair():
    """Generates an RSA keypair for testing RS256 JWT signatures."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem, public_pem

def make_jwt(private_pem, user_id, org_id, roles=None, is_owner=False, expired=False, aud="arnasite"):
    """Creates a signed JWT matching Arna SSO claims format."""
    payload = {
        "user_id": str(user_id),
        "org_id": str(org_id),
        "email": "admin@arna.com",
        "roles": roles or [],
        "permissions": [],
        "is_owner": is_owner,
        "aud": aud,
        "exp": datetime.datetime.utcnow() + (
            datetime.timedelta(hours=-1) if expired
            else datetime.timedelta(hours=1)
        )
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")
