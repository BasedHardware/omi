"""External sources for the morning brief.

Every source module returns ``(items, SourceHealth)``. The health record is not
optional and not decoration: a source that quietly returns nothing looks exactly
like a quiet day, so each one reports whether it worked as well as what it found.
"""
