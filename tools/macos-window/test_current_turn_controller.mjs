import {pump} from './current_turn_controller.mjs';
import * as fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
import os from 'node:os';
const base=await fs.mkdtemp(path.join(os.tmpdir(),'current-turn-controller-'));
await fs.mkdir(base,{recursive:true});
async function test(op,p,app={},extra={}) {
 const root=await fs.mkdtemp(base+'/case-');
 try {
  await fs.writeFile(root+'/request.json',JSON.stringify({protocol:1,id:1,operation:op,parameters:p,expires_unix:Date.now()/1000+5,...extra}));
  await pump({root,app,appPath:'/test/WOS.app',allowedRoot:base,milliseconds:30});
  return JSON.parse(await fs.readFile(root+'/response.json','utf8'));
 } finally {await fs.rm(root,{recursive:true,force:true});}
}
let count=0;
assert.equal((await test('click',{point:[12,34]},{click:async p=>{assert.deepEqual(p,[12,34]);count++},getAXState:async()=>''})).ok,true);
assert.equal(count,1);
assert.equal((await test('eval',{code:'throw 1'})).ok,false);
assert.equal((await test('click',{point:[1,2]},{},{expires_unix:0})).ok,false);
assert.equal((await test('bind',{app_path:'/other/app'})).ok,false);
assert.equal((await test('key',{key:'super+q',count:1,duration_ms:100})).ok,false);
assert.equal((await test('observe',{}, {getAXStateAndScreenshot:async()=>({})})).ok,false);
assert.equal((await test('click',{point:[1,2]},{click:async()=>{throw Error('platform denied')}})).ok,false);
console.log('7 controller tests passed; no real UI used');
await fs.rmdir(base);
