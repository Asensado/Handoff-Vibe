/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2024 EarPort Contributors
 *
 * The sound restart script, run for real against a fake pactl (canned sink
 * and stream lists, actions logged) and a sleep that doesn't wait, both
 * first in PATH
 */

#include <glib.h>
#include <gio/gio.h>
#include <glib/gstdio.h>
#include <string.h>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#include "audio_route.h"

#define AIRPODS "00:00:00:00:00:0A"

static char *dir;
static GPtrArray *messages;

static const char FAKE_PACTL[] =
    "#!/bin/sh\n"
    "echo $$ > \"$FAKE_PACTL_DIR/child-pid\"\n"
    "[ -e \"$FAKE_PACTL_DIR/hang\" ] && exec /bin/sleep 60\n"
    "case \"$1\" in\n"
    "list) [ \"$2\" = sinks ] && cat \"$FAKE_PACTL_DIR/sinks\" || cat \"$FAKE_PACTL_DIR/inputs\";;\n"
    "*) echo \"$*\" >> \"$FAKE_PACTL_DIR/log\"\n"
    "  [ \"$3\" = 1 ] && [ -e \"$FAKE_PACTL_DIR/fail-suspend\" ] && exit 1; exit 0;;\n"
    "esac\n";

/* pactl list sinks short: the AirPods (7), another pair (8), speakers */
static const char SINKS[] =
    "1\talsa_output.pci-0000_00_1f.3.analog-stereo\tPipeWire\ts32le 2ch 48000Hz\tIDLE\n"
    "7\tbluez_output.00_00_00_00_00_0A.1\tPipeWire\ts16le 2ch 48000Hz\tRUNNING\n"
    "8\tbluez_output.00_00_00_00_00_0B.1\tPipeWire\ts16le 2ch 48000Hz\tRUNNING\n";

/* pactl list sink-inputs: playing (20) and paused (21) on the AirPods,
 * playing on the speakers (22) and on a sink whose id starts the same (23) */
static const char INPUTS[] =
    "Sink Input #20\n\tDriver: PipeWire\n\tSink: 7\n\tCorked: no\n\n"
    "Sink Input #21\n\tDriver: PipeWire\n\tSink: 7\n\tCorked: yes\n\n"
    "Sink Input #22\n\tDriver: PipeWire\n\tSink: 1\n\tCorked: no\n\n"
    "Sink Input #23\n\tDriver: PipeWire\n\tSink: 77\n\tCorked: no\n";

static const char PAUSED_ONLY[] =
    "Sink Input #21\n\tDriver: PipeWire\n\tSink: 7\n\tCorked: yes\n\n"
    "Sink Input #22\n\tDriver: PipeWire\n\tSink: 1\n\tCorked: no\n";

static void log_handler(const gchar *domain, GLogLevelFlags level, const gchar *message,
                        gpointer user_data)
{
    (void)user_data;
    g_ptr_array_add(messages, g_strdup(message));
    g_log_default_handler(domain, level, message, NULL);
}

static void write_file(const char *name, const char *contents)
{
    g_autofree char *path = g_build_filename(dir, name, NULL);
    g_assert_true(g_file_set_contents(path, contents, -1, NULL));
}

static void setup(const char *sinks, const char *inputs, bool fail_load)
{
    write_file("sinks", sinks);
    write_file("inputs", inputs);
    write_file("log", "");
    g_autofree char *fail = g_build_filename(dir, "fail-load", NULL);
    if (fail_load)
        write_file("fail-load", "");
    else
        g_unlink(fail);
    g_ptr_array_set_size(messages, 0);
}

static bool logged(const char *prefix)
{
    for (guint i = 0; i < messages->len; i++)
        if (g_str_has_prefix(messages->pdata[i], prefix))
            return true;
    return false;
}

/* Runs the restart to its end; returns the pactl actions */
static char *restart(const char *mode)
{
    audio_route_restart(AIRPODS, mode);
    gint64 end = g_get_monotonic_time() + 5 * G_USEC_PER_SEC;
    while (!logged("Restarted") && !logged("Nothing playing") && !logged("Could not") &&
           g_get_monotonic_time() < end)
        g_main_context_iteration(NULL, FALSE);

    g_autofree char *path = g_build_filename(dir, "log", NULL);
    char *actions = NULL;
    g_assert_true(g_file_get_contents(path, &actions, NULL, NULL));
    return actions;
}

/* The streams playing to the AirPods go through a muted output and back,
 * the others stay */
static void test_streams(void)
{
    setup(SINKS, INPUTS, false);
    g_autofree char *actions = restart("streams");
    g_assert_true(logged("Restarted the sound playing to the AirPods"));
    g_assert_cmpstr(actions, ==, "suspend-sink 7 1\nsuspend-sink 7 0\n");
}

