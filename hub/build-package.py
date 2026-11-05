#!/usr/bin/env python3
"""Package the rebuilt WASI reactor with the tested, locked Hub JS runtime."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
URL = 'https://registry.npmjs.org/@tailwindcss/oxide-wasm32-wasi/-/oxide-wasm32-wasi-4.3.4.tgz'
INTEGRITY = 'bjO9WmoM687p8AoCIyw1DUqzpAs4JICLvNmIPxIWDmhw8IOsdubtWQLShyJmISnDKtRy1BBApHVOUl6sNFQQJA=='
OUTPUT = ROOT / 'dist'

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')

def main():
    data = urllib.request.urlopen(URL).read()
    assert base64.b64encode(hashlib.sha512(data).digest()).decode() == INTEGRITY, 'upstream integrity mismatch'
    OUTPUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hub-tailwind-') as temporary:
        stage = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            archive.extractall(stage, filter='data')
        package = stage / 'package'
        wasm = ROOT.parent / 'crates/node/npm/wasm32-wasi/tailwindcss-oxide.wasm32-wasi.wasm'
        if '--refresh-lock' not in sys.argv:
            if not wasm.is_file():
                raise SystemExit('PRECONDITION: run pnpm --filter @tailwindcss/oxide build:wasm first')
            subprocess.run(['node', '-e', 'const fs=require("node:fs"); const m=new WebAssembly.Module(fs.readFileSync(process.argv[1])); if(!WebAssembly.Module.exports(m).some(e=>e.name==="_initialize")) throw Error("WASI reactor _initialize is required")', str(wasm)], check=True)
            shutil.copyfile(wasm, package / wasm.name)
        shutil.rmtree(package / 'node_modules')
        manifest = json.loads((package / 'package.json').read_text())
        manifest['version'] = '4.3.4+hub.1'
        manifest['dependencies'] = {
            '@napi-rs/wasm-runtime': '1.2.7', '@emnapi/core': '1.11.3',
            '@emnapi/runtime': '1.11.3', '@tybys/wasm-util': '0.10.4',
            '@emnapi/wasi-threads': '2.2.0', 'tslib': '2.9.1',
        }
        # npm overrides are only honored at the root. The bundled core manifest
        # is patched below as well so consumers receive a valid dependency tree.
        manifest['overrides'] = {'@emnapi/wasi-threads': '2.2.0'}
        manifest['repository'] = {'type': 'git', 'url': 'git+https://github.com/ndkedrov/tailwindcss.git', 'directory': 'crates/node/npm/wasm32-wasi'}
        write_json(package / 'package.json', manifest)
        lock = ROOT / 'runtime-package-lock.json'
        if '--refresh-lock' in sys.argv:
            subprocess.run(['npm', 'install', '--package-lock-only', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=package, check=True)
            shutil.copyfile(package / 'package-lock.json', lock)
            return
        if not lock.exists():
            raise SystemExit('PRECONDITION: generate and review hub/runtime-package-lock.json first')
        shutil.copyfile(lock, package / 'package-lock.json')
        subprocess.run(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=package, check=True)
        core_path = package / 'node_modules/@emnapi/core/package.json'
        core = json.loads(core_path.read_text())
        assert core['dependencies']['@emnapi/wasi-threads'] == '1.2.3'
        core['dependencies']['@emnapi/wasi-threads'] = '2.2.0'
        write_json(core_path, core)
        # Keep upstream loaders/workers, replacing the binary with the reactor
        # compiled from this fork. The export check above prevents the upstream
        # missing-CRT initialization failure from being republished.
        provenance = {'upstream': URL, 'integrity': 'sha512-' + INTEGRITY,
                      'patch': '@emnapi/core 1.11.3 dependency metadata: wasi-threads 1.2.3 -> 2.2.0',
                      'wasmSha256': hashlib.sha256(wasm.read_bytes()).hexdigest(),
                      'wasmBuild': 'Rust 1.95.0, napi-build 2.3.2, resolved reactor CRT; see crates/node/build.rs',
                      'sourceCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
        write_json(package / 'hub-provenance.json', provenance)
        manifest['files'].append('hub-provenance.json')
        manifest.pop('overrides')
        write_json(package / 'package.json', manifest)
        subprocess.run(['npm', 'pack', '--ignore-scripts', '--pack-destination', str(OUTPUT)], cwd=package, check=True)

if __name__ == '__main__':
    main()
