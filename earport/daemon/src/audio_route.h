/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2024 EarPort Contributors
 * SPDX-FileCopyrightText: 2026 Asensado */
#ifndef AUDIO_ROUTE_H
#define AUDIO_ROUTE_H
#include <stdbool.h>
/* Bounded native sink refresh. "streams" requires an uncorked local stream;
 * "any" / "output" are explicit user recovery. No temporary sinks or profiles. */
void audio_route_restart(const char *airpods_address, const char *mode);
bool audio_route_cancel(void);
void audio_route_shutdown(void);
#endif
