# Handoff Vibe for Windows 11

This first x64 beta is a portable Windows app and Bluetooth diagnostic for Powerbeats Fit. It uses Windows controls and the same noise-control layout as Handoff Vibe for Linux. The portable build adds no driver, service or installer and runs as a normal user.

Battery, ANC and automatic switching remain disabled while the headset control channel is being verified. The Bluetooth and Sound buttons open Windows Settings for manual connection and output selection.

## First hardware test

1. Extract the Windows beta artifact and open `handoff-vibe.exe`.
2. Pair Powerbeats Fit in Bluetooth settings. Open PowerShell in the extracted folder.
3. Run `.\handoff-vibe-diagnostics.exe list`. It lists paired classic Bluetooth devices and their connection state without scanning for nearby devices.
4. Keep the iPhone playing through the Beats. Run `.\handoff-vibe-diagnostics.exe probe AA:BB:CC:DD:EE:FF` with the Beats address from the list. Check whether playback continues. The probe only opens the advertised standard Serial Port service and closes it without sending headset commands. Windows may briefly connect to the earbuds during the probe.
5. Record the result and whether audio moved. Share the status/error code and Windows version, with Bluetooth addresses removed.

Opening the Serial Port service only establishes that transport is available. Powerbeats Fit also exposes a separate AAP service. Handoff Vibe on Linux uses classic L2CAP for AAP, while Windows desktop Bluetooth sockets provide RFCOMM. The beta does not assume the Serial Port service speaks AAP or send unverified commands to it.

## Build and verify

On Windows with CMake and Visual Studio C++ tools:

```powershell
cmake -S windows -B build/windows -A x64
cmake --build build/windows --config Release
ctest --test-dir build/windows -C Release --output-on-failure
```

The Windows workflow runs command-line checks, launches and closes the GUI, and records idle working set and private memory. The target is under 500 MB for each. Remeasure with a live session once headset controls are implemented. Physical testing requires a Windows machine with Bluetooth and the earbuds.
