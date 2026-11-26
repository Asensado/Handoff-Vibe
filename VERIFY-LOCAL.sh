#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -m unittest discover -s tests -p 'test_*.py'
node tests/indicator.mjs
if [ ! -f earport/daemon/build/build.ninja ]; then
    meson setup earport/daemon/build earport/daemon --buildtype=release
fi
ninja -C earport/daemon/build
meson test -C earport/daemon/build --print-errorlogs
cmake -S upstream -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
