# Credits and sources

Original audio engine: [xatuke/handoff](https://github.com/xatuke/handoff),
Aayushman Choudhary and contributors. Based on installed commit
`4568bde6f19efe480bdc0e26058f49998bb58912`. Its README declares MIT licensing;
that checkout contains no separate license file. The original engine is retained in `upstream/` with MIT attribution.
A separately licensed integration patch in `patches/` adds GUI status telemetry, address validation, a per-device process
lock, initialized packet state, capped reconnect arithmetic, refreshed audio
sink discovery, and a fixed locale for the upstream audio-status parser.

GUI: Made with ❤️ by Asensado with ChatGPT 6.1-Sol Medium Work.
This is the creator credit requested by Asensado.

Design inspiration: [Packet](https://github.com/nozwock/packet), nozwock,
Dominik Baran, and contributors. No Packet source code, icons, or screenshots
are included in the application. The interface is a fresh GTK/libadwaita implementation.

Device identifier research (constant values and protocol layout only, no copied code):
[LibrePods BLEManager](https://github.com/kavishdevar/librepods/blob/main/android/app/src/main/java/me/kavishdevar/librepods/bluetooth/BLEManager.kt)
and [CAPod Apple device descriptions](https://github.com/d4rken-org/capod/tree/main/app/src/main/java/eu/darken/capod/pods/core/apple/ble/devices).

Product photos: Apple and Beats, downloaded from Apple's public product-image
CDN. Exact per-model URLs are in `assets/sources.json`. The photos are not
licensed for redistribution by this project and remain the property of Apple/Beats. This
local prototype includes them for device identification. Review asset rights
before public redistribution. The UI does not request images over the network.

Eligibility references:
- https://support.apple.com/en-gb/104988
- https://support.apple.com/en-sg/guide/beats/devee8a2c156/web

Eligibility is distinct from verified Linux protocol support. Models in the
catalog are candidates; a successful AACP handshake is shown separately. A
Bluetooth name is a hint, never proof of the model. Unknown and known
incompatible product IDs cannot silently pass based on a matching name.

Daily Bible verses: World English Bible (WEB), public domain, downloaded
from the publisher at https://ebible.org/Scriptures/eng-web_usfm.zip.
A curated set of 31 passages is bundled in assets/verses.json with no runtime
network requests. Publisher copyright status: https://worldenglish.bible/.

Creator profile: https://github.com/Asensado/
The historical internal application ID is retained solely for upgrade continuity.

Asensado’s additions use PolyForm Noncommercial 1.0.0. The original engine
remains MIT; see LICENSE, NOTICE, LICENSING.md, and LICENSES/MIT-upstream.txt.
