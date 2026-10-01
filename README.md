# Specter DIY Web Simulator

Browser-specific MicroPython/WASM build tooling, the browser runtime, and its
smoke tests for the real Specter DIY application. The Web Simulator is not a
second implementation of Specter wallet logic: it freezes and runs the actual
Python application from `specter-diy/src` in a browser MicroPython/WASM runtime.

The reusable workflow runs in the calling `specter-diy` repository's GitHub
Actions context. It builds there with read-only permissions and uploads a
small provenance-bearing artifact. Pages publishing, PR comments, and write
permissions stay in each caller repository.

## Getting Started

See [Getting Started](docs/browser-simulator.md#getting-started) for the
supported environment, exact tool versions, checkout layout, manual build and
test commands, local server URL, and Virtual Host connection.

The browser build is experimental. Never enter a real seed phrase or use real
funds. Use public test data only.

## Reusable workflow

Call
`cryptoadvance/specter-diy-web-simulator/.github/workflows/build-preview.yml`
using a full 40-character commit SHA. The workflow needs no caller inputs: it
gets the source repository, source SHA, and PR number from the caller's GitHub
event, and gets its own repository and commit from GitHub's `job.workflow_*`
context.

The build workflow has only `contents: read`, declares no secrets, and does
not deploy Pages or comment on PRs. Its `browser-preview` artifact contains
only `provenance.json`, `browser/current.json`, and the four files for the
addressed build under `builds/<owner>/<repo>/<source-sha>/`. The provenance
records the source repository/SHA, PR number, Web Simulator repository/SHA,
the GitHub workflow run and attempt, and byte counts and SHA-256 hashes for
every payload file.

The required Virtual Host smoke test checks out
`cryptoadvance/specter-virtual-host` at
`3cf3ecd58a97da0f2cc4b7586ca33abf02f68372`. This revision is pinned because
CI must not test today's moving `main`. Maintainers update the pin by
reviewing a new Virtual Host commit, then updating the full SHA in
`build-preview.yml`, this document, and the workflow contract test.

## Responsibility split

The reusable workflow supplies only the untrusted build and test implementation.
It cannot publish Pages or modify the caller's repository. Each
`specter-diy` repository or fork owns its local caller workflow, protected
publisher, Pages site, `gh-pages` branch, and PR comment. Developers need to
fork only `specter-diy`.
