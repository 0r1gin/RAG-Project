import getpass

from argon2 import PasswordHasher

password = getpass.getpass("New admin password: ")
if password != getpass.getpass("Repeat password: "):
    raise SystemExit("Passwords do not match")
if len(password) < 12:
    raise SystemExit("Use at least 12 characters")
print(PasswordHasher().hash(password))