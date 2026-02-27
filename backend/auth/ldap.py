"""LDAP authentication against Active Directory / OpenLDAP."""

import logging

from ldap3 import Connection, Server, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException

from backend.config import settings

logger = logging.getLogger(__name__)


class InvalidCredentialsError(Exception):
    """Raised when LDAP bind or user lookup fails."""
    pass


def authenticate_ldap(username: str, password: str) -> dict[str, str]:
    """
    Authenticate a user against the configured LDAP directory.

    Performs a simple bind with the provided credentials, then searches
    for the user entry to retrieve email.

    Returns:
        dict with keys 'ldap_username' and 'email'.

    Raises:
        InvalidCredentialsError: if bind fails or user is not found.
    """
    server = Server(settings.LDAP_URL, get_info=ALL, connect_timeout=10)

    # Construct the bind DN — supports both AD (user@domain) and OpenLDAP (uid=user,...)
    bind_dn = f"uid={username},{settings.LDAP_BASE_DN}"

    try:
        conn = Connection(
            server,
            user=bind_dn,
            password=password,
            auto_bind=True,
            read_only=True,
            receive_timeout=10,
        )
    except LDAPException as exc:
        logger.warning("LDAP bind failed for user %s: %s", username, exc)
        raise InvalidCredentialsError(f"LDAP authentication failed for user '{username}'") from exc

    # Search for the user entry to get email
    email = ""
    try:
        search_filter = f"(uid={username})"
        conn.search(
            search_base=settings.LDAP_BASE_DN,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["mail", "uid"],
        )
        if conn.entries:
            entry = conn.entries[0]
            email = str(entry.mail) if hasattr(entry, "mail") and entry.mail else ""
        else:
            logger.warning("LDAP user '%s' authenticated but entry not found in search", username)
    except LDAPException as exc:
        logger.warning("LDAP search failed for user %s: %s", username, exc)
    finally:
        conn.unbind()

    return {
        "ldap_username": username,
        "email": email,
    }
