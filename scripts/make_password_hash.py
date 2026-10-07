import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apexoperator.security.auth import hash_password


if __name__ == "__main__":
    password = getpass.getpass("Bootstrap password (12+ characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    print(hash_password(password))
