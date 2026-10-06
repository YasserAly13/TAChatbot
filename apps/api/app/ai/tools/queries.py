"""The allow-list of queries the model may run against the EXTERNAL database (ADR-0009).

Every entry is a fixed, parameterised, read-only statement. The model chooses a *name* and
supplies *named parameters*; it never writes SQL. This is the primary control — the read-only
engine (``app/db/external.py``) and the owner's SELECT-only login are the layers behind it.

A project registers its queries here (or from its own module at startup)::

    register_query(
        "orders_by_customer",
        sql="SELECT TOP (:limit) order_id, order_date, total FROM dbo.orders "
            "WHERE customer_id = :customer_id ORDER BY order_date DESC",
        params={"customer_id": "int", "limit": "int"},
        description="Most recent orders for one customer (limit ≤ 100).",
        max_rows=100,
    )

Parameter *types* are validated (``int`` | ``float`` | ``str`` | ``bool``) before binding.
The template ships an EMPTY registry — it knows nothing about your data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PARAM_TYPES: dict[str, type] = {"int": int, "float": float, "str": str, "bool": bool}
READ_ONLY_PREFIXES = ("SELECT", "WITH")


class QueryNotAllowed(PermissionError):
    """The requested query name is not in the allow-list."""


class InvalidQueryParams(ValueError):
    """Missing/unknown parameters or a value of the wrong type."""


@dataclass(frozen=True)
class AllowedQuery:
    name: str
    sql: str
    params: dict[str, str] = field(default_factory=dict)
    description: str = ""
    max_rows: int = 100

    def validate_params(self, given: dict[str, object]) -> dict[str, object]:
        """Return a clean parameter dict or raise ``InvalidQueryParams``."""
        unknown = set(given) - set(self.params)
        missing = set(self.params) - set(given)
        if unknown or missing:
            raise InvalidQueryParams(
                f"query {self.name!r}: unknown params {sorted(unknown)}, missing {sorted(missing)}"
            )
        clean: dict[str, object] = {}
        for key, type_name in self.params.items():
            expected = PARAM_TYPES[type_name]
            value = given[key]
            # bool is an int subclass — keep the check strict.
            if isinstance(value, bool) and expected is not bool:
                raise InvalidQueryParams(f"query {self.name!r}: param {key!r} must be {type_name}")
            if not isinstance(value, expected):
                raise InvalidQueryParams(f"query {self.name!r}: param {key!r} must be {type_name}")
            clean[key] = value
        return clean


_REGISTRY: dict[str, AllowedQuery] = {}


def register_query(
    name: str,
    *,
    sql: str,
    params: dict[str, str] | None = None,
    description: str = "",
    max_rows: int = 100,
) -> AllowedQuery:
    """Add a query to the allow-list. Refuses non-SELECT statements and unknown param types."""
    first = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    if first not in READ_ONLY_PREFIXES:
        raise ValueError(f"query {name!r} must start with SELECT/WITH (got {first!r})")
    for key, type_name in (params or {}).items():
        if type_name not in PARAM_TYPES:
            raise ValueError(f"query {name!r}: unsupported param type {type_name!r} for {key!r}")
    query = AllowedQuery(
        name=name, sql=sql, params=dict(params or {}), description=description, max_rows=max_rows
    )
    _REGISTRY[name] = query
    return query


def get_query(name: str) -> AllowedQuery:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise QueryNotAllowed(f"query {name!r} is not in the allow-list") from exc


def list_queries() -> list[AllowedQuery]:
    return list(_REGISTRY.values())


def _reset_for_tests() -> None:
    _REGISTRY.clear()
