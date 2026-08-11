from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_keypair() -> tuple[str, str]:
    """
    Generate a 2048-bit RSA key pair serialized as PEM strings.

    Public key: shared with others so they can encrypt an AES session key for this user.
    Private key: kept by this user to decrypt AES keys others send to them.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_key_pem, public_key_pem
