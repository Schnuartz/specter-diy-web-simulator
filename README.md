# Specter DIY web simulator

Browser simulator tooling for Specter DIY. It provides the WebAssembly build,
simulated smartcard/SD-card/USB runtime, browser shell, provenance checks,
tests, and the reusable GitHub Actions workflows used by
[`cryptoadvance/specter-diy`](https://github.com/cryptoadvance/specter-diy).

The simulator is intentionally consumed by the firmware repository at an
immutable commit. The caller supplies the exact Specter source commit and the
simulator commit to the reusable build workflow, so a preview always has
auditable source and tooling provenance.

See [the simulator workflow and release notes](docs/browser-simulator.md) for
the repository contract and migration details.

The official browser build and pull-request previews are published by the
firmware repository at <https://cryptoadvance.github.io/specter-diy/>. To
connect a running simulator to wallet software, use the
[`cryptoadvance/specter-virtual-host`](https://github.com/cryptoadvance/specter-virtual-host)
local bridge and its [latest release](https://github.com/cryptoadvance/specter-virtual-host/releases/latest).
