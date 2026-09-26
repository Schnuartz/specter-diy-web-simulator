# Specter DIY web simulator

Browser simulator tooling for Specter DIY. It provides the WebAssembly build,
simulated smartcard/SD-card/USB runtime, browser shell, provenance checks,
tests, and the reusable GitHub Actions workflows used by
[`Schnuartz/specter-diy`](https://github.com/Schnuartz/specter-diy).

The simulator is intentionally consumed by the firmware repository at an
immutable commit. The caller supplies the exact Specter source commit and the
simulator commit to the reusable build workflow, so a preview always has
auditable source and tooling provenance.

See [the simulator workflow and release notes](docs/browser-simulator.md) for
the repository contract and migration details.
