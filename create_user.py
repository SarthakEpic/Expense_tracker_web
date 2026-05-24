import hashlib
import os
from getpass import getpass
from pathlib import Path
from secrets import token_urlsafe


ENV_PATH = Path(".env")
PASSWORD_ITERATIONS = 120_000


def hash_password(password):
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def read_env():
    values = {}
    if not ENV_PATH.exists():
        return values

    for line in ENV_PATH.read_text().splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(values):
    lines = [
        f"APP_USERNAME={values['APP_USERNAME']}",
        f"APP_PASSWORD_HASH={values['APP_PASSWORD_HASH']}",
        f"SECRET_KEY={values['SECRET_KEY']}",
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n")


def main():
    values = read_env()
    username = input("Username: ").strip()
    password = getpass("Password: ").strip()

    if not username or not password:
        raise SystemExit("Username and password are required.")

    values["APP_USERNAME"] = username
    values["APP_PASSWORD_HASH"] = hash_password(password)
    values["SECRET_KEY"] = values.get("SECRET_KEY") or token_urlsafe(32)
    write_env(values)
    print(f"Credentials for '{username}' saved to .env")


if __name__ == "__main__":
    main()
