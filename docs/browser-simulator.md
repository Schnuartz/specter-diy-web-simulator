# Browser simulator

## Getting Started

The browser simulator freezes and runs the **real Specter DIY Python
application** from `specter-diy/src` inside MicroPython compiled to WebAssembly.
It is not a second implementation of Specter wallet logic. Browser-only
transport shims model the device interfaces; wallet logic remains in Specter
DIY.

Supported development environment: Ubuntu 24.04 or WSL 2 with Ubuntu 24.04.
The required versions used by blocking CI are:

- Emscripten SDK **3.1.74**, bootstrapped from `emscripten-core/emsdk`
  commit `3d6d8ee910466516a53e665b86458faa81dae9ba`.
- Node.js **22.20.0**.
- The Emscripten SDK itself carries its pinned Node.js runtime for compiler
  tools; Node.js 22.20.0 runs the locked JavaScript and Playwright tests.
- Python **3.11.9**.
- Go **1.25.5** for the Virtual Host smoke test.
- Chromium from the Playwright version locked in `web/package-lock.json`.
- Specter DIY's recursive submodules at the selected source commit.

Install the native tools used by the build and bridge:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends build-essential git make pkg-config libffi-dev libgmp-dev libreadline-dev libsdl2-dev libgtk-3-dev libwebkit2gtk-4.1-dev
```

Install the exact Node, Python, and Go versions above using the version
managers supported in your environment. Check them before building:

```sh
node --version
python3 --version
go version
```

### Checkout layout and source selection

Keep the two repositories side by side. Select the exact Specter checkout to
simulate, including a fork checkout when you are building a fork PR:

```text
work/
  specter-diy/                 # source commit to simulate
  specter-diy-web-simulator/   # this repository
