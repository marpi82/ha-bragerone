"""Helpers for evaluating BragerOne status command rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def resolve_rule_display_value(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> Any | None:
    """Return the first matched rule value normalized for display.

    Prefers SPA ``paths.value`` / ``raw.value`` if/elseif/else lists (prefix-agnostic
    diodes such as pump status), then cached ``command_rules``.
    """
    mapping = descriptor.get("mapping")
    if not isinstance(mapping, Mapping):
        return None

    paths_display = evaluate_status_value_rules(mapping=mapping, flat_values=flat_values)
    if paths_display is not None:
        return normalize_rule_value(paths_display)

    return _command_rules_display_value(mapping=mapping, flat_values=flat_values, default_actual=default_actual)


def _command_rules_display_value(
    *,
    mapping: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> Any | None:
    """Return the first matched cached ``command_rules`` value, or ``None``."""
    command_rules = mapping.get("command_rules")
    if not isinstance(command_rules, list) or not command_rules:
        return None

    for rule in command_rules:
        if not isinstance(rule, Mapping):
            continue
        if not rule_matches(rule, flat_values=flat_values, default_actual=default_actual):
            continue
        value = rule.get("value")
        if value is None:
            continue
        return normalize_rule_value(value)
    return None


def mapping_has_status_value_rules(mapping: Mapping[str, Any] | None) -> bool:
    """Return True when *mapping* carries SPA if/elseif/else value rules."""
    return _status_value_rule_list(mapping) is not None


def mapping_has_status_label_rules(mapping: Mapping[str, Any] | None) -> bool:
    """Return True for diode-style rule lists that yield status labels.

    Schedule / password composites also use if/elseif/else, but their ``then`` /
    ``else`` branches are address-selector lists (``P12.a``…), not ON/OFF labels.
    Those must not count as a bootstrap display value — they are not HA entities yet.
    """
    rules = _status_value_rule_list(mapping)
    if rules is None:
        return False
    saw_label = False
    for rule in rules:
        # ``_status_value_rule_list`` already keeps Mapping entries only.
        for key in ("then", "else"):
            if key not in rule:
                continue
            value = _unwrap_rule_result(rule.get(key))
            if isinstance(value, list):
                return False
            if (isinstance(value, str) and value.strip()) or isinstance(value, (int, float, bool)):
                saw_label = True
    return saw_label


def _unwrap_rule_result(value: Any) -> Any:
    """Unwrap ``{value: ...}`` rule payloads used by some SPA compilers."""
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


def status_value_rules_fingerprint(mapping: Mapping[str, Any] | None) -> str | None:
    """Stable fingerprint of the SPA rule list used for evaluation / address dedupe.

    Dictionary keys are sorted so equivalent rule trees fingerprint identically
    regardless of insertion order; list order is preserved.
    """
    rules = _status_value_rule_list(mapping)
    if rules is None:
        return None
    return repr(_canonicalize_for_fingerprint(rules))


def _canonicalize_for_fingerprint(value: Any) -> Any:
    """Return a deep copy with mapping keys sorted for stable ``repr`` fingerprints."""
    if isinstance(value, Mapping):
        return {key: _canonicalize_for_fingerprint(value[key]) for key in sorted(value.keys(), key=str)}
    if isinstance(value, list):
        return [_canonicalize_for_fingerprint(item) for item in value]
    return value


def status_rule_selector_addresses(mapping: Mapping[str, Any] | None) -> set[str]:
    """Return register addresses referenced by SPA if/elseif selectors in status rules.

    Used as entity refresh dependencies so non-primary condition registers still
    wake STATUS_* entities when their value changes.
    """
    rules = _status_value_rule_list(mapping)
    if rules is None:
        return set()
    return _addresses_from_status_rules(rules)


def evaluate_status_value_rules(
    *,
    mapping: Mapping[str, Any],
    flat_values: Mapping[str, Any],
) -> Any | None:
    """Evaluate SPA ``if``/``elseif``/``else`` lists from ``paths.value`` / ``raw.value``.

    Prefers ``pybragerone.ComputedValueEvaluator`` (library boundary). Falls back to a
    local equalTo/notEqualTo evaluator only when the library evaluator is unavailable
    (offline stubs / older pins).
    """
    rules = _status_value_rule_list(mapping)
    if rules is None:
        return None
    library_value = _evaluate_rules_via_library(rules, flat_values=flat_values)
    if library_value is not None or _library_evaluator_available():
        return library_value
    return _eval_spa_value_rules(rules, flat_values=flat_values)


def _library_evaluator_available() -> bool:
    """Return True when the pinned library exposes a usable ComputedValueEvaluator."""
    try:
        from pybragerone.models.param import ParamStore
        from pybragerone.models.param_resolver import ComputedValueEvaluator
    except ImportError:
        return False
    return callable(getattr(ParamStore, "upsert", None)) and callable(getattr(ComputedValueEvaluator, "evaluate", None))


def _evaluate_rules_via_library(rules: list[Any], *, flat_values: Mapping[str, Any]) -> Any | None:
    """Run SPA rule lists through ``ComputedValueEvaluator`` when available."""
    if not _library_evaluator_available():
        return None
    from pybragerone.models.param import ParamStore
    from pybragerone.models.param_resolver import ComputedValueEvaluator

    store = ParamStore()
    # Seed only registers referenced by rule selectors — full flatten upserts
    # deep-copy family snapshots on every STATUS_* WebSocket tick.
    for key in _addresses_from_status_rules(rules):
        if key in flat_values:
            store.upsert(key, flat_values[key])
    return ComputedValueEvaluator(store).evaluate({"value": list(rules)})


def _status_value_rule_list(mapping: Mapping[str, Any] | None) -> list[Any] | None:
    if not isinstance(mapping, Mapping):
        return None
    candidates: list[Any] = []
    paths = mapping.get("paths")
    if isinstance(paths, Mapping):
        candidates.append(paths.get("value"))
    raw = mapping.get("raw")
    if isinstance(raw, Mapping):
        candidates.append(raw.get("value"))
        candidates.append(raw.get("any"))
    for entries in candidates:
        if _looks_like_status_rule_list(entries):
            return [entry for entry in entries if isinstance(entry, Mapping)]
    return None


def _looks_like_status_rule_list(entries: Any) -> bool:
    if not isinstance(entries, list) or not entries:
        return False
    return any(isinstance(entry, Mapping) and any(key in entry for key in ("if", "elseif", "then", "else")) for entry in entries)


def _addresses_from_status_rules(rules: list[Any]) -> set[str]:
    """Collect ``P<n>.<chan><idx>`` addresses from rule conditions and payloads.

    Includes if/elseif selectors plus ``then``/``else`` address lists so entities
    that bind a conditional value register (e.g. ``ZADANA_TEMP_CO*_WRITE``) refresh
    when either the gate bit or the active setpoint word changes.
    """
    out: set[str] = set()
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        for key in ("if", "elseif"):
            conds = rule.get(key)
            if not isinstance(conds, list):
                continue
            for cond in conds:
                if not isinstance(cond, Mapping):
                    continue
                values = cond.get("value")
                if not isinstance(values, list):
                    continue
                for sel in values:
                    if not isinstance(sel, Mapping):
                        continue
                    address = _address_from_spa_selector(sel)
                    if address is not None:
                        out.add(address)
        for payload_key in ("then", "else"):
            if payload_key not in rule:
                continue
            out.update(_addresses_from_rule_payload(rule.get(payload_key)))
    return out


def _addresses_from_rule_payload(payload: Any) -> set[str]:
    """Collect addresses from a ``then``/``else`` label or address-selector payload."""
    out: set[str] = set()
    if isinstance(payload, Mapping):
        if "value" in payload:
            out.update(_addresses_from_rule_payload(payload.get("value")))
            return out
        address = _address_from_spa_selector(payload)
        if address is not None:
            out.add(address)
        return out
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, Mapping):
                out.update(_addresses_from_rule_payload(entry))
    return out


def select_raw_any_branch(
    any_rules: Any,
    *,
    flat_values: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Return the active ``raw.any`` then/else payload mapping, if any.

    Mirrors library ``ParamResolver._select_raw_any_branch`` with the local SPA
    condition matcher so HA stays usable against stubs / older pins.
    """
    if not isinstance(any_rules, list):
        return None
    explicit_else: Mapping[str, Any] | None = None
    for rule in any_rules:
        if not isinstance(rule, Mapping):
            continue
        conds = rule.get("if")
        if conds is None:
            conds = rule.get("elseif")
        if (
            isinstance(conds, list)
            and conds
            and all(isinstance(c, Mapping) and _spa_condition_matches(c, flat_values=flat_values) for c in conds)
        ):
            then_val = rule.get("then")
            return then_val if isinstance(then_val, Mapping) else None
        if explicit_else is None:
            else_val = rule.get("else")
            if isinstance(else_val, Mapping):
                explicit_else = else_val
    return explicit_else