/* Nothing to restart: no AirPods output, or nothing playing to it */
static void test_nothing_playing(void)
{
    setup("1\talsa_output.pci-0000_00_1f.3.analog-stereo\tPipeWire\ts32le 2ch 48000Hz\tIDLE\n",
          INPUTS, false);
    g_autofree char *no_output = restart("any");
    g_assert_true(logged("Nothing playing to the AirPods"));
    g_assert_cmpstr(no_output, ==, "");

    setup(SINKS, PAUSED_ONLY, false);
    g_autofree char *paused = restart("streams");
    g_assert_true(logged("Nothing playing to the AirPods"));
    g_assert_cmpstr(paused, ==, "");
}

/* The output itself: asked for, or when no stream plays ("any") */
static void test_output(void)
{
    setup(SINKS, INPUTS, false);
    g_autofree char *asked = restart("output");
    g_assert_true(logged("Restarted"));
    g_assert_cmpstr(asked, ==, "suspend-sink 7 1\nsuspend-sink 7 0\n");

    setup(SINKS, PAUSED_ONLY, false);
    g_autofree char *nothing_playing = restart("any");
    g_assert_true(logged("Restarted"));
    g_assert_cmpstr(nothing_playing, ==, "suspend-sink 7 1\nsuspend-sink 7 0\n");
}

/* No muted output to go through: given up, streams left alone */
static void test_suspend_failure_cleanup(void)
{
    setup(SINKS, INPUTS, false);
    write_file("fail-suspend", "");
    g_autofree char *actions = restart("streams");
    g_assert_true(logged("Could not restart"));
    g_assert_cmpstr(actions, ==, "suspend-sink 7 1\nsuspend-sink 7 0\n");
    g_autofree char *path = g_build_filename(dir, "fail-suspend", NULL);
    g_unlink(path);
}

static void test_hung_command_recovers(void)
{
    setup(SINKS, INPUTS, false);
    write_file("hang", "");
    gint64 started = g_get_monotonic_time();
    g_autofree char *failed = restart("streams");
    g_assert_true(logged("Could not restart"));
    g_assert_cmpint(g_get_monotonic_time() - started, <, G_USEC_PER_SEC);
    g_autofree char *path = g_build_filename(dir, "hang", NULL);
    g_unlink(path);
    setup(SINKS, INPUTS, false);
    g_autofree char *next = restart("streams");
    g_assert_true(logged("Restarted"));
}

static void test_cancel_cleans_suspended_output(void)
{
    setup(SINKS, INPUTS, false);
    audio_route_restart(AIRPODS, "streams");
    gint64 end = g_get_monotonic_time() + G_USEC_PER_SEC;
    g_autofree char *path = g_build_filename(dir, "log", NULL);
    while (g_get_monotonic_time() < end) {
        char *text = NULL;
        g_file_get_contents(path, &text, NULL, NULL);
        bool suspended = text && strstr(text, "suspend-sink 7 1");
        g_free(text);
        if (suspended) break;
        g_main_context_iteration(NULL, FALSE);
    }
    g_assert_true(audio_route_cancel());
    while (!logged("Audio repair cancelled") && g_get_monotonic_time() < end)
        g_main_context_iteration(NULL, FALSE);
    g_assert_true(logged("Audio repair cancelled"));
    char *actions = NULL;
    g_file_get_contents(path, &actions, NULL, NULL);
    g_assert_nonnull(strstr(actions, "suspend-sink 7 0"));
    g_free(actions);
}

/* One at a time; no address, nothing */
static void test_one_at_a_time(void)
{
    setup(SINKS, INPUTS, false);
    audio_route_restart(NULL, "streams");
    g_assert_cmpuint(messages->len, ==, 0);

    audio_route_restart(AIRPODS, "streams");
    g_autofree char *actions = restart("output");
    g_assert_cmpstr(actions, ==, "suspend-sink 7 1\nsuspend-sink 7 0\n");
    guint starts = 0;
    for (guint i = 0; i < messages->len; i++)
        if (g_str_has_prefix(messages->pdata[i], "Restarting the sound"))
            starts++;
    g_assert_cmpuint(starts, ==, 1);
}

