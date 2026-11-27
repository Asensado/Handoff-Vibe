// SPDX-License-Identifier: GPL-3.0-or-later
#include <windows.h>
#include <shellapi.h>
#include <commctrl.h>
#include <uxtheme.h>

namespace {
constexpr int bluetooth_settings = 1;
constexpr int sound_settings = 2;
HFONT body_font;
HFONT title_font;

HWND add(HWND parent, const wchar_t* type, const wchar_t* text, int x, int y,
         int width, int height, DWORD flags = 0, int id = 0)
{
    const UINT dpi = GetDpiForWindow(parent);
    const auto scale = [dpi](int units) { return MulDiv(units, static_cast<int>(dpi), 96); };
    HWND child = CreateWindowExW(0, type, text, WS_CHILD | WS_VISIBLE | flags,
                                scale(x), scale(y), scale(width), scale(height), parent,
                                reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),
                                GetModuleHandleW(nullptr), nullptr);
    SendMessageW(child, WM_SETFONT, reinterpret_cast<WPARAM>(body_font), TRUE);
    if (lstrcmpW(type, L"BUTTON") == 0)
        SetWindowTheme(child, L"Explorer", nullptr);
    return child;
}

void open_settings(HWND owner, const wchar_t* uri)
{
    if (reinterpret_cast<INT_PTR>(ShellExecuteW(owner, L"open", uri, nullptr, nullptr, SW_SHOWNORMAL)) <= 32)
        MessageBoxW(owner, L"Open Settings from the Start menu.", L"Could not open Settings", MB_OK);
}

LRESULT CALLBACK window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam)
{
    switch (message) {
    case WM_CREATE: {
        const auto dpi = static_cast<int>(GetDpiForWindow(window));
        body_font = CreateFontW(-MulDiv(15, dpi, 96), 0, 0, 0, FW_NORMAL, FALSE, FALSE,
                               FALSE, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        title_font = CreateFontW(-MulDiv(28, dpi, 96), 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE,
                                FALSE, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        const HWND title = add(window, L"STATIC", L"Handoff Vibe", 24, 24, 390, 38);
        SendMessageW(title, WM_SETFONT, reinterpret_cast<WPARAM>(title_font), TRUE);
        add(window, L"STATIC", L"Windows beta  •  Powerbeats Fit", 24, 68, 390, 22);
        add(window, L"STATIC", L"Open Bluetooth settings to pair or connect your Beats.", 24, 105, 390, 42);
        add(window, L"BUTTON", L"Bluetooth settings", 24, 154, 176, 36, WS_TABSTOP, bluetooth_settings);
        add(window, L"BUTTON", L"Sound settings", 216, 154, 176, 36, WS_TABSTOP, sound_settings);

        add(window, L"STATIC", L"Noise control", 24, 223, 390, 25);
        add(window, L"BUTTON", L"Off", 24, 256, 108, 34, WS_DISABLED);
        add(window, L"BUTTON", L"Transparency", 142, 256, 118, 34, WS_DISABLED);
        add(window, L"BUTTON", L"Noise cancellation", 270, 256, 144, 34, WS_DISABLED);
        add(window, L"STATIC", L"Battery, noise controls and automatic switching need a verified headset connection.",
            24, 318, 392, 54);
        return 0;
    }
    case WM_COMMAND:
        if (LOWORD(wparam) == bluetooth_settings)
            open_settings(window, L"ms-settings:bluetooth");
        else if (LOWORD(wparam) == sound_settings)
            open_settings(window, L"ms-settings:sound");
        return 0;
    case WM_DESTROY:
        DeleteObject(title_font);
        DeleteObject(body_font);
        PostQuitMessage(0);
        return 0;
    default:
        return DefWindowProcW(window, message, wparam, lparam);
    }
}
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show)
{
    SetProcessDPIAware();
    INITCOMMONCONTROLSEX controls{sizeof(controls), ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&controls);
    WNDCLASSW window_class{};
    window_class.hInstance = instance;
    window_class.lpfnWndProc = window_proc;
    window_class.lpszClassName = L"HandoffVibeBeta";
    window_class.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32512));
    window_class.hbrBackground = GetSysColorBrush(COLOR_WINDOW);
    if (!RegisterClassW(&window_class))
        return 1;

    const DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    const auto dpi = static_cast<int>(GetDpiForSystem());
    RECT size{0, 0, MulDiv(440, dpi, 96), MulDiv(387, dpi, 96)};
    AdjustWindowRectExForDpi(&size, style, FALSE, 0, static_cast<UINT>(dpi));
    HWND window = CreateWindowExW(0, window_class.lpszClassName, L"Handoff Vibe",
                                  style, CW_USEDEFAULT, CW_USEDEFAULT, size.right - size.left,
                                  size.bottom - size.top, nullptr, nullptr, instance, nullptr);
    if (!window)
        return 1;
    ShowWindow(window, show);

    MSG message{};
    for (;;) {
        const auto result = GetMessageW(&message, nullptr, 0, 0);
        if (result == 0)
            return static_cast<int>(message.wParam);
        if (result == -1)
            return 1;
        if (!IsDialogMessageW(window, &message)) {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }
}