def first_selector_address_value(
    payload: Mapping[str, Any] | None,
    *,
    flat_values: Mapping[str, Any],
) -> Any | None:
    """Read the first address-selector entry under ``payload['value']`` from *flat_values*."""
    if not isinstance(payload, Mapping):
        return None
    value_payload = payload.get("value")
    if not isinstance(value_payload, list):
        return None
    for entry in value_payload:
        if not isinstance(entry, Mapping):
            continue
        address = _address_from_spa_selector(entry)
        if address is None:
            continue
        if address in flat_values and flat_values.get(address) is not None:
            return flat_values.get(address)
    return None


def _address_from_spa_selector(entry: Mapping[str, Any]) -> str | None:
    """Build ``P<n>.<chan><idx>`` from an SPA ``{group, number, use}`` selector."""
    group = entry.get("group")
    number = entry.get("number")
    use = entry.get("use")
    if not isinstance(group, str) or not group.strip():
        return None
    if not isinstance(number, int):
        return None
    if not isinstance(use, str) or not use.strip():
        return None
    return f"{group.strip()}.{use.strip()[0]}{number}"


def _eval_spa_value_rules(rules: list[Any], *, flat_values: Mapping[str, Any]) -> Any | None:
    else_value: Any = None
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        conds = rule.get("if")
        if conds is None:
            conds = rule.get("elseif")
        # Unmatched if/elseif may still carry an inline ``else`` (library parity).
        if (
            isinstance(conds, list)
            and conds
            and all(isinstance(c, Mapping) and _spa_condition_matches(c, flat_values=flat_values) for c in conds)
        ):
            then = rule.get("then")
            if isinstance(then, Mapping):
                return then.get("value")
            return then
        if else_value is None and "else" in rule:
            else_value = rule.get("else")
    if isinstance(else_value, Mapping):
        return else_value.get("value")
    return else_value


