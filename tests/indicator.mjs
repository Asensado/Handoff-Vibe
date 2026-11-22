import assert from 'node:assert/strict';
import fs from 'node:fs';
// Load the pure ES module independently of GNOME Shell for deterministic checks.
const code = fs.readFileSync(new URL('../gnome-extension/state.js', import.meta.url), 'utf8');
const {statusFor} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const config = {selected:'AA:BB:CC:DD:EE:FF'};
const ready = {updated:990,ready:true};
assert.equal(statusFor(config,'active',ready,1000)[0],'Active');
assert.equal(statusFor(config,'active',{...ready,switching:true},1000)[0],'Switching');
assert.equal(statusFor(config,'inactive',ready,1000)[0],'Paused');
assert.equal(statusFor(config,'failed',ready,1000)[0],'Error');
assert.equal(statusFor(config,'unavailable',null,1000)[0],'Unavailable');
assert.equal(statusFor(config,'active',{...ready,updated:900},1000)[0],'Waiting');
assert.equal(statusFor(config,'active',{...ready,updated:1100},1000)[0],'Waiting');
assert.equal(statusFor(config,'active',{updated:999,ready:false,error:'Unavailable'},1000)[0],'Error');
assert.equal(statusFor({...config,cli_mode:true},'active',ready,1000)[0],'CLI mode');
assert.equal(statusFor(null,'active',ready,1000)[0],'Not set up');
console.log('10 indicator status checks passed.');
