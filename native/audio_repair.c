/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 Asensado
 * Handoff-owned bounded audio refresh. Never creates sinks, moves streams,
 * changes card profiles, or shells out to a command string. */
#define _GNU_SOURCE
#include "../earport/daemon/src/audio_route.h"
#include <gio/gio.h>
#include <signal.h>
#include <sys/prctl.h>
#include <unistd.h>

#ifndef AUDIO_REPAIR_STEP_MS
#define AUDIO_REPAIR_STEP_MS 2000
#endif
#ifndef AUDIO_REPAIR_SETTLE_MS
#define AUDIO_REPAIR_SETTLE_MS 500
#endif

typedef enum { FIND_SINK, FIND_STREAMS, SUSPEND, RESUME } Step;
typedef struct {
    char *prefix;
    char *sink;
    bool automatic;
    bool cancelled;
    bool suspended;
    bool failed;
    Step step;
    guint timer;
    GSubprocess *child;
} Repair;
static Repair *active;
static bool shutting_down;
static void run_step(Repair *r, Step step);

static void finish(Repair *r, const char *message)
{
    if (r->timer)
        g_source_remove(r->timer);
    g_clear_object(&r->child);
    g_free(r->prefix);
    g_free(r->sink);
    active = NULL;
    g_free(r);
    g_message("%s", message);
}

static gboolean deadline(gpointer data)
{
    Repair *r = data;
    r->timer = 0;
    r->failed = true;
    g_subprocess_force_exit(r->child);
    return G_SOURCE_REMOVE;
}

static gboolean resume_later(gpointer data)
{
    Repair *r = data;
    r->timer = 0;
    run_step(r, RESUME);
    return G_SOURCE_REMOVE;
}

static void fail_or_cancel(Repair *r)
{
    // Even an interrupted suspend may have reached the server. Always undo it.
    if (r->suspended && r->step != RESUME)
        run_step(r, RESUME);
    else
        finish(r, r->cancelled ? "Audio repair cancelled" : "Could not restart the AirPods audio");
}

static bool has_stream(const char *text, const char *sink)
{
    bool on_sink = false;
    g_auto(GStrv) lines = g_strsplit(text, "\n", -1);
    for (char **line = lines; *line; line++) {
        char *value = g_strstrip(*line);
        if (g_str_has_prefix(value, "Sink Input #"))
            on_sink = false;
        else if (g_str_has_prefix(value, "Sink: "))
            on_sink = g_strcmp0(value + 6, sink) == 0;
        else if (on_sink && g_strcmp0(value, "Corked: no") == 0)
            return true;
    }
    return false;
}

static void completed(GObject *source, GAsyncResult *result, gpointer data)
{
    Repair *r = data;
    char *output = NULL;
    GError *error = NULL;
    bool ok = g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result, &output, NULL, &error);
    if (r->timer) {
        g_source_remove(r->timer);
        r->timer = 0;
    }
    ok = ok && g_subprocess_get_if_exited(r->child) && g_subprocess_get_exit_status(r->child) == 0;
    g_clear_object(&r->child);
    g_clear_error(&error);
    if (!ok || r->cancelled) {
        r->failed = r->failed || !ok;
        g_free(output);
        fail_or_cancel(r);
        return;
    }
    if (r->step == FIND_SINK) {
        g_auto(GStrv) lines = g_strsplit(output ? output : "", "\n", -1);
        for (char **line = lines; *line; line++) {
            g_auto(GStrv) columns = g_strsplit(*line, "\t", 3);
            if (columns[0] && columns[1] && g_str_has_prefix(columns[1], r->prefix)) {
                r->sink = g_strdup(columns[0]);
                break;
            }
        }
        g_free(output);
        if (!r->sink)
            finish(r, "Nothing playing to the AirPods to restart");
        else
            run_step(r, r->automatic ? FIND_STREAMS : SUSPEND);
    } else if (r->step == FIND_STREAMS) {
        bool playing = has_stream(output ? output : "", r->sink);
        g_free(output);
        if (playing)
            run_step(r, SUSPEND);
        else
            finish(r, "Nothing playing to the AirPods to restart");
    } else {
        g_free(output);
        if (r->step == SUSPEND)
            r->timer = g_timeout_add(AUDIO_REPAIR_SETTLE_MS, resume_later, r);
        else
            finish(r, r->failed ? "Could not restart the AirPods audio" : "Restarted the sound playing to the AirPods");
    }
}

static void attach_parent(gpointer data)
{
    pid_t expected = GPOINTER_TO_INT(data);
    // The production child is pactl itself, with no intermediate shell/helpers.
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) < 0 || getppid() != expected)
        _exit(125);
}

static void run_step(Repair *r, Step step)
{
    r->step = step;
    if (step == SUSPEND)
        r->suspended = true;
    const char *tool = "/usr/bin/pactl";
#ifdef AUDIO_REPAIR_TESTING
    tool = g_getenv("FAKE_PACTL_PATH");
#endif
    const char *argv[] = {tool, NULL, NULL, NULL, NULL};
    if (step == FIND_SINK) {
        argv[1] = "list"; argv[2] = "sinks"; argv[3] = "short";
    } else if (step == FIND_STREAMS) {
        argv[1] = "list"; argv[2] = "sink-inputs";
    } else {
        argv[1] = "suspend-sink"; argv[2] = r->sink; argv[3] = step == SUSPEND ? "1" : "0";
    }
    GSubprocessLauncher *launcher = g_subprocess_launcher_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE |
                                                              G_SUBPROCESS_FLAGS_STDERR_SILENCE);
    g_subprocess_launcher_setenv(launcher, "LC_ALL", "C", TRUE);
    g_subprocess_launcher_set_child_setup(launcher, attach_parent, GINT_TO_POINTER(getpid()), NULL);
    r->child = g_subprocess_launcher_spawnv(launcher, argv, NULL);
    g_object_unref(launcher);
    if (!r->child) {
        r->failed = true;
        fail_or_cancel(r);
        return;
    }
    r->timer = g_timeout_add(AUDIO_REPAIR_STEP_MS, deadline, r);
    g_subprocess_communicate_utf8_async(r->child, NULL, NULL, completed, r);
}

bool audio_route_cancel(void)
{
    Repair *r = active;
    if (!r)
        return false;
    r->cancelled = true;
    if (r->child && r->step != RESUME)
        g_subprocess_force_exit(r->child);
    else if (!r->child) {
        if (r->timer) { g_source_remove(r->timer); r->timer = 0; }
        fail_or_cancel(r);
    }
    return true;
}

void audio_route_restart(const char *address, const char *mode)
{
    if (shutting_down || active || !address || !mode)
        return;
    if (g_strcmp0(mode, "streams") && g_strcmp0(mode, "output") && g_strcmp0(mode, "any"))
        return;
    Repair *r = g_new0(Repair, 1);
    char *name = g_ascii_strup(address, -1);
    g_strdelimit(name, ":", '_');
    r->prefix = g_strdup_printf("bluez_output.%s.", name);
    g_free(name);
    r->automatic = g_strcmp0(mode, "streams") == 0;
    active = r;
    g_message("Restarting the sound to the AirPods (%s)", mode);
    run_step(r, FIND_SINK);
}

void audio_route_shutdown(void)
{
    shutting_down = true;
    audio_route_cancel();
    gint64 end = g_get_monotonic_time() + 5 * G_USEC_PER_SEC;
    while (active && g_get_monotonic_time() < end) {
        g_main_context_iteration(NULL, FALSE);
        g_usleep(1000);
    }
}
