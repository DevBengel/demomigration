"""Explicit, auditable selection of CUCM hunt pilots (no writes)."""
import csv
import fnmatch
import json
import re
from pathlib import Path


def key(item):
    return (str(item.get('pilot', '')).strip(), str(item.get('partition', '')).strip())


def read_selection(path):
    path = Path(path)
    if path.suffix.lower() == '.json':
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(obj, list):
            raise ValueError('JSON selection file must be an array')
        rows = obj
    else:
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
    selected = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Selection entries must be objects')
        pilot = str(row.get('pilot', row.get('huntPilot', ''))).strip()
        if not pilot:
            raise ValueError('Selection entry missing pilot')
        selected.add((pilot, str(row.get('partition', '')).strip()))
    return selected


def select(graph, *, include=(), exclude=(), partitions=(), regex=None, selection_file=None, all_pilots=False):
    """Exact/glob filters are case-insensitive; empty file partition means any partition."""
    patterns = [x.strip() for value in include for x in value.split(',') if x.strip()]
    excluded = [x.strip() for value in exclude for x in value.split(',') if x.strip()]
    pts = [x.strip() for value in partitions for x in value.split(',') if x.strip()]
    file_entries = read_selection(selection_file) if selection_file else None
    has_positive = bool(patterns or pts or regex or file_entries is not None)
    if all_pilots and has_positive:
        raise ValueError('--all cannot be combined with positive selection filters')
    if not has_positive and not all_pilots:
        raise ValueError('No selection: use --pilot, --partition, --match, --select-file or explicit --all; use --list-pilots to inspect')
    rx = re.compile(regex, re.IGNORECASE) if regex else None
    result = []
    for item in graph:
        pilot, partition = key(item)
        if patterns and not any(fnmatch.fnmatchcase(pilot.casefold(), p.casefold()) for p in patterns):
            continue
        if pts and not any(fnmatch.fnmatchcase(partition.casefold(), p.casefold()) for p in pts):
            continue
        if rx and not rx.search(pilot):
            continue
        if file_entries is not None and not any(pilot == p and (not pt or partition == pt) for p, pt in file_entries):
            continue
        if any(fnmatch.fnmatchcase(pilot.casefold(), p.casefold()) for p in excluded):
            continue
        result.append(item)
    return result
