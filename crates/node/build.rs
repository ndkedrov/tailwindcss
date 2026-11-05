extern crate napi_build;

fn main() {
  if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("wasi") {
    // napi-build 2.3.2 locates crt1-reactor.o relative to RUSTC. napi's CLI
    // can supply the bare command "rustc", which silently omits the reactor
    // and leaves pthread TLS uninitialized. Resolve the selected compiler's
    // actual sysroot before handing its path to napi-build.
    let rustc = std::env::var_os("RUSTC").expect("Cargo must provide RUSTC");
    let output = std::process::Command::new(rustc)
      .args(["--print", "sysroot"])
      .output()
      .expect("query Rust sysroot for WASI reactor");
    assert!(output.status.success(), "Rust sysroot query failed");
    let sysroot = String::from_utf8(output.stdout).expect("UTF-8 Rust sysroot");
    let sysroot = std::path::Path::new(sysroot.trim());
    let target = std::env::var("TARGET").expect("Cargo must provide TARGET");
    let reactor = sysroot.join("lib/rustlib").join(target).join("lib/self-contained/crt1-reactor.o");
    assert!(reactor.is_file(), "WASI reactor is required: {}", reactor.display());
    let compiler = sysroot.join("bin").join(if cfg!(windows) { "rustc.exe" } else { "rustc" });
    assert!(compiler.is_file(), "Rust compiler is required: {}", compiler.display());
    std::env::set_var("RUSTC", compiler);
  }
  napi_build::setup();
}
