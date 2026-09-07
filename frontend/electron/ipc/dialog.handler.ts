import { ipcMain, dialog, BrowserWindow } from 'electron'
import { IPC_CHANNELS } from '../types'

export function registerDialogHandlers(getMainWindow: () => BrowserWindow | null): void {
  ipcMain.handle(IPC_CHANNELS.DIALOG_OPEN_FILE, async () => {
    const win = getMainWindow()
    if (!win) throw new Error('No main window available.')
    const res = await dialog.showOpenDialog(win, {
      properties: ['openFile'],
      filters: [{ name: '文本文件', extensions: ['txt'] }],
    })
    if (res.canceled || !res.filePaths.length) return null
    return res.filePaths[0]
  })
}
