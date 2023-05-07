import base64
import hashlib
import hmac
import os
import secrets
from hashlib import pbkdf2_hmac

from django.conf import settings
from rest_framework.exceptions import ValidationError

from django_hmac_authentication.aes import aes_crypt
from django_hmac_authentication.models import ApiSecret

encoding = 'utf-8'
hash_func = 'sha256'

user_model = settings.AUTH_USER_MODEL
max_hmacs_per_user = getattr(settings, 'MAX_HMACS_PER_USER', 10)

digests_map = {
    'HMAC-SHA512': hashlib.sha512,
    'HMAC-SHA384': hashlib.sha384,
    'HMAC-SHA256': hashlib.sha256,
}


def aes_encrypt_hmac_secret() -> tuple:
    salt = os.urandom(24)
    iv = salt[-16:]
    enc_key = pbkdf2_hmac(hash_func, settings.SECRET_KEY.encode(encoding), salt, 1000)

    hmac_secret = secrets.token_bytes(32)
    encrypted = aes_crypt(hmac_secret, enc_key, iv)
    return hmac_secret, encrypted, enc_key, salt


def aes_decrypt_hmac_secret(encrypted: bytes, salt: bytes) -> bytes:
    enc_key = pbkdf2_hmac(hash_func, settings.SECRET_KEY.encode(encoding), salt, 1000)

    return aes_crypt(encrypted, enc_key, salt[-16:], False)


def create_shared_secret_for_user(user: user_model):
    n_user_hmacs = ApiSecret.objects.filter(user=user).count()
    if n_user_hmacs >= max_hmacs_per_user:
        raise ValidationError('Maximum API secrets limit reached for user')
    hmac_secret, encrypted, enc_key, salt = aes_encrypt_hmac_secret()
    api_secret = ApiSecret(user=user, secret=encrypted.hex(), salt=salt.hex())
    api_secret.save()
    return api_secret.id, base64.b64encode(hmac_secret).decode('utf-8')


def hash_content(digest, content):
    if digest not in digests_map.keys():
        raise ValidationError(f'Unsupported HMAC function {digest}')

    func = digests_map[digest]
    hasher = func()
    hasher.update(content)
    hashed_bytes = hasher.digest()
    base64_encoded_bytes = base64.b64encode(hashed_bytes)
    content_hash = base64_encoded_bytes.decode('utf-8')
    return content_hash


def message_signature(message: str, secret: bytes, digest):
    if digest not in digests_map.keys():
        raise ValidationError(f'Unsupported HMAC function {digest}')
    encoded_string_to_sign = message.encode(encoding)
    hashed_bytes = hmac.digest(
        secret, encoded_string_to_sign, digest=digests_map[digest]
    )
    encoded_signature = base64.b64encode(hashed_bytes)
    signature = encoded_signature.decode(encoding)
    return signature