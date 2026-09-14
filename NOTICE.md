# NOTICE

This package was assembled from user-supplied FIFA 20 Local FUT reference materials.

- `open_runner.py`, package-check/diagnostic helpers, and packaging glue are readable source.
- The local runtime in `runtime-open/runtime_entries.json` is recovered, unencrypted
  Python 3.13 marshal bytecode from the supplied working reference.
- The recovered runtime is included for local interoperability/parity testing; no
  independent open-source license is asserted for that recovered code.
- No Discord authorization, launch token, encrypted secure payload, or remote FUT
  backend is required by this package.
- This package does not bypass EA ownership/DRM. Use a legitimate FIFA 20 copy and
  normal EA App game-launch flow.
