// Pure status reduction, shared by the Shell indicator and its unit checks.
export function statusFor(config, service, protocol, now) {
    if (config?.cli_mode)
        return ['CLI mode', '#c0bfbc'];
    if (!config?.selected)
        return ['Not set up', '#c0bfbc'];
    if (service === 'failed')
        return ['Error', '#f66151'];
    if (service === 'inactive')
        return ['Paused', '#c0bfbc'];
    if (service === 'unavailable')
        return ['Unavailable', '#f8e45c'];
    const fresh = protocol && now - protocol.updated >= 0 && now - protocol.updated < 20;
    if (fresh && protocol.ready)
        return protocol.switching ? ['Switching', '#62a0ea'] : ['Active', '#57e389'];
    if (fresh && protocol.error)
        return ['Error', '#f66151'];
    return ['Waiting', '#f8e45c'];
}
