import getpass

from apexoperator.security.auth import hash_password


if __name__ == "__main__":
    password = getpass.getpass("Bootstrap password (12+ characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    print(hash_password(password))