```

From this Web Simulator repository root:

```sh
git clone --recursive https://github.com/OWNER/specter-diy.git ../specter-diy
git -C ../specter-diy checkout --detach <FULL_40_CHARACTER_SPECTER_SHA>
git -C ../specter-diy submodule update --init --recursive
git status --short --branch
```

Replace `OWNER` with the repository that owns the source commit and replace
the SHA with the exact commit you intend to simulate. Set the source
repository explicitly so the build manifest records the right fork identity:

```sh
export SPECTER_SRC="$PWD/../specter-diy"
export SPECTER_SOURCE_REPOSITORY="OWNER/specter-diy"
export SIMULATOR_REPOSITORY="cryptoadvance/specter-diy-web-simulator"
export SIMULATOR_COMMIT="$(git rev-parse HEAD)"
```

The browser output is written under
`web/builds/<owner>/<repo>/<source-sha>/`; the current build pointer is
`web/browser/current.json`.

### Install Emscripten and build

From this repository root, check out the pinned Emscripten SDK bootstrap and
build the selected Specter commit:

```sh
mkdir -p .browser-work
git clone https://github.com/emscripten-core/emsdk.git .browser-work/emsdk
git -C .browser-work/emsdk checkout --detach 3d6d8ee910466516a53e665b86458faa81dae9ba
.browser-work/emsdk/emsdk install 3.1.74
.browser-work/emsdk/emsdk activate 3.1.74
source .browser-work/emsdk/emsdk_env.sh
bash web/browser/build-browser.sh
```

The build uses the selected Specter commit's MicroPython/LVGL submodules and
freezes `specter-diy/src`. It applies browser compatibility changes to the
build checkout and emits JavaScript, WebAssembly, preloaded data, and
`build-info.json`. It does not rewrite Specter wallet screens or logic.

### Verify, test, and serve locally

Run the provenance checks and simulator unit tests:

```sh
python3 web/browser/verify_build.py
python3 web/tests/test-resolve-build-target.py
python3 web/tests/test-package-preview.py
python3 web/tests/test-source-project.py
python3 web/tests/test-usb-vcp.py
node web/tests/test-build-provenance.mjs
npm ci --prefix web
npx --prefix web playwright install --with-deps chromium
```

Serve the built simulator from another shell:

```sh
python3 -m http.server 8765 --directory web
```

Open <http://127.0.0.1:8765/>. The exact generated files remain in
`web/builds` and `web/browser/current.json`.

In another shell, run the browser suite and network-policy test against the
served simulator:

```sh
npm ci --prefix web
npx --prefix web playwright install --with-deps chromium
CI=true npm run test:browser --prefix web
node web/tests/test-network-policy.mjs
```

The Playwright suite boots the real WASM application in Chromium. The network
test confirms its worker cannot make an outbound HTTP request.

### Connect Specter Virtual Host

Build or install Specter Virtual Host. CI tests against the immutable
Virtual Host commit **3cf3ecd58a97da0f2cc4b7586ca33abf02f68372**; the SHA is
recorded in [the workflow](../.github/workflows/build-preview.yml). Then start
its local bridge in another shell:

```sh
git clone https://github.com/cryptoadvance/specter-virtual-host.git ../specter-virtual-host
git -C ../specter-virtual-host checkout --detach 3cf3ecd58a97da0f2cc4b7586ca33abf02f68372
cd ../specter-virtual-host
go run -tags webkit2_41 . serve --headless --site http://127.0.0.1:8765
```

Open <http://127.0.0.1:8765/?virtual-host=1>. The simulator connects to the
local bridge at port 8788; Virtual Host exposes the wallet/HWI endpoint at
port 8789. The integration test sends binary USB frames in both directions
and verifies they are unchanged. No remote service is involved.

With both services running, use a third shell from the Web Simulator root:

```sh
node web/tests/test-usb-transport.mjs
```

## CI workflow

A caller in a Specter DIY repository invokes this workflow by a full
40-character commit SHA:

```yaml
uses: cryptoadvance/specter-diy-web-simulator/.github/workflows/build-preview.yml@<FULL_40_CHARACTER_SHA>
```

The reusable workflow reads source repository, PR number, and source SHA from
the caller event. GitHub's `job.workflow_repository` and `job.workflow_sha`
identify the exact Web Simulator repository commit that is running. The
workflow has `contents: read`, no secret inputs, and no publication steps.
It builds in the caller's Actions run; it is not a centralized build service.
A developer needs to fork only `specter-diy`.

The workflow builds JavaScript glue a second time from the caller's base
Specter source and the same pinned simulator tooling. The untrusted PR build
replaces its generated JavaScript with that independently built runtime,
then verifies all generated hashes and provenance before upload. A PR that
adds incompatible C imports may need the trusted runtime updated before the
browser smoke test can pass.

The artifact contract is versioned with `schema_version: 1` and records:

- `source_repository`, `source_sha`, and `pr_number`.
- `web_simulator_repository` and `web_simulator_sha`.
- `workflow_run_id` and `workflow_run_attempt`, so reruns cannot be confused
  with artifacts from an earlier attempt.
- `browser/current.json` and the addressed build files, each with byte count
  and SHA-256 digest.

The trusted publisher is deliberately outside this repository. It runs from
the calling Specter repository's protected default branch, validates artifact
data against the live PR and the immutable workflow pin, and alone publishes
Pages or updates PR comments.

## Pin maintenance

The blocking compatibility test uses Virtual Host commit
`3cf3ecd58a97da0f2cc4b7586ca33abf02f68372`, not a moving branch. To update
it, review a candidate Virtual Host commit and update the `ref` in
`.github/workflows/build-preview.yml`, the pin in this section and README,
and `web/tests/test-workflow-contract.py`. Run the unit, browser, USB, and
network-policy checks before accepting the change.

All action dependencies and the Emscripten bootstrap are pinned to full commit
SHAs. Node, Python, Go, Chromium, and JavaScript packages use explicit versions
or the committed lockfile.

## Safety

The browser build is experimental. Use public test data only. Never enter a
real seed phrase or use real funds. The page runs the PR's firmware logic and
cannot simulate physical hardware security, an air gap, STM32 timing, or the
physical properties of the card and device.
