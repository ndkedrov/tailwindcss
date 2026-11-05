// Scanner contract: integrations/oxide/wasm.test.ts:33-59.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { Worker, isMainThread, parentPort, workerData } = require('node:worker_threads')
let wasiWorkers = 0
require('node:worker_threads').Worker = class extends Worker {
  constructor(filename, options) {
    super(filename, options)
    if (String(filename).endsWith('wasi-worker.mjs')) wasiWorkers++
  }
}
assert.equal(process.platform, 'linux', 'PRECONDITION: Linux WASI filesystem support')
const root = path.resolve(process.argv[2] || workerData?.root || '.')
const resolveFrom = require('node:module').createRequire(path.join(root, 'package.json'))
const wasmPath = resolveFrom.resolve('@tailwindcss/oxide-wasm32-wasi')
const wasmRequire = require('node:module').createRequire(wasmPath)
const versions = {
  '@napi-rs/wasm-runtime': '1.2.7', '@emnapi/core': '1.11.3',
  '@emnapi/runtime': '1.11.3', '@tybys/wasm-util': '0.10.4',
  '@emnapi/wasi-threads': '2.2.0', tslib: '2.9.1',
}
function packageVersion(name) {
  let directory = path.dirname(wasmRequire.resolve(name))
  while (directory !== path.dirname(directory)) {
    const file = path.join(directory, 'package.json')
    if (fs.existsSync(file)) {
      const manifest = JSON.parse(fs.readFileSync(file))
      if (manifest.name === name) return manifest.version
    }
    directory = path.dirname(directory)
  }
  throw Error(`PRECONDITION: missing manifest for ${name}`)
}
for (const [name, version] of Object.entries(versions)) assert.equal(packageVersion(name), version, name)

function scan(base) {
  console.error(`scan: loading WASM (main=${isMainThread})`)
  const { Scanner } = require(wasmPath)
  console.error('scan: WASM loaded')
  // Import the WASI package directly: native fallback cannot mask a broken WASM build.
  const scanner = new Scanner({ sources: [{ base, pattern: '**/*.html', negated: false }] })
  const actual = scanner.scan().sort()
  console.error('scan: completed')
  // Parallel walk spawns Rust threads: crates/ignore/src/walk.rs:1543-1551.
  assert.ok(wasiWorkers > 0, 'PRECONDITION: scanner must exercise WASI worker startup')
  for (let i = 0; i < 256; i++) assert.ok(actual.includes(`mt-[${i}px]`), `missing candidate ${i}`)
  for (const name of Object.keys(require.cache)) assert.ok(!name.endsWith('.node'), 'WASM test loaded native code')
  return actual
}

if (!isMainThread) {
  parentPort.postMessage(scan(workerData.base))
  process.exit(0)
} else {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-wasi-scan-'))
  ;(async () => {
    try {
      for (let i = 0; i < 256; i++) {
        const directory = path.join(base, `group-${i % 16}`)
        fs.mkdirSync(directory, { recursive: true })
        fs.writeFileSync(path.join(directory, `${i}.html`), `<div class="flex mt-[${i}px] hover:bg-red-500"></div>`)
      }
      const actual = scan(base)
      const inWorker = await new Promise((resolve, reject) => {
        const worker = new Worker(__filename, { workerData: { root, base } })
        worker.once('message', resolve)
        worker.once('error', reject)
        worker.once('exit', code => { if (code) reject(Error(`worker exited ${code}`)) })
      })
      assert.deepEqual(inWorker, actual, 'worker-thread result differs')
      const { Scanner } = resolveFrom('@tailwindcss/oxide')
      const native = new Scanner({ sources: [{ base, pattern: '**/*.html', negated: false }] }).scan().sort()
      assert.deepEqual(actual, native, 'WASM/native scanner parity')
      console.log(JSON.stringify({ ok: true, files: 256, candidates: actual.length, wasiWorkers, workerParity: true, nativeParity: true, versions }))
    } finally { fs.rmSync(base, { recursive: true, force: true }) }
  })().then(() => process.exit(0), error => { console.error(error); process.exit(1) })
}
