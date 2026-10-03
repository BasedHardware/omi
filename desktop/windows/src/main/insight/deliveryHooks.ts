/** Main-process callbacks; never serialized over IPC. */
export type ToastDeliveryHooks = {
  isCurrent: () => boolean
  onPresented: () => void
  onOpened: () => void
  onDismissed: (reason: 'dismissed' | 'timeout') => void
}
