/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 Asensado */
#define _GNU_SOURCE
#include "process_guard.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/file.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <unistd.h>

int handoff_process_guard(void)
{
    const char *parent = getenv("HANDOFF_SUPERVISOR_PID");
    if (parent) {
        char *end;
        errno = 0;
        long expected = strtol(parent, &end, 10);
        /* Close the race where the supervisor died before prctl ran. */
        if (errno || *end || expected <= 1 || expected > INT_MAX ||
            prctl(PR_SET_PDEATHSIG, SIGKILL) < 0 || getppid() != expected) {
            fprintf(stderr, "Handoff supervisor is no longer available\n");
            return -1;
        }
    }
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    if (!runtime || runtime[0] != '/') {
        fprintf(stderr, "A private XDG_RUNTIME_DIR is required\n");
        return -1;
    }
    char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s/earport-daemon.lock", runtime) >= (int)sizeof(path))
        return -1;
    int fd = open(path, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
    struct stat st;
    if (fd < 0)
        return -1;
    if (fstat(fd, &st) < 0 || st.st_uid != getuid() || !S_ISREG(st.st_mode) ||
        flock(fd, LOCK_EX | LOCK_NB) < 0) {
        fprintf(stderr, "Another backend owns the control transport (or invalid lock)\n");
        close(fd);
        return -1;
    }
    return fd;
}
