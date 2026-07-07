import { ElectronAPI } from '@electron-toolkit/preload'
import type { OmiBridgeApi, OmiOverlayApi } from '../shared/types'

declare global {
  interface Window {
    electron: ElectronAPI
    omi: OmiBridgeApi
    omiOverlay: OmiOverlayApi
  }
}
