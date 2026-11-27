// SPDX-License-Identifier: GPL-3.0-or-later
#include <winsock2.h>
#include <windows.h>
#include <ws2bth.h>
#include <bluetoothapis.h>

#include "address.h"
#include <cwctype>
#include <iomanip>
#include <iostream>
#include <string_view>

namespace {
constexpr GUID serial_port_service{0x00001101, 0x0000, 0x1000,
                                   {0x80, 0x00, 0x00, 0x80, 0x5f, 0x9b, 0x34, 0xfb}};

void print_address(BTH_ADDR address)
{
    std::wcout << std::hex << std::uppercase << std::setfill(L'0');
    for (int shift = 40; shift >= 0; shift -= 8) {
        if (shift != 40)
            std::wcout << L':';
        std::wcout << std::setw(2) << ((address >> shift) & 0xff);
    }
    std::wcout << std::dec << std::setfill(L' ');
}

int list_paired()
{
    BLUETOOTH_DEVICE_SEARCH_PARAMS search{};
    search.dwSize = sizeof(search);
    search.fReturnAuthenticated = TRUE;
    BLUETOOTH_DEVICE_INFO device{};
    device.dwSize = sizeof(device);
    auto handle = BluetoothFindFirstDevice(&search, &device);
    if (!handle) {
        const auto error = GetLastError();
        if (error == ERROR_NO_MORE_ITEMS) {
            std::wcout << L"No paired classic Bluetooth devices. Pair your Beats in Windows Settings.\n";
            return 0;
        }
        std::wcerr << L"Bluetooth device listing failed (Windows error " << error
                   << L"). Check that Bluetooth is enabled.\n";
        return 2;
    }

    do {
        if (!device.fAuthenticated)
            continue;
        print_address(device.Address.ullLong);
        std::wcout << L"  ";
        for (const wchar_t ch : device.szName) {
            if (ch == L'\0')
                break;
            std::wcout << (std::iswcntrl(ch) ? L'?' : ch);
        }
        std::wcout << (device.fConnected ? L"  [connected]\n" : L"  [paired]\n");
        device.dwSize = sizeof(device);
    } while (BluetoothFindNextDevice(handle, &device));
    const auto error = GetLastError();
    BluetoothFindDeviceClose(handle);
    if (error != ERROR_NO_MORE_ITEMS) {
        std::wcerr << L"Bluetooth device listing ended early (Windows error " << error << L").\n";
        return 2;
    }
    return 0;
}

struct WinsockSession {
    WinsockSession() { WSADATA data{}; error = WSAStartup(MAKEWORD(2, 2), &data); }
    ~WinsockSession() { if (error == 0) WSACleanup(); }
    int error;
};

struct BluetoothSocket {
    SOCKET value = socket(AF_BTH, SOCK_STREAM, BTHPROTO_RFCOMM);
    ~BluetoothSocket() { if (value != INVALID_SOCKET) closesocket(value); }
};

int report_socket_error(const wchar_t* operation, int error)
{
    std::wcerr << operation << L" failed (Winsock error " << error << L").\n";
    return 2;
}

int probe(BTH_ADDR address)
{
    BLUETOOTH_DEVICE_SEARCH_PARAMS search{};
    search.dwSize = sizeof(search);
    search.fReturnAuthenticated = TRUE;
    BLUETOOTH_DEVICE_INFO device{};
    device.dwSize = sizeof(device);
    auto handle = BluetoothFindFirstDevice(&search, &device);
    bool paired = false;
    if (handle) {
        do {
            paired = device.fAuthenticated && device.Address.ullLong == address;
        } while (!paired && BluetoothFindNextDevice(handle, &device));
        BluetoothFindDeviceClose(handle);
    }
    if (!paired) {
        std::wcerr << L"Pair this device in Windows Settings first, then use the address from list.\n";
        return 2;
    }

    WinsockSession winsock;
    if (winsock.error)
        return report_socket_error(L"Starting Winsock", winsock.error);
    BluetoothSocket link;
    if (link.value == INVALID_SOCKET)
        return report_socket_error(L"Opening the RFCOMM socket", WSAGetLastError());

    const ULONG enabled = 1;
    const auto* option = reinterpret_cast<const char*>(&enabled);
    if (setsockopt(link.value, SOL_RFCOMM, SO_BTH_AUTHENTICATE, option, sizeof(enabled)) == SOCKET_ERROR ||
        setsockopt(link.value, SOL_RFCOMM, SO_BTH_ENCRYPT, option, sizeof(enabled)) == SOCKET_ERROR)
        return report_socket_error(L"Requiring authentication and encryption", WSAGetLastError());

    u_long nonblocking = 1;
    if (ioctlsocket(link.value, FIONBIO, &nonblocking) == SOCKET_ERROR)
        return report_socket_error(L"Setting nonblocking mode", WSAGetLastError());

    SOCKADDR_BTH target{};
    target.addressFamily = AF_BTH;
    target.btAddr = address;
    target.serviceClassId = serial_port_service;
    if (connect(link.value, reinterpret_cast<const sockaddr*>(&target), sizeof(target)) == SOCKET_ERROR) {
        const int error = WSAGetLastError();
        if (error != WSAEWOULDBLOCK)
            return report_socket_error(L"Connecting to the Serial Port service", error);

        fd_set writable, failed;
        FD_ZERO(&writable);
        FD_ZERO(&failed);
        FD_SET(link.value, &writable);
        FD_SET(link.value, &failed);
        timeval deadline{8, 0};
        const int ready = select(0, nullptr, &writable, &failed, &deadline);
        if (ready == 0)
            return report_socket_error(L"Connecting to the Serial Port service", WSAETIMEDOUT);
        if (ready == SOCKET_ERROR)
            return report_socket_error(L"Waiting for the socket", WSAGetLastError());
        int result = 0;
        int length = sizeof(result);
        if (getsockopt(link.value, SOL_SOCKET, SO_ERROR, reinterpret_cast<char*>(&result), &length) == SOCKET_ERROR)
            return report_socket_error(L"Checking the connection", WSAGetLastError());
        if (result || FD_ISSET(link.value, &failed))
            return report_socket_error(L"Connecting to the Serial Port service", result ? result : WSAECONNABORTED);
    }

    std::wcout << L"Authenticated, encrypted RFCOMM Serial Port opened. No headset commands sent.\n";
    return 0;
}

void help()
{
    std::wcout << L"Handoff Vibe for Windows 0.1.0-beta.1\n"
               << L"  list                    Show paired classic Bluetooth devices\n"
               << L"  probe AA:BB:CC:DD:EE:FF Test the paired device's Serial Port connection\n"
               << L"  --version               Show the beta version\n";
}
}

int main(int argc, char** argv)
{
    const std::string_view command = argc > 1 ? argv[1] : "--help";
    if (argc <= 2 && (command == "--help" || command == "-h")) {
        help();
        return 0;
    }
    if (argc == 2 && command == "--version") {
        std::wcout << L"0.1.0-beta.1\n";
        return 0;
    }
    if (argc == 2 && command == "list")
        return list_paired();
    if (argc == 3 && command == "probe") {
        if (const auto address = parse_address(argv[2]))
            return probe(*address);
        std::wcerr << L"Use a Bluetooth address in AA:BB:CC:DD:EE:FF format.\n";
        return 1;
    }
    help();
    return 1;
}
