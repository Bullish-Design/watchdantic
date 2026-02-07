"""Rule matching: globs, excludes, event type filtering."""

from __future__ import annotations

from fnmatch import fnmatch

from watchdantic.engine.config_models import RuleConfig
from watchdantic.engine.events import FileEvent


def _glob_match(path: str, pattern: str) -> bool:
    """Match a POSIX relative path against a glob pattern.

    Always uses segment-based matching so that * only matches within a
    single path segment (does not cross /). Supports ** for zero-or-more
    directory segments.
    """
    return _match_segments(path.split("/"), pattern.split("/"))


def _match_segments(path_parts: list[str], pat_parts: list[str]) -> bool:
    """Recursively match path segments against pattern segments with ** support."""
    pi = 0  # path index
    pp = 0  # pattern index

    while pp < len(pat_parts):
        if pat_parts[pp] == "**":
            # ** matches zero or more path segments
            # Try matching the rest of the pattern against every suffix of path
            remaining_pattern = pat_parts[pp + 1:]
            if not remaining_pattern:
                # ** at end matches everything remaining
                return True
            for start in range(pi, len(path_parts) + 1):
                if _match_segments(path_parts[start:], remaining_pattern):
                    return True
            return False
        else:
            if pi >= len(path_parts):
                return False
            if not fnmatch(path_parts[pi], pat_parts[pp]):
                return False
            pi += 1
            pp += 1

    return pi == len(path_parts)


def event_matches_rule(event: FileEvent, rule: RuleConfig) -> bool:
    """Check if a single FileEvent matches a rule."""
    # 1. Event type must be in rule.on
    if event.change not in rule.on:
        return False

    # 2. Watch name must match
    if event.watch_name != rule.watch:
        return False

    posix_path = event.path_rel_posix

    # 3. Exclude patterns (OR: any exclude match disqualifies)
    for pattern in rule.exclude:
        if _glob_match(posix_path, pattern):
            return False

    # 4. Match patterns (OR: any match qualifies)
    for pattern in rule.match:
        if _glob_match(posix_path, pattern):
            return True

    return False


def match_events_to_rules(
    events: list[FileEvent],
    rules: list[RuleConfig],
) -> list[tuple[RuleConfig, list[FileEvent]]]:
    """Match a batch of events against all rules.

    Returns a list of (rule, matching_events) tuples for rules that have
    at least one matching event.
    """
    results: list[tuple[RuleConfig, list[FileEvent]]] = []
    for rule in rules:
        matched = [e for e in events if event_matches_rule(e, rule)]
        if matched:
            results.append((rule, matched))
    return results
