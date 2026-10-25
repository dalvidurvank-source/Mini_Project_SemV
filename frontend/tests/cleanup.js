import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

export default async function cleanup(config) {
  const target=path.resolve(config.metadata.appDb);
  if(path.dirname(target)!==path.resolve(os.tmpdir())||!path.basename(target).startsWith('agrolink-e2e-'))throw new Error('Unexpected test database path.');
  for(const suffix of ['', '-journal','-wal','-shm']) {
    try {fs.rmSync(target+suffix,{force:true});} catch(e) {if(e.code!=='EBUSY'&&e.code!=='EPERM')throw e;}
  }
}
