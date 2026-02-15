# Handoff Context (from py-bragerone workspace)

## Goal
Continue Home Assistant integration work for BragerOne in this repository without losing prior decisions made in `py-bragerone`.

## Decisions Already Made
- Start with **pragmatic send-first behavior** for command execution.
- Add strict ACK/correlation logic only if field testing proves it is needed.
- For HA integration, enum handling is **must-have**:
  - user-facing enum labels/options must be mapped to raw value before send,
  - incoming raw values should be mapped back to display labels.

## Command/State Notes
- REST snapshot (prime) is required after startup/reconnect.
- WebSocket delivers deltas; do not assume full initial state from WS.
- Queue depth/status events are not enough for robust per-request command correlation in concurrent cases.

## Behavior Implemented in py-bragerone CLI (reference)
- `--set SYMBOL=VALUE` and `--toggle SYMBOL` send-only mode.
- Write path chooses route:
  - direct parameter write via module command when address exists,
  - raw command via command rules otherwise.
- Numeric write pipeline includes:
  - inverse display transform for send (e.g., display `*0.1` => send `/0.1`),
  - min/max (`n`/`x`) range validation before send.
- TUI gained direct controls (`j/k`, arrows, `t`, `s`) and improved Ctrl+C shutdown handling.

## Priority for HA Repository
1. Implement robust enum serialization/deserialization in HA entities/services.
2. Keep runtime model lightweight; avoid over-engineering ACK layer initially.
3. Add diagnostics logs for command route/value mapping to help field debugging.

## Suggested First Tasks Here
- Add enum conversion utility module (display -> raw and raw -> display).
- Integrate conversion in all write entry points (service calls/select entities/number entities where relevant).
- Add tests for:
  - valid enum write,
  - invalid enum label,
  - round-trip raw<->display conversion,
  - transformed numeric write with bounds checks.

## Working Assumption
This repository is now mounted at `/workspaces/ha-bragerone` from the same devcontainer session.
