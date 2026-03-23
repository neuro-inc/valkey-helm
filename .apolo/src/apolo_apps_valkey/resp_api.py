"""
RESPApi model

Lightweight representation of a Redis/RESP API endpoint used by the
Valkey app output processor.

Important notes for contributors:
- `ApoloSecret` is a typing-only construct (a TypedDict/Protocol) provided
  by `apolo_app_types`. It is NOT a runtime constructor — do not call
  `ApoloSecret(...)`. Instead provide a plain dict with the expected keys
  (e.g. {"name": "...", "value": "..."}) and, if you want mypy to
  treat it as an `ApoloSecret`, wrap it with `typing.cast(ApoloSecret, ...)`.

This module intentionally contains only a small data model and a helper
property for generating a connection URI string.
"""

from apolo_app_types.protocols.common import AbstractAppFieldType, ApoloSecret


class RESPApi(AbstractAppFieldType):
    """Model for a RESP (Redis-like) API endpoint.

    Attributes:
        scheme: URL scheme (defaults to redis://)
        host: hostname or service name
        port: TCP port number
        base_path: optional path appended to the URI
        user: optional username for credentials
        password: an ApoloSecret (typing-only); see module docstring above
    """

    scheme: str = "redis://"
    host: str
    port: int
    base_path: str = ""
    user: str = ""
    password: ApoloSecret

    @property
    def resp_uri(self) -> str:
        """Build a redis:// style URI including credentials.

        This uses the `user` and `password` fields to produce a textual
        credentials portion. If `password` is a dict-like TypedDict it will
        be formatted into the string representation by Python; ensure caller
        provides a sensible value (e.g. cast(ApoloSecret, {"name":..., "value":...})).
        """
        creds = ""
        if self.user:
            # user provided -> include user:password
            creds = f"{self.user}:{self.password}"
        else:
            # no user -> include only :password
            creds = f":{self.password}"

        return f"{self.scheme}{creds}@{self.host}:{self.port}{self.base_path}"
