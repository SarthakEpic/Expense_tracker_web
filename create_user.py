from getpass import getpass
from pathlib import Path
from secrets import token_urlsafe


ENV_PATH = Path(".env")
REQUIRED_KEYS = ("APP_USERNAME", "APP_PASSWORD", "SECRET_KEY")


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
    ENV_PATH.write_text(
        "\n".join(f"{key}={values[key]}" for key in REQUIRED_KEYS) + "\n"
    )


def main():
    values = read_env()
    username = input("Username: ").strip()
    password = getpass("Password: ").strip()

    if not username or not password:
        raise SystemExit("Username and password are required.")

    values["APP_USERNAME"] = username
    values["APP_PASSWORD"] = password
    values["SECRET_KEY"] = values.get("SECRET_KEY") or token_urlsafe(32)
    write_env(values)
    print(f"Credentials for '{username}' saved to .env")


if __name__ == "__main__":
    main()
