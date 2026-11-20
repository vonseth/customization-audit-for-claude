"""Data format version of the audit data and its migrations (standard library only).

Not meant to be run directly; build_overview.py, sample_data.py, import_data.py and update.py load it by file
path (python3 -I has no import path to this folder).

data-meta carries the optional integer "schema_version". A missing value means schema 0 (data written by
versions before 1.4.0). CURRENT is the version this copy of the tools writes. To change the data format later:
raise CURRENT, add a step to MIGRATIONS (key = the version it migrates FROM) and describe it in CHANGELOG.md.

  1  first versioned schema; identical in content to schema 0 (migration only stamps the version)
"""
CURRENT = 1


def version_of(blocks):
    """Schema version of a dict of data blocks (0 when data-meta has none).

    A value that is present but not a valid version (negative, bool, not an integer) is returned unchanged;
    migrate() then refuses it with a clear message.
    """
    meta = blocks.get("meta") if isinstance(blocks, dict) else None
    v = meta.get("schema_version") if isinstance(meta, dict) else None
    return 0 if v is None else v


def _from_0(data):
    return data  # nothing changes in the content; the version stamp is set by migrate()


MIGRATIONS = {0: _from_0}


def migrate(data, from_version):
    """Return the data blocks migrated from from_version to CURRENT (the input dict is not modified)."""
    if not isinstance(from_version, int) or isinstance(from_version, bool) or from_version < 0:
        raise ValueError("data-meta has an invalid schema_version (%r); it must be a whole number of 0 or "
                         "more" % (from_version,))
    if from_version > CURRENT:
        raise ValueError("the data has schema version %d, so it comes from a newer version of "
                         "this project than these tools (they know up to %d); update the tools first" % (from_version, CURRENT))
    out = dict(data)
    for v in range(from_version, CURRENT):
        out = MIGRATIONS[v](out)
    meta = out.get("meta")
    out["meta"] = dict(meta) if isinstance(meta, dict) else {"as_of": None}
    out["meta"]["schema_version"] = CURRENT
    return out
