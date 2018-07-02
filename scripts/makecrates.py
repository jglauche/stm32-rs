"""
makecrates.py
Copyright 2017 Adam Greig
Licensed under the MIT and Apache 2.0 licenses.

Autogenerate the crate Cargo.toml and src/lib.rs file based on available
YAML files for each STM32 family.

Usage: python3 scripts/makecrates.py devices/
"""

import os
import sys
import glob
import os.path
import yaml

VERSION = "0.2.1"
SVD2RUST_VERSION = "0.13.1"

CARGO_TOML_TPL = """\
[package]
name = "{crate}"
version = "{version}"
authors = ["Adam Greig <adam@adamgreig.com>"]
description = "Device support crates for {family} devices"
repository = "https://github.com/adamgreig/stm32-rs"
readme = "README.md"
keywords = ["stm32", "svd2rust", "no_std", "embedded"]
categories = ["embedded", "no-std"]
license = "MIT/Apache-2.0"

[dependencies]
bare-metal = "0.2.0"
vcell = "0.1.0"
cortex-m = "0.5.2"

[dependencies.cortex-m-rt]
optional = true
version = "0.5.1"

[features]
default = []
rt = ["cortex-m-rt/device"]
{features}
"""

SRC_LIB_RS_TPL = """\
//! Peripheral access API for {family} microcontrollers
//! (generated using [svd2rust] {svd2rust_version})
//! [svd2rust]: https://github.com/japaric/svd2rust
//!
//! You can find an overview of the API here:
//! https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api
//!
//! For more details see the README here:
//! https://github.com/adamgreig/stm32-rs

#![allow(non_camel_case_types)]
#![feature(const_fn)]
#![feature(try_from)]
#![no_std]

#![cfg_attr(feature = "rt", feature(global_asm))]
#![cfg_attr(feature = "rt", feature(use_extern_macros))]
#![cfg_attr(feature = "rt", feature(used))]

extern crate vcell;
extern crate bare_metal;
extern crate cortex_m;

#[cfg(feature = "rt")]
extern crate cortex_m_rt;

{mods}
"""

README_TPL = """\
# {crate}
This crate provides an autogenerated API for access to {family} peripherals.
The API is generated using [svd2rust] with patched svd files containing
extensive type-safe support. For more information please see the [main repo].

[svd2rust]: https://github.com/japaric/svd2rust
[main repo]: https://github.com/adamgreig/stm32-rs

## Usage
Each device supported by this crate is behind a feature gate so that you only
compile the device(s) you want. To use, in your Cargo.toml:

```toml
[dependencies.{crate}]
version = "{version}"
features = ["{device}", "rt"]
```

The `rt` feature is optional and brings in support for `cortex-m-rt`.

In your code:

```rust
extern crate {crate};
use {crate}::{device};

let mut peripherals = {device}::Peripherals::take().unwrap();
let gpioa = &peripherals.GPIOA;
gpioa.odr.modify(|_, w| w.odr0().set_bit());
```

For full details on the autogenerated API, please see:
https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api

## Supported Devices

| Module | Devices | Links |
|:------:|:-------:|:-----:|
{devices}
"""


BUILD_TPL = """\
use std::env;
use std::fs;
use std::path::PathBuf;
fn main() {{
    if env::var_os("CARGO_FEATURE_RT").is_some() {{
        let out = &PathBuf::from(env::var_os("OUT_DIR").unwrap());
        println!("cargo:rustc-link-search={{}}", out.display());
        let device_file = {device_clauses};
        fs::copy(device_file, out.join("device.x")).unwrap();
        println!("cargo:rerun-if-changed={{}}", device_file);
    }}
    println!("cargo:rerun-if-changed=build.rs");
}}
"""


def read_device_table():
    path = os.path.join(
        os.path.abspath(os.path.split(__file__)[0]), os.pardir,
        "stm32_part_table.yaml")
    with open(path) as f:
        table = yaml.safe_load(f)
    return table


def make_device_rows(table, family):
    rows = []
    for device, dt in table[family].items():
        links = "[{}]({}), [st.com]({})".format(
            dt['rm'], dt['rm_url'], dt['url'])
        members = ", ".join(m for m in dt['members'])
        rows.append("| {} | {} | {} |".format(device, members, links))
    return "\n".join(sorted(rows))


def make_features(devices):
    return "\n".join("{} = []".format(d) for d in sorted(devices))


def make_mods(devices):
    return "\n".join('#[cfg(feature = "{0}")]\npub mod {0};\n'.format(d)
                     for d in sorted(devices))

def make_device_clauses(devices):
    return " else ".join("""\
        if env::var_os("CARGO_FEATURE_{}").is_some() {{
            "src/{}/device.x"
        }}""".format(d.upper(), d) for d in sorted(devices)) + \
            " else { panic!(\"No device features selected\"); }"


def main():
    devices = {}

    for path in glob.glob(os.path.join(sys.argv[1], "*.yaml")):
        yamlfile = os.path.basename(path)
        family = yamlfile[:7]
        device = os.path.splitext(yamlfile)[0].lower()
        if family not in devices:
            devices[family] = []
        devices[family].append(device)

    table = read_device_table()

    dirs = ", ".join(x.lower()+"/" for x in devices)
    print("Going to create/update the following directories:")
    print(dirs)
    input("Enter to continue, ctrl-C to cancel")

    for family in devices:
        devices[family] = sorted(devices[family])
        crate = family.lower()
        features = make_features(devices[family])
        clauses = make_device_clauses(devices[family])
        mods = make_mods(devices[family])
        ufamily = family.upper()
        cargo_toml = CARGO_TOML_TPL.format(
            family=ufamily, crate=crate, version=VERSION, features=features)
        readme = README_TPL.format(
            family=ufamily, crate=crate, device=devices[family][0],
            version=VERSION, svd2rust_version=SVD2RUST_VERSION,
            devices=make_device_rows(table, family))
            # devices="\n".join("* " + d.upper().replace("X", "x")
                              # for d in devices[family]))
        lib_rs = SRC_LIB_RS_TPL.format(family=ufamily, mods=mods,
                                       svd2rust_version=SVD2RUST_VERSION)
        build_rs = BUILD_TPL.format(device_clauses=clauses)

        os.makedirs(os.path.join(crate, "src"), exist_ok=True)
        with open(os.path.join(crate, "Cargo.toml"), "w") as f:
            f.write(cargo_toml)
        with open(os.path.join(crate, "README.md"), "w") as f:
            f.write(readme)
        with open(os.path.join(crate, "src", "lib.rs"), "w") as f:
            f.write(lib_rs)
        with open(os.path.join(crate, "build.rs"), "w") as f:
            f.write(build_rs)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: {} <yaml directory>".format(sys.argv[0]))
        sys.exit(1)
    else:
        main()
