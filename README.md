# OpenFUT20 Local

OpenFUT20 Local is an experimental community project that runs a **local FIFA 20 Ultimate Team environment** on your own PC. It provides a local FUT server path, a persistent local club/save, custom packs and Draft tuning, and tooling for testing older FIFA 20 FUT flows without depending on a live FUT backend.

> **Important:** this build is experimental. It has bugs, incomplete behavior, and known FIFA 20 crashes. It is being published openly so people can inspect it, test it, improve it, document it, and help fix what is still broken.

## Current status

The project can launch the local FUT stack and includes local implementations or compatibility paths for authentication/session flow, club data, squads, items, packs, the Store, transfer-market behavior, SBC/Draft-related surfaces, and persistent SQLite state.

The current Store/Draft build also includes the V26 balance changes and custom packs. Native Player Pick confirmation remains a known unstable area and **can still crash FIFA 20 after a selection**. Other bugs are expected. Do not treat this as a finished emulator or production-quality server.

## What this project does

OpenFUT20 starts local services for the FIFA 20 FUT/Blaze/redirector paths and redirects the required FUT hostnames to `127.0.0.1`. FIFA 20 still uses your normal legitimate game installation and EA App launch/ownership flow; the FUT service traffic handled by this project stays local.

Local progress is stored in `runtime/data/localfut20.sqlite3` after the first run. Runtime logs, crash reports and backups are generated locally and are intentionally ignored by Git.

## Quick start

Requirements:

- Windows x64
- A legitimate FIFA 20 installation
- EA App for the normal game launch/ownership step
- Python **3.13 x64**
- Administrator permission for the hosts-file redirect and the in-memory trust bridge

Setup:

1. Clone or extract this repository into its own folder.
2. Run `INSTALL_DEPENDENCIES.cmd`.
3. Optional but recommended: run `SET_CLUB_NAME.cmd`.
4. Optional: run `SET_COINS.cmd` and choose the starting/local balance you want.
5. Run `CHECK_LOCAL_FUT.cmd`.
6. If FIFA 20 is installed in a non-standard location, edit `launcher-settings.json` and set `fifa_exe`.
7. Run `START_LOCAL_FUT.cmd`.
8. When finished, run `STOP_LOCAL_FUT.cmd`.

There is **no club-name or coin prompt inside the server startup anymore**. Club name and coins are deliberately separate tools in the project root.

## Club name and coins

`SET_CLUB_NAME.cmd` changes only the club name/abbreviation.

`SET_COINS.cmd` changes only the coin balance. You can enter an exact value such as `2500000`, or use `+500000` / `-100000` when an existing save is present.

When a save already exists, both tools create a dated SQLite backup under `runtime/backups/` before changing that value. They do not intentionally rebuild your club, squads, players or items.

`SHOW_MY_CLUB.cmd` displays the currently persisted local club name, coin balance and save path.

## Useful commands

- `START_LOCAL_FUT.cmd` — start the local services and launch path
- `STOP_LOCAL_FUT.cmd` — stop local services and clean the FUT hosts redirects
- `SET_CLUB_NAME.cmd` — edit only the club name
- `SET_COINS.cmd` — edit only the coin balance
- `SHOW_MY_CLUB.cmd` — show the current local profile
- `CHECK_LOCAL_FUT.cmd` — verify the package/runtime
- `COLLECT_DIAGNOSTICS.cmd` — collect diagnostics after a failure
- `SHOW_PLAYER_DATABASE.cmd` — show player-database information

## Repository layout

- `localfut20/` — active local FUT configuration, player/manager data and bundled FUT assets
- `runtime-open/` — recovered unencrypted runtime entries plus disassembly/inspection material
- `runtime-source/` — certificates and low-level runtime compatibility material
- `runtime/mined/` — native FIFA 20 tables used by the local runtime
- `runtime/content-cache/` — bundled content required by current card/head fallbacks
- `source-data/` — source player/card datasets used by the active catalog
- `tools/` — package checks, profile editing and diagnostics helpers
- `tests/` — local lifecycle/regression tests
- `logs/crash-reports/` — generated crash reports; contents are not committed

The `.txt` files under `runtime-open/disassembly/` and `runtime-open/strings/` are intentionally kept: they are inspection material for the recovered runtime, not old release notes.

## Known issues and crashes

This project is open partly because it is **not finished**. Current known limitations include:

- Native Player Pick confirmation can crash FIFA 20 after the chosen player is committed.
- Some protocol/UI behavior is based on compatibility work and may differ from the original live FUT service.
- Custom Store packs, pack weights and Draft weights are community-tuned rather than authentic live-service values.
- Edge cases in inventory, duplicate handling, transfers, SBCs, Draft and other FUT modes may still be incomplete.
- FIFA 20 may expose additional client assumptions that are not yet reproduced by the local runtime.

If you hit a crash, keep the newest report from `logs/crash-reports/` or run `COLLECT_DIAGNOSTICS.cmd` after the failure. When opening a GitHub issue, include the exact steps that caused the problem and the relevant diagnostics, but remove any information you do not want to publish.

## Credits

Thanks to **Kyro** for helping during the stream, testing the project, and helping move the build forward.

Thanks as well to everyone who tests, documents bugs, studies the FIFA 20 behavior, contributes fixes, and keeps old games alive through community work.

## Source and licensing note

The readable wrapper/helper code created for this project is distributed under the MIT terms in `LICENSE`.

The recovered runtime in `runtime-open/runtime_entries.json`, its disassembly, FIFA/EA assets, extracted/native data, and other third-party material are **not automatically covered by that MIT grant**. See `NOTICE.md`. This repository does not claim ownership of EA/FIFA intellectual property and is not affiliated with or endorsed by Electronic Arts.

The project does not remove the requirement to own/launch a legitimate FIFA 20 copy through the normal game client.

## Contributing

GitHub is the home for this work. Bug reports, reproducible crash traces, documentation improvements, cleanup, reverse-engineering notes and code fixes are welcome. Keep changes understandable, keep generated saves/logs out of commits, and document behavior changes in `CHANGELOG.md`.

THE OPEN SOURCE IS FOR EVERYONE
