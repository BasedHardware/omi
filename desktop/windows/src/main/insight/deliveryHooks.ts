/** Main-process callbacks; never serialized over IPC. */
export type ToastDeliveryHooks = {
  isCurrent: () => boolean
  onPresented: () => void
  onFeedback?: (action: 'thumbs_up' | 'thumbs_down') => void
  onOpened: () => void
  onDismissed: (reason: 'dismissed' | 'timeout') => void
}
