import { ElectronAPI } from '@electron-toolkit/preload'
import type { OmiBridgeApi, OmiOverlayApi, OmiBarApi } from '../shared/types'

declare global {
  interface Window {
    electron: ElectronAPI
    omi: OmiBridgeApi
    omiOverlay: OmiOverlayApi
    omiBar: OmiBarApi
  }
}