def _coerce_spa_expected(expected: Any) -> Any:
    """Normalize SPA ``void 0`` / empty expected tokens to ``None``."""
    if isinstance(expected, str) and expected.strip() in {"void 0", "undefined"}:
        return None
    return expected


def _spa_condition_matches(cond: Mapping[str, Any], *, flat_values: Mapping[str, Any]) -> bool:
    operation = cond.get("operation")
    expected = _coerce_spa_expected(cond.get("expected"))
    if not isinstance(operation, str):
        return False
    values = cond.get("value")
    if not isinstance(values, list) or not values:
        return False
    for sel in values:
        if not isinstance(sel, Mapping):
            continue
        group = sel.get("group")
        number = sel.get("number")
        use = sel.get("use")
        if not isinstance(group, str) or not isinstance(number, int) or not isinstance(use, str) or not use:
            continue
        address = f"{group}.{use[0]}{number}"
        # Absent register: only null/undefined equality can match (pump-diode guard).
        if address not in flat_values:
            op = operation.strip()
            if "." in op:
                op = op.rsplit(".", 1)[-1]
            if op == "equalTo" and expected is None:
                return True
            continue
        actual = read_target_actual(
            {"address": address, "bit": sel.get("bit"), "mask": sel.get("mask")},
            flat_values=flat_values,
        )
        if compare_condition(operation=operation, actual=actual, expected=expected):
            return True
    return False


