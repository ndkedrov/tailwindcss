# Hub WASI runtime maintenance package

This fork starts at upstream `v4.3.4`. Its maintenance artifact is
`@tailwindcss/oxide-wasm32-wasi@4.3.4+hub.1`.

The packager verifies the upstream npm tarball SHA-512 and preserves its loaders
and worker entrypoints. It replaces the WASM binary with a source build from
this fork and installs a locked runtime tree:
wasm-runtime 1.2.7, wasm-util 0.10.4, wasi-threads 2.2.0, tslib 2.9.1,
and stable emnapi core/runtime 1.11.3. The bundled core manifest's exact
wasi-threads pin is patched to 2.2.0; this is recorded in the artifact's
`hub-provenance.json`. The core implementation itself remains unchanged.

The upstream binary lacks the WASI reactor `_initialize` export. Its libc
thread-local storage is not initialized, causing module loading to spin in
`pthread_key_delete`. `crates/node/build.rs` resolves the selected Rust sysroot
and requires `crt1-reactor.o` before calling napi-build; a missing CRT now stops
the build. This also handles napi CLI's bare `RUSTC=rustc` command correctly.

Python 3.12+, Node, pnpm 11.9.0, and Rust 1.95.0 with the
`wasm32-wasip1-threads` target are required:

```sh
pnpm install --frozen-lockfile --filter '@tailwindcss/oxide...' --ignore-scripts
pnpm --filter @tailwindcss/oxide build:wasm
python3 hub/build-package.py
```

`runtime-package-lock.json` fixes every runtime package and registry integrity.
To intentionally refresh it, run `python3 hub/build-package.py --refresh-lock`
and review the resulting changes before packing. This maintenance build is
uses the workspace's locked Rust source build. The packager rejects a binary
without `_initialize` and records its SHA-256 in the provenance file.

Run the packed artifact test on Linux (upstream WASI filesystem tests also
require Linux), with both the packed WASI package and native oxide 4.3.4 installed:

```sh
node /absolute/path/to/hub/test-package.cjs /absolute/path/to/installation
```

The test directly imports WASI, scans 256 files, compares worker-thread and
main-thread output, and compares it with the native scanner. A release must
pass this test and the consuming application's frontend/SSR checks. Merely
changing dependency metadata is not evidence of compatibility.

Consumers pin the release asset URL and integrity. Canonical package names and
semver build metadata retain upstream update visibility.
