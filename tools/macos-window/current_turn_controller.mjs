// Runs only inside the active conversation's official cua_repl tool.
// Requests are typed data, never executable code. No credentials or unlock APIs.
import * as fs from 'node:fs/promises';
import path from 'node:path';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
export async function pump({root, app, appPath, allowedRoot, milliseconds = 12000}) {
  root = path.resolve(root);
  if (typeof allowedRoot !== 'string' || !root.startsWith(path.resolve(allowedRoot) + path.sep)) throw Error('Explicit private bridge parent required');
  if ((await fs.lstat(root)).isSymbolicLink()) throw Error('Symlink bridge rejected');
  const end = Date.now() + Math.min(milliseconds, 15000);
  const operations = [];
  const atomic = async (name, value) => {
    const dest = path.join(root, name);
    await fs.writeFile(dest + '.new', JSON.stringify(value), {mode:0o600});
    await fs.rename(dest + '.new', dest);
  };
  while (Date.now() < end) {
    for (const flag of ['closed.json', 'stopped.json']) {
      try { await fs.access(path.join(root, flag)); return {status:flag,operations}; }
      catch (e) { if (e.code !== 'ENOENT') throw e; }
    }
    const pending = path.join(root, 'request.json');
    let request;
    try {
      if ((await fs.lstat(pending)).isSymbolicLink()) throw Error('Symlink request rejected');
      request = JSON.parse(await fs.readFile(pending, 'utf8'));
    } catch (e) { if (e.code === 'ENOENT') { await pause(75); continue; } throw e; }
    // Claim BEFORE an input. An interrupted claim cannot be replayed.
    const claim = path.join(root, 'processing.json');
    try { await fs.access(claim); throw Error('Prior operation has unknown effect; stop'); }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
    await fs.rename(pending, claim);
    try {
      if (request.protocol !== 1 || !Number.isInteger(request.id) || request.id < 1 ||
          !Number.isFinite(request.expires_unix) || request.expires_unix * 1000 <= Date.now()) throw Error('Invalid or expired request');
      let completed = 0;
      try { completed = JSON.parse(await fs.readFile(path.join(root,'completed.json'),'utf8')).id; }
      catch(e) { if(e.code !== 'ENOENT') throw e; }
      if (request.id <= completed) throw Error('Repeated operation ID rejected');
      const p = request.parameters;
      if (!p || typeof p !== 'object') throw Error('Missing parameters');
      switch (request.operation) {
        case 'bind':
          if (p.app_path !== appPath) throw Error('App path differs from explicitly bound official app');
          break;
        case 'observe': {
          const view = await app.getAXStateAndScreenshot({emit:false});
          if (!view.screenshot?.length) throw Error('Official screenshot unavailable');
          await fs.writeFile(path.join(root, `frame-${request.id}.bin`), view.screenshot, {mode:0o600});
          break;
        }
        case 'click':
          if (!Array.isArray(p.point) || p.point.length !== 2 || !p.point.every(Number.isFinite) ||
              p.point.some(x => x < 0 || x > 10000)) throw Error('Invalid native point');
          await app.click(p.point);
          await app.getAXState({emit:false});
          break;
        case 'key':
          if (typeof p.key !== 'string' || !['Up','Down','Left','Right','Escape','Return','Tab','space'].includes(p.key) ||
              !Number.isInteger(p.count) || p.count !== 1 ||
              !Number.isInteger(p.duration_ms) || p.duration_ms < 1 || p.duration_ms > 2000) throw Error('Invalid typed key');
          // Check expiry and cancellation between individual inputs.
          for (let i = 0; i < p.count; i++) {
            if (request.expires_unix * 1000 <= Date.now()) throw Error('Key request expired mid-operation');
            try { await fs.access(path.join(root,'stopped.json')); throw Error('Client stopped'); }
            catch(e) { if(e.code !== 'ENOENT') throw e; }
            await app.pressKey(p.key, {durationMs:p.duration_ms});
            await app.getAXState({emit:false});
          }
          break;
        default: throw Error('Unknown operation; no code execution');
      }
      await atomic('completed.json', {id:request.id});
      await fs.unlink(claim);
      await atomic('response.json', {id:request.id,ok:true});
      operations.push({id:request.id,operation:request.operation});
    } catch (e) {
      await atomic('response.json', {id:request.id,ok:false,error:String(e)});
      await atomic('stopped.json', {id:request.id,error:String(e)});
      return {status:'stopped',error:String(e),operations};
    }
  }
  return {status:'yield',operations};
}