def resolve_rule_bool(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> bool | None:
    """Resolve rule output to boolean for binary-state entities."""
    mapping = descriptor.get("mapping")
    if isinstance(mapping, Mapping) and mapping_has_status_value_rules(mapping):
        # Multi-state SPA footers (e.g. STATUS_BAR_COMPRESSOR) emit mode labels
        # such as COMPRESSOR_STATE_HEATING before ON_SHORT/OFF_SHORT — for binary
        # entities skip non-bool labels and keep walking.
        return evaluate_status_binary_from_rules(mapping=mapping, flat_values=flat_values)
    display = resolve_rule_display_value(descriptor=descriptor, flat_values=flat_values, default_actual=default_actual)
    return status_label_to_bool(display)


def status_binary_has_sync_path(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> bool:
    """Return whether a status binary can resolve without ``ParamResolver``."""
    return (
        try_resolve_status_binary_sync(
            descriptor=descriptor,
            flat_values=flat_values,
            default_actual=default_actual,
        )
        is not None
    )


def try_resolve_status_binary_sync(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> bool | None:
    """Return on/off when a sync path works, else ``None`` (use ``ParamResolver``).

    Evaluates SPA value rules at most once per call so STATUS_* WebSocket refreshes
    do not rebuild the library store twice for the same tick.
    """
    mapping_raw = descriptor.get("mapping")
    mapping: Mapping[str, Any] | None = mapping_raw if isinstance(mapping_raw, Mapping) else None
    if mapping is not None and mapping_has_status_value_rules(mapping):
        # Claim a sync path only for on/off labels. Mode-only ``then`` tokens
        # (COMPRESSOR_STATE_*) are skipped so later ON_SHORT/OFF_SHORT branches
        # can win; explicit ``then: null`` and fully unmatched rules return None
        # (defer to async resolver — do not fall through to raw coercion).
        return evaluate_status_binary_from_rules(mapping=mapping, flat_values=flat_values)
    rule_value = resolve_rule_bool(descriptor=descriptor, flat_values=flat_values, default_actual=default_actual)
    if rule_value is not None:
        return rule_value
    if mapping is None:
        return None
    inputs = mapping.get("inputs")
    if not isinstance(inputs, list):
        return None
    bit_inputs = [
        entry
        for entry in inputs
        if isinstance(entry, Mapping) and (isinstance(entry.get("bit"), int) or isinstance(entry.get("mask"), int))
    ]
    preferred = _preferred_bit_input(bit_inputs)
    if preferred is None:
        return None
    actual = read_target_actual(preferred, flat_values=flat_values)
    if isinstance(actual, int | float) and not isinstance(actual, bool):
        return bool(int(actual))
    # Preferred bit/mask input exists — same sync eligibility as resolve_entity_bool.
    return coerce_status_bool(default_actual)


def evaluate_status_binary_from_rules(
    *,
    mapping: Mapping[str, Any],
    flat_values: Mapping[str, Any],
) -> bool | None:
    """Walk SPA status value rules for on/off, skipping non-bool mode labels.

    Display evaluation keeps first-match semantics (``COMPRESSOR_STATE_HEATING``
    wins for sensors). Binary diodes need the physical ON/OFF bit that often sits
    *after* those mode branches — continue until a bool-mappable label appears.
    Explicit ``then: null`` still means undefined (stop).
    """
    rules = _status_value_rule_list(mapping)
    if rules is None:
        return None

    else_payload: Any = None
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        conds = rule.get("if")
        if conds is None:
            conds = rule.get("elseif")
        if (
            isinstance(conds, list)
            and conds
            and all(isinstance(c, Mapping) and _spa_condition_matches(c, flat_values=flat_values) for c in conds)
        ):
            if "then" in rule and rule.get("then") is None:
                return None
            resolved = _status_payload_to_bool(rule.get("then"))
            if resolved is not None:
                return resolved
            continue
        if else_payload is None and "else" in rule:
            else_payload = rule.get("else")

    if else_payload is None:
        return None
    return _status_payload_to_bool(else_payload)


def _status_payload_to_bool(payload: Any) -> bool | None:
    """Map a rule ``then``/``else`` payload to on/off when the label is binary."""
    if isinstance(payload, Mapping):
        if "value" in payload:
            return _status_payload_to_bool(payload.get("value"))
        return None
    return status_label_to_bool(payload)


def status_label_to_bool(value: Any) -> bool | None:
    """Map a STATUS display label/token to on/off, or None when unknown.

    Accepts SPA enum tags (``e.ON_MANUAL``), English diode tokens (``On Manual``),
    and translated labels including parenthetical manual notes
    (``Włączone (ręcznie)`` / ``Wyłączony (ręcznie)``).
    """
    if not isinstance(value, str):
        return None
    norm = _normalize_status_label_token(value)
    if not norm:
        return None
    if norm in _BOOL_TRUE_TOKENS:
        return True
    if norm in _BOOL_FALSE_TOKENS:
        return False
    # Prefix fallback covers ON_MANUAL / OFF_MANUAL after underscore→space.
    if norm.startswith("on"):
        return True
    if norm.startswith("off"):
        return False
    return None


def _normalize_status_label_token(value: str) -> str:
    """Normalize STATUS labels/tokens for boolean mapping."""
    norm = value.strip().casefold()
    if not norm:
        return ""
    # Drop manual/context notes: "wyłączony (ręcznie)" → "wyłączony".
    if "(" in norm:
        norm = norm.split("(", 1)[0].rstrip()
    # Strip enum/path prefixes: "e.on_manual", "diodestate['off']" leftovers.
    if "." in norm:
        norm = norm.rsplit(".", 1)[-1]
    if "'" in norm:
        # DiodeState['OFF'] → off
        parts = [part for part in norm.replace("]", "").split("'") if part and part not in {"[", " "}]
        if parts:
            norm = parts[-1]
    return norm.replace("_", " ").strip()


def resolve_entity_bool(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> bool:
    """Resolve on/off for switches and binary sensors.

    Prefer command-rule labels, then bit/mask inputs from the mapping (when several
    bits share one address, use the lowest bit — e.g. PumpState ON/OFF on bit 1
    before manual bit 3), and finally a conservative raw coercion that refuses
    multi-bit status words.
    """
    rule_value = resolve_rule_bool(descriptor=descriptor, flat_values=flat_values, default_actual=default_actual)
    if rule_value is not None:
        return rule_value

    mapping = descriptor.get("mapping")
    if isinstance(mapping, Mapping):
        inputs = mapping.get("inputs")
        if isinstance(inputs, list):
            bit_inputs = [
                entry
                for entry in inputs
                if isinstance(entry, Mapping) and (isinstance(entry.get("bit"), int) or isinstance(entry.get("mask"), int))
            ]
            preferred = _preferred_bit_input(bit_inputs)
            if preferred is not None:
                actual = read_target_actual(preferred, flat_values=flat_values)
                if isinstance(actual, int | float) and not isinstance(actual, bool):
                    return bool(int(actual))

    return coerce_status_bool(default_actual)


def _preferred_bit_input(bit_inputs: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Pick the best bit/mask input when command rules did not resolve."""
    if not bit_inputs:
        return None
    if len(bit_inputs) == 1:
        return bit_inputs[0]

    addresses = {str(entry.get("address") or "") for entry in bit_inputs}
    if len(addresses) != 1:
        return None

    numbered = [entry for entry in bit_inputs if isinstance(entry.get("bit"), int)]
    if not numbered:
        return None
    return min(numbered, key=lambda entry: int(entry["bit"]))


_BOOL_TRUE_TOKENS = frozenset(
    {
        "on",
        "on manual",
        "enabled",
        "true",
        "yes",
        "1",
        "tak",
        "włączony",
        "wlaczony",
        "włączone",
        "wlaczone",
        "włączono",
        "wlaczono",
        "załączony",
        "zalaczony",
        "załączone",
        "zalaczone",
        "załączono",
        "zalaczono",
    }
)
_BOOL_FALSE_TOKENS = frozenset(
    {
        "off",
        "off manual",
        "disabled",
        "false",
        "no",
        "0",
        "nie",
        "wyłączony",
        "wylaczony",
        "wyłączone",
        "wylaczone",
        "wyłączono",
        "wylaczono",
    }
)


def rule_matches(rule: Mapping[str, Any], *, flat_values: Mapping[str, Any], default_actual: Any) -> bool:
    """Check whether all/any rule conditions match current values."""
    conditions = rule.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        return True

    condition_results: list[bool] = []
    for cond in conditions:
        if not isinstance(cond, Mapping):
            return False
        condition_results.append(_condition_matches(cond, flat_values=flat_values, default_actual=default_actual))

    logic = str(rule.get("logic") or "").strip().casefold()
    if logic == "any":
        return any(condition_results)
    return all(condition_results)


def _condition_matches(cond: Mapping[str, Any], *, flat_values: Mapping[str, Any], default_actual: Any) -> bool:
    operation = cond.get("operation")
    expected = cond.get("expected")
    targets = cond.get("targets")
    if not isinstance(operation, str):
        return False
    if not isinstance(targets, list) or not targets:
        return compare_condition(operation=operation, actual=default_actual, expected=expected)
    for target in targets:
        if not isinstance(target, Mapping):
            return False
        actual = read_target_actual(target, flat_values=flat_values)
        if not compare_condition(operation=operation, actual=actual, expected=expected):
            return False
    return True


def _as_bitmask_int(value: Any) -> int | None:
    """Coerce JSON numbers (including floats like ``64.0``) to ints for bit ops."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def read_target_actual(target: Mapping[str, Any], *, flat_values: Mapping[str, Any]) -> Any:
    """Read target value from flat payload, optionally applying bit/mask."""
    address = target.get("address")
    if not isinstance(address, str) or not address.strip():
        return None
    value = flat_values.get(address.strip())
    bitmask_value = _as_bitmask_int(value)
    if bitmask_value is None:
        return value
    bit = target.get("bit")
    if isinstance(bit, int):
        return (bitmask_value >> bit) & 1
    mask = target.get("mask")
    if isinstance(mask, int):
        return bitmask_value & mask
    return bitmask_value


def coerce_status_bool(value: Any) -> bool:
    """Coerce obvious on/off tokens; refuse multi-bit status words without a rule."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        as_int = int(value)
        if as_int in (0, 1):
            return bool(as_int)
        return False
    if isinstance(value, str):
        norm = value.strip().casefold()
        if norm in _BOOL_TRUE_TOKENS:
            return True
        if norm in _BOOL_FALSE_TOKENS:
            return False
    return False


def compare_condition(*, operation: str, actual: Any, expected: Any) -> bool:
    """Evaluate one rule operation against actual and expected values."""
    op = operation.strip()
    if "." in op:
        op = op.rsplit(".", 1)[-1]
    if op == "equalTo":
        return bool(actual == expected)
    if op == "notEqualTo":
        return bool(actual != expected)
    return False


def normalize_rule_value(value: Any) -> Any:
    """Normalize token-like rule values to user-friendly text."""
    if isinstance(value, str):
        token = value.strip()
        if "." in token:
            token = token.rsplit(".", 1)[-1]
        norm = token.casefold()
        if norm.startswith("on"):
            return "On"
        if norm.startswith("off"):
            return "Off"
        return token.replace("_", " ").title()
    return value
