"""Timestamp parsing shared by the models and the parser."""

from datetime import datetime

# MEDLINE writes timestamps either with or without a time of day, and carries no
# zone information, so the results are naive by nature.
_FORMATS = ("%Y/%m/%d %H:%M", "%Y/%m/%d")


def parse_pubmed_datetime(value: str) -> datetime | None:
    """Parse a PubMed timestamp.

    Args:
        value: A string such as ``2022/06/02 06:00`` or ``1975/06/01``.

    Returns:
        The parsed value, or ``None`` if it matches neither layout.

    Examples:
        >>> parse_pubmed_datetime("1975/06/01")
        datetime.datetime(1975, 6, 1, 0, 0)
        >>> parse_pubmed_datetime("not a date") is None
        True
    """
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
