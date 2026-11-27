// SPDX-License-Identifier: GPL-3.0-or-later
#include "address.h"
#include <iostream>

int main()
{
    if (parse_address("12:ab:CD:34:56:78") != 0x12abcd345678ULL ||
        parse_address("00:00:00:00:00:01") != 1)
        return 1;
    for (const auto* invalid : {"", "12:AB:CD:34:56:7", "12-AB-CD-34-56-78",
                                "12:GX:CD:34:56:78", "12:AB:CD:34:56:78 ",
                                "00:00:00:00:00:00", "ff:FF:ff:FF:FF:ff"}) {
        if (parse_address(invalid)) {
            std::cerr << "Accepted invalid address: " << invalid << '\n';
            return 1;
        }
    }
    return 0;
}
