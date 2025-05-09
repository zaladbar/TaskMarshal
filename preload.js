const { contextBridge, ipcRenderer } = require('electron');

/**
 * Secure bridge — renderer gets only these two async helpers.
 */
contextBridge.exposeInMainWorld('electronAPI', {
  saveOpenAIKey: key => ipcRenderer.invoke('key-save', key),
  readOpenAIKey: () => ipcRenderer.invoke('key-read')
});
