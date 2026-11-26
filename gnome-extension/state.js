// SPDX-License-Identifier: GPL-3.0-or-later
// Pure status reduction, shared by the Shell indicator and its unit checks.
export function unpack(value) {
    if (value && typeof value.deepUnpack === 'function')
        return unpack(value.deepUnpack());
    if (Array.isArray(value))
        return value.map(unpack);
    if (value && typeof value === 'object')
        return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, unpack(item)]));
    return value;
}

// The live control service is the source of truth when available. In
// particular, "other" means Handoff even when systemd polling lags behind.
export function protocolFromProperties(config, properties, now) {
    if (!config?.selected || config.cli_mode)
        return null;
    const p = unpack(properties);
    if (p.Connected && String(p.DeviceAddress || '').toUpperCase() !== config.selected.toUpperCase())
        return null;
    return {
        updated: now,
        ready: p.Connected === true,
        switching: p.Reconnecting === true,
        owner: p.AudioSource === 'computer' ? 'linux' : p.AudioSource || '',
        controls_ready: p.Connected === true && p.SupportsANC === true,
        noise_control: p.NoiseControlMode || '',
        supports_adaptive: p.SupportsAdaptive === true,
        battery_left: p.BatteryLeft ?? -1,
        battery_right: p.BatteryRight ?? -1,
        battery_case: p.BatteryCase ?? -1,
        charging_left: p.ChargingLeft === true,
        charging_right: p.ChargingRight === true,
        charging_case: p.ChargingCase === true,
        listening_minutes: p.ListeningTimeRemaining ?? -1,
        nearby: p.NearbyBattery || {},
    };
}

export function statusFor(config, service, protocol, now) {
    if (config?.cli_mode)
        return ['CLI mode', '#c0bfbc'];
    if (!config?.selected)
        return ['Not set up', '#c0bfbc'];
    if (service === 'failed')
        return ['Error', '#f66151'];
    if (service === 'inactive')
        return ['Paused', '#c0bfbc'];
    const fresh = protocol && now - protocol.updated >= 0 && now - protocol.updated < 20;
    if (fresh && (protocol.switching || protocol.switching_until > now))
        return ['Switching', '#62a0ea'];
    if (fresh && protocol.ready)
        return protocol.owner === 'other' ? ['Handoff', '#62a0ea'] : ['Active', '#57e389'];
    if (fresh)
        return ['Disconnected', '#c0bfbc'];
    if (service === 'unavailable')
        return ['Unavailable', '#f8e45c'];
    return ['Waiting', '#f8e45c'];
}
