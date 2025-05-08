const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let pyProc = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  // Load the frontend GUI from index.html
  win.loadFile(path.join(__dirname, 'frontend', 'index.html'));

  // Optional: Open DevTools for debugging (comment out in production)
  // win.webContents.openDevTools();
}

function shouldAutoLaunch() {
  // Determine if app should auto-start at login (based on user preference)
  try {
    const prefsPath = path.join(__dirname, 'backend', 'data', 'prefs.json');
    if (fs.existsSync(prefsPath)) {
      const prefs = JSON.parse(fs.readFileSync(prefsPath, 'utf-8'));
      if (prefs.hasOwnProperty('auto_launch')) {
        return prefs.auto_launch;
      }
    }
  } catch (err) {
    console.error('Error reading prefs.json:', err);
  }
  // Default: auto-launch enabled
  return true;
}

// Start the Python backend server and then the Electron app
app.whenReady().then(() => {
  // Spawn the Python backend (ensure that Python is installed and in PATH)
  const script = path.join(__dirname, 'backend', 'server.py');
  pyProc = spawn('python', [script], { stdio: 'inherit' });
  pyProc.on('error', (error) => {
    console.error('Failed to start Python backend:', error);
  });

  // Create the browser window for the frontend
  createWindow();

  // Set application to launch at login (Windows & macOS; Linux requires manual setup)
  if (shouldAutoLaunch() && (process.platform === 'win32' || process.platform === 'darwin')) {
    app.setLoginItemSettings({ openAtLogin: true });
  }

  app.on('activate', () => {
    // On macOS, re-create a window when the dock icon is clicked and there are no open windows
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows are closed (except on macOS, where it's common to stay active until explicit quit)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Ensure the Python process is terminated when the app quits
app.on('before-quit', () => {
  if (pyProc) {
    try {
      pyProc.kill();
    } catch (err) {
      console.error('Error terminating Python process:', err);
    }
  }
});
