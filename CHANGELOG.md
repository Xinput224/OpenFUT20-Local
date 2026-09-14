# Changelog

## V27 - GitHub clean/public layout

- Removed generated saves, WAL/SHM files, runtime logs, status/session files, caches and old per-experiment release notes from the distributable repository.
- Removed the automatic club-name/coin prompt from `START_LOCAL_FUT.cmd`.
- Replaced the combined club/coin editor with `SET_CLUB_NAME.cmd` and `SET_COINS.cmd`; each changes only its own value.
- Added `.gitignore` and `.gitattributes` for a clean GitHub workflow.
- Rewrote the README around setup, project structure, credits, known crashes and contribution status.
- Reset tracked public defaults to `OpenFUT FC` and `0` coins; local saves are created at runtime and are not shipped.

## V26 - Store refresh + gentle pack/draft balance

- Removed Jasser Pack, OtaGoat Special Pack and Store pack IDs 12-18.
- Added **Jumbo bambo** (200k, 10x 85+), **Xinput Specials** (300k, 5 special players with max 95), and **GET IT IF YOU CAN** (250k, 3 ShapeShifters).
- Icon Player Pick packs now award one 1-of-5 token instead of three.
- Slightly reduced Store promo odds and Draft high-end weighting while keeping the game intentionally generous.

## V25 - Native 1-of-5 Player Pick static definition

- Replaced the incorrect 1-of-3 backing item with FIFA 20's genuine 1-of-5 Player Pick resource `5004094`.
- Added migration for unresolved legacy Player Pick tokens.
- Kept existing resolved picks and selected players untouched.

## 0.2.3 / 0.2.4 - Persistent Player Pick investigation

- Added SQLite-backed Player Pick token/session/candidate state and stable candidate identities.
- Added stale-selection protection and repeated confirmation experiments based on real crash traces.
- Player Pick confirmation remains a known unstable/crashing area in the retail FIFA 20 client.

## 0.2.2 - CSV player database

- Rebuilt the active player/card catalog from `source-data/Fifa 20 Fut Players.csv`.
- Integrated 25,034 CSV rows while preserving compatible known resource IDs and save compatibility holdovers.
- Added player database inspection tooling.

## 0.2.1 - Local club profile tooling

- Added persistent local club name and coin configuration backed by SQLite and JSON defaults.
- Added save backup behavior before profile edits.
- V27 later split the combined editor into two separate root commands.

## 0.2.0 - Parity runtime

- Switched from the incomplete protocol rewrite to the recovered local runtime path used by the working reference package.
- Removed Discord authorization/launch-token gating and the encrypted payload wrapper.
- Added unencrypted `runtime-open/runtime_entries.json` plus inspection output.
- Restored local authentication/session/FUT/redirector functionality, player assets, pack configuration and diagnostics tooling.
