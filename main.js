// main.js — robust backend launcher
const { app, BrowserWindow, ipcMain, dialog } = require('electron');   // ⮑ dialog added
const path     = require('path');
const { spawn } = require('child_process');
const fs       = require('fs');
const keytar   = require('keytar');
const waitOn   = require('wait-on');

const SERVICE = 'ProductivityBoss';
const ACCOUNT = 'openai_api_key';

let pyProc = null;

/* ───────────────── window ───────────────── */
function createWindow () {
  const win = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.loadFile(path.join(__dirname, 'frontend', 'index.html'));
  // win.webContents.openDevTools();
}

/* ───────────── secure-key helpers ───────── */
ipcMain.handle('key-save', async (_e, key) => {
  if (!key) return false;
  await keytar.setPassword(SERVICE, ACCOUNT, key);
  return true;
});
ipcMain.handle('key-read', async () => keytar.getPassword(SERVICE, ACCOUNT));

/* ─────────────── backend spawn ──────────── */
async function startBackend () {
  const exe = process.platform === 'win32' ? 'server.exe' : 'server';
  const distPath = path.join(__dirname, 'backend', 'dist', exe);

  const apiKey = await keytar.getPassword(SERVICE, ACCOUNT) || '';
  const env    = { ...process.env, OPENAI_API_KEY: apiKey };

  let cmd, args;
  if (fs.existsSync(distPath)) {
    cmd  = distPath;
    args = [];
  } else {
    cmd  = process.platform === 'win32' ? 'python' : 'python3';
    args = [path.join(__dirname, 'backend', 'server.py')];
    console.log('[dev] launching backend via', cmd, args.join(' '));
  }

  pyProc = spawn(cmd, args, { env, stdio: ['ignore', 'inherit', 'inherit'] });

  pyProc.once('exit', code => {
    if (code !== 0) {
      console.error(`Backend exited with code ${code}`);
      dialog.showErrorBox('Backend failed', 'Python backend terminated unexpectedly.');
      app.quit();
    }
  });
}

/* ───────────── app lifecycle ────────────── */
app.whenReady().then(async () => {
  await startBackend();

  try {
    // ⮑ 30 s total, poll every 250 ms, 1 s connect window
    await waitOn({
      resources: ['tcp:127.0.0.1:5000'],
      timeout: 30000,
      interval: 250,
      tcpTimeout: 1000,
      window: 0
    });
  } catch (err) {
    console.error('wait-on timeout:', err.message);

    const { response } = await dialog.showMessageBox({
      type: 'error',
      buttons: ['Retry', 'Quit'],
      defaultId: 0,
      cancelId: 1,
      title: 'Backend not ready',
      message:
        'Flask did not start within 30 seconds.\n' +
        'If this is the first run, dependencies can take a while.\n' +
        'Retry or quit?'
    });

    if (response === 0) {
      app.relaunch();
      return app.exit(0);
    }
    return app.quit();
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('before-quit', () => {
  if (pyProc) {
    try { pyProc.kill(); } catch { /* ignore */ }
  }
});
