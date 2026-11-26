/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 Asensado */
#ifndef HANDOFF_PROCESS_GUARD_H
#define HANDOFF_PROCESS_GUARD_H
#ifdef __cplusplus
extern "C" {
#endif
/* Returns a held CLOEXEC lock fd, or -1. Call before opening any transport. */
int handoff_process_guard(void);
#ifdef __cplusplus
}
#endif
#endif