/* Killing the backend must kill its direct pactl leaf even without cleanup. */
static void test_backend_death_kills_command(void)
{
    setup(SINKS, INPUTS, false);
    write_file("hang", "");
    g_autofree char *pid_file = g_build_filename(dir, "child-pid", NULL);
    g_unlink(pid_file);
    g_assert_cmpint(prctl(PR_SET_CHILD_SUBREAPER, 1), ==, 0);
    g_autofree char *self = g_file_read_link("/proc/self/exe", NULL);
    GSubprocessLauncher *launcher = g_subprocess_launcher_new(G_SUBPROCESS_FLAGS_STDOUT_SILENCE |
        G_SUBPROCESS_FLAGS_STDERR_SILENCE);
    g_subprocess_launcher_setenv(launcher, "FAKE_REPAIR_LONG_TIMEOUT", "1", TRUE);
    GSubprocess *backend = g_subprocess_launcher_spawn(launcher, NULL, self, "--parent-death-fixture", NULL);
    g_object_unref(launcher);
    g_assert_nonnull(backend);
    char *text = NULL;
    gint64 end = g_get_monotonic_time() + 2 * G_USEC_PER_SEC;
    while (!g_file_get_contents(pid_file, &text, NULL, NULL) && g_get_monotonic_time() < end)
        g_usleep(1000);
    pid_t command = text ? (pid_t)g_ascii_strtoll(text, NULL, 10) : 0;
    g_free(text);
    g_subprocess_force_exit(backend);
    g_assert_true(g_subprocess_wait(backend, NULL, NULL));
    g_object_unref(backend);
    g_assert_cmpint(command, >, 1);
    int status = 0;
    pid_t reaped = 0;
    end = g_get_monotonic_time() + G_USEC_PER_SEC;
    while ((reaped = waitpid(command, &status, WNOHANG)) == 0 && g_get_monotonic_time() < end)
        g_usleep(1000);
    if (reaped == 0) {  /* Reap on failure too, rather than strand a fixture. */
        kill(command, SIGKILL);
        waitpid(command, NULL, 0);
    }
    g_assert_cmpint(prctl(PR_SET_CHILD_SUBREAPER, 0), ==, 0);
    g_autofree char *hang = g_build_filename(dir, "hang", NULL);
    g_unlink(hang);
    g_assert_cmpint(reaped, ==, command);
    g_assert_true(WIFSIGNALED(status));
    g_assert_cmpint(WTERMSIG(status), ==, SIGKILL);
}

int main(int argc, char **argv)
{
    if (argc == 2 && g_strcmp0(argv[1], "--parent-death-fixture") == 0) {
        audio_route_restart(AIRPODS, "streams");
        g_main_loop_run(g_main_loop_new(NULL, FALSE));
        return 1;
    }
    g_test_init(&argc, &argv, NULL);
    messages = g_ptr_array_new_with_free_func(g_free);
    g_log_set_handler(NULL, G_LOG_LEVEL_MESSAGE | G_LOG_LEVEL_WARNING, log_handler, NULL);

    dir = g_dir_make_tmp("earport-audio-route-XXXXXX", NULL);
    g_assert_nonnull(dir);
    write_file("pactl", FAKE_PACTL);
    write_file("sleep", "#!/bin/sh\n");
    g_autofree char *pactl = g_build_filename(dir, "pactl", NULL);
    g_autofree char *sleep = g_build_filename(dir, "sleep", NULL);
    g_assert_cmpint(g_chmod(pactl, 0755), ==, 0);
    g_assert_cmpint(g_chmod(sleep, 0755), ==, 0);
    g_autofree char *path = g_strdup_printf("%s:%s", dir, g_getenv("PATH"));
    g_setenv("PATH", path, TRUE);
    g_setenv("FAKE_PACTL_DIR", dir, TRUE);
    g_setenv("FAKE_PACTL_PATH", pactl, TRUE);

    g_test_add_func("/audio-route/streams", test_streams);
    g_test_add_func("/audio-route/nothing-playing", test_nothing_playing);
    g_test_add_func("/audio-route/output", test_output);
    g_test_add_func("/audio-route/suspend-failure-cleanup", test_suspend_failure_cleanup);
    g_test_add_func("/audio-route/hung-command-recovers", test_hung_command_recovers);
    g_test_add_func("/audio-route/cancel-cleans-output", test_cancel_cleans_suspended_output);
    g_test_add_func("/audio-route/one-at-a-time", test_one_at_a_time);
    g_test_add_func("/audio-route/backend-death-kills-command", test_backend_death_kills_command);
    int ret = g_test_run();

    const char *files[] = { "pactl", "sleep", "sinks", "inputs", "log", "fail-load", "child-pid" };
    for (gsize i = 0; i < G_N_ELEMENTS(files); i++) {
        g_autofree char *file = g_build_filename(dir, files[i], NULL);
        g_unlink(file);
    }
    g_rmdir(dir);
    g_free(dir);
    g_ptr_array_unref(messages);
    return ret;
}
