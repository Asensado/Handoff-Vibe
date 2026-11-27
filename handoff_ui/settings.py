# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Normalize persisted preferences at the untrusted JSON boundary."""
def normalize_settings(value):
    data = dict(value) if isinstance(value, dict) else {}
    for key, default in [('auto_connect', False), ('check_updates', True), ('multiple_devices', False)]:
        if type(data.get(key)) is not bool:
            data[key] = default
    # Release gate: automatic connection awaits hardware validation (#17).
    data['auto_connect'] = False
    mode = data.get('ear_pause_mode')
    data['ear_pause_mode'] = mode if type(mode) is int and mode in (0, 1, 2) else 1
    data['apple_handoff'] = True
    return data
