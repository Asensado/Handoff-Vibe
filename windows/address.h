// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <optional>
#include <string_view>

inline std::optional<std::uint64_t> parse_address(std::string_view text)
{
    if (text.size() != 17)
        return std::nullopt;
    std::uint64_t address = 0;
    for (std::size_t i = 0; i < text.size(); ++i) {
        const char ch = text[i];
        if (i % 3 == 2) {
            if (ch != ':')
                return std::nullopt;
            continue;
        }
        unsigned digit;
        if (ch >= '0' && ch <= '9')
            digit = static_cast<unsigned>(ch - '0');
        else if (ch >= 'A' && ch <= 'F')
            digit = static_cast<unsigned>(ch - 'A' + 10);
        else if (ch >= 'a' && ch <= 'f')
            digit = static_cast<unsigned>(ch - 'a' + 10);
        else
            return std::nullopt;
        address = (address << 4) | digit;
    }
    if (address == 0 || address == 0xffffffffffffULL)
        return std::nullopt;
    return address;
}
