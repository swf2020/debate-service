"""Provision an administrator from the service host with access to the SQLite database."""

import argparse
import asyncio
from getpass import getpass

from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    if not 2 <= len(args.username) <= 50:
        parser.error("Username must have 2–50 characters")

    password = getpass("Password: ")
    if len(password) < 12 or len(password.encode("utf-8")) > 72:
        parser.error("Password must have at least 12 characters and at most 72 UTF-8 bytes")
    if password != getpass("Confirm password: "):
        parser.error("Passwords differ")

    load_dotenv()
    from auth import hash_password
    from db import init_db, provision_admin

    async def provision() -> None:
        await init_db()
        await provision_admin(args.username, hash_password(password))

    try:
        asyncio.run(provision())
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
