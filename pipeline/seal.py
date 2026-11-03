"""Seal the site's data behind a shared password.

GitHub Pages serves every file to anyone with the link, so each JSON the jobs write is encrypted here (AES-256-GCM, key
from the password by PBKDF2-SHA256) and the plaintext removed; the page asks for the password once per device and
decrypts in the browser. Several passwords: one random data key encrypts the files and is wrapped once per password,
so a person is removed by deleting their line. No password set: the site stays open.
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


def passwords():
    """Every password that opens the site: SITE_PASSWORDS (one per line, 'name: password' or just the password) plus
    SITE_PASSWORD. Returns (label, password) pairs; labels only name the entry in the sealed files."""
    out = []
    for i, line in enumerate(os.environ.get("SITE_PASSWORDS", "").splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label, _, pw = line.partition(":") if ":" in line else (f"key{i + 1}", ":", line)
        if pw.strip():
            out.append((label.strip() or f"key{i + 1}", pw.strip()))
    single = os.environ.get("SITE_PASSWORD", "").strip()
    if single and single not in [pw for _, pw in out]:
        out.append(("main", single))
    return out


def _b64(b):
    return base64.b64encode(b).decode("ascii")


def wrap_keys(data_key, pws):
    """The data key wrapped once per password: a salt and an AES-GCM wrapping of the key under the derived key."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    entries = []
    for label, pw in pws:
        salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
        entries.append(dict(label=label, salt=_b64(salt), iv=_b64(iv), wk=_b64(AESGCM(_key(pw, salt)).encrypt(iv, data_key, None))))
    return entries


def seal_bytes(data, pws, data_key=None, keys=None):
    """One file: AES-256-GCM under a data key, with that key wrapped per password (keys reused across a run)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if isinstance(pws, str):
        pws = [("main", pws)]
    data_key = data_key or secrets.token_bytes(32)
    keys = keys or wrap_keys(data_key, pws)
    iv = secrets.token_bytes(12)
    return json.dumps(dict(v=2, kdf="pbkdf2-sha256", iter=ITER, keys=keys, iv=_b64(iv), ct=_b64(AESGCM(data_key).encrypt(iv, data, None))))


def unseal_bytes(blob, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    d = json.loads(blob)
    b64 = base64.b64decode
    if d.get("v") == 1:
        return AESGCM(_key(password, b64(d["salt"]))).decrypt(b64(d["iv"]), b64(d["ct"]), None)
    for k in d["keys"]:
        try:
            data_key = AESGCM(_key(password, b64(k["salt"]))).decrypt(b64(k["iv"]), b64(k["wk"]), None)
        except Exception:  # noqa: BLE001
            continue
        return AESGCM(data_key).decrypt(b64(d["iv"]), b64(d["ct"]), None)
    raise ValueError("no key entry opens with this password")


def seal_dir(site, pws):
    """Encrypt every *.json in `site` to *.json.enc and delete the plaintext. Returns the names sealed."""
    if isinstance(pws, str):
        pws = [("main", pws)]
    site = Path(site)
    data_key = secrets.token_bytes(32)
    keys = wrap_keys(data_key, pws)
    done = []
    for p in sorted(site.glob("*.json")):
        Path(str(p) + ".enc").write_text(seal_bytes(p.read_bytes(), pws, data_key, keys))
        p.unlink()
        done.append(p.name)
    return done


def read_json(path, password=None):
    """A site JSON as a dict/list: the plaintext if present, else the sealed copy with the password, else None."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    enc = Path(str(path) + ".enc")
    pws = [password] if password else [pw for _, pw in passwords()]
    if enc.exists():
        for pw in pws:
            try:
                return json.loads(unseal_bytes(enc.read_text(), pw).decode("utf-8"))
            except Exception:  # noqa: BLE001
                continue
        print(f"  {enc.name}: no current password opens it; treated as missing")
    return None


def cmd_seal(site):
    pws = passwords()
    if not pws:
        print("seal: no SITE_PASSWORD or SITE_PASSWORDS set; the site stays open")
        return []
    done = seal_dir(site, pws)
    print(f"seal: {len(done)} files sealed for {len(pws)} password{'s' if len(pws) != 1 else ''} ({', '.join(done)})" if done else "seal: nothing to seal")
    return done
