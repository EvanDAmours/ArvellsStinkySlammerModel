"""Seal the site's data behind a shared password.

GitHub Pages serves every file to anyone with the link, so each JSON the jobs write is encrypted here (AES-256-GCM, key
from the password by PBKDF2-SHA256) and the plaintext removed; the page asks for the password once per device and
decrypts in the browser. One salt per sealing run, so the browser derives one key. No password set: the site stays open.
"""
import base64
import json
import os
import secrets
from pathlib import Path

ITER = 200_000
EXT = ".json.enc"


def _key(password, salt):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(password.encode("utf-8"))


def seal_bytes(data, password, salt=None):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt = salt or secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    ct = AESGCM(_key(password, salt)).encrypt(iv, data, None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return json.dumps(dict(v=1, kdf="pbkdf2-sha256", iter=ITER, salt=b64(salt), iv=b64(iv), ct=b64(ct)))


def unseal_bytes(blob, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    d = json.loads(blob)
    b64 = base64.b64decode
    return AESGCM(_key(password, b64(d["salt"]))).decrypt(b64(d["iv"]), b64(d["ct"]), None)


def seal_dir(site, password):
    """Encrypt every *.json in `site` to *.json.enc and delete the plaintext. Returns the names sealed."""
    site = Path(site)
    salt = secrets.token_bytes(16)
    done = []
    for p in sorted(site.glob("*.json")):
        Path(str(p) + ".enc").write_text(seal_bytes(p.read_bytes(), password, salt))
        p.unlink()
        done.append(p.name)
    return done


def read_json(path, password=None):
    """A site JSON as a dict/list: the plaintext if present, else the sealed copy with the password, else None."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    enc = Path(str(path) + ".enc")
    password = password or os.environ.get("SITE_PASSWORD")
    if enc.exists() and password:
        try:
            return json.loads(unseal_bytes(enc.read_text(), password).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"  {enc.name}: cannot unseal ({type(e).__name__}); treated as missing")
    return None


def cmd_seal(site):
    password = os.environ.get("SITE_PASSWORD", "")
    if not password:
        print("seal: no SITE_PASSWORD set; the site stays open")
        return []
    done = seal_dir(site, password)
    print(f"seal: {len(done)} files sealed ({', '.join(done)})" if done else "seal: nothing to seal")
    return done
