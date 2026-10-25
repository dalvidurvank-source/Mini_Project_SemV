import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import { randomUUID } from 'node:crypto';

const frontend = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(frontend, '..');
const python = process.env.AGROLINK_TEST_PYTHON || path.join(root, '.venv-local', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const appDb=path.join(os.tmpdir(),`agrolink-e2e-${randomUUID()}.sqlite3`);

export default defineConfig({
  testDir:'./tests', timeout:120000, expect:{timeout:90000}, workers:1,
  metadata:{appDb},globalTeardown:'./tests/cleanup.js',
  reporter:'list', use:{baseURL:'http://127.0.0.1:15173', channel:'chrome', headless:true, trace:'retain-on-failure'},
  webServer:[
    {command:`"${python}" -B -m backend.server`, cwd:root, env:{AGROLINK_PORT:'18080',
      AGROLINK_APP_DB:appDb,AGROLINK_FRONTEND_ORIGIN:'http://127.0.0.1:15173',
      AGROLINK_BUYERS_FILE:path.join(root,'backend/test_fixtures/buyer_offers.demo.json')},
     url:'http://127.0.0.1:18080/api/health', timeout:30000, reuseExistingServer:false, stdout:'ignore', stderr:'ignore'},
    {command:'npm run dev -- --port 15173 --strictPort', cwd:frontend,
     env:{AGROLINK_API_TARGET:'http://127.0.0.1:18080'}, url:'http://127.0.0.1:15173',
     timeout:30000, reuseExistingServer:false, stdout:'ignore', stderr:'ignore'}
  ]
});
