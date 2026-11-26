import assert from 'node:assert/strict';
import fs from 'node:fs';
// Load the pure ES module independently of GNOME Shell for deterministic checks.
const code = fs.readFileSync(new URL('../gnome-extension/state.js', import.meta.url), 'utf8');
const {statusFor, protocolFromProperties, unpack} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const config = {selected:'AA:BB:CC:DD:EE:FF'};
const ready = {updated:990,ready:true};
assert.equal(statusFor(config,'active',ready,1000)[0],'Active');
assert.equal(statusFor(config,'active',{...ready,switching:true},1000)[0],'Switching');
assert.equal(statusFor(config,'inactive',ready,1000)[0],'Paused');
assert.equal(statusFor(config,'failed',ready,1000)[0],'Error');
assert.equal(statusFor(config,'unavailable',null,1000)[0],'Unavailable');
assert.equal(statusFor(config,'active',{...ready,updated:900},1000)[0],'Waiting');
assert.equal(statusFor(config,'active',{...ready,updated:1100},1000)[0],'Waiting');
assert.equal(statusFor(config,'active',{updated:999,ready:false,error:'Unavailable'},1000)[0],'Disconnected');
assert.equal(statusFor({...config,cli_mode:true},'active',ready,1000)[0],'CLI mode');
assert.equal(statusFor(null,'active',ready,1000)[0],'Not set up');
assert.equal(statusFor(config,'active',{...ready,owner:'other'},1000)[0],'Handoff');
assert.equal(statusFor(config,'active',{...ready,owner:'other',switching_until:1002},1000)[0],'Switching');
assert.equal(statusFor(config,'active',{...ready,owner:'other',switching_until:999},1000)[0],'Handoff');
assert.equal(statusFor(config,'active',{updated:999,ready:false,error:''},1000)[0],'Disconnected');
const remote = protocolFromProperties(config, {
    Connected:true, DeviceAddress:config.selected.toLowerCase(), AudioSource:'other',
    SupportsANC:true, NoiseControlMode:'transparency', BatteryLeft:78, BatteryRight:77,
},1000);
assert.equal(statusFor(config,'active',remote,1000)[0],'Handoff');
assert.equal(statusFor(config,'unavailable',remote,1000)[0],'Handoff');
assert.equal(remote.controls_ready,true);
assert.equal(remote.battery_left,78);
assert.equal(remote.battery_case,-1);
assert.equal(remote.noise_control,'transparency');
assert.equal(protocolFromProperties(config,{Connected:true,DeviceAddress:'11:22:33:44:55:66'},1000),null);
assert.equal(protocolFromProperties({...config,cli_mode:true},{},1000),null);
assert.equal(statusFor(config,'active',protocolFromProperties(config,{Connected:false},1000),1000)[0],'Disconnected');
assert.deepEqual(unpack({deepUnpack:()=>[{deepUnpack:()=> 'active'}]}),['active']);
assert.deepEqual(unpack({NearbyBattery:{deepUnpack:()=>({Left:{deepUnpack:()=>78}})}}),{NearbyBattery:{Left:78}});
console.log('25 indicator and live D-Bus state checks passed.');
