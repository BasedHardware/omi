import type { WindowsUpdateChannel } from './windowsUpdateFeed'

// Pure mapping between the persisted "receive beta updates" opt-in and the
// backend-owned Windows release channel. The release workflow marks beta builds
// with GitHub's prerelease flag while their app version stays plain semver, so
// the backend is the authority that maps that flag to beta/stable.

export function betaOptInToUpdateChannel(optIn: boolean): WindowsUpdateChannel {
  return optIn === true ? 'beta' : 'stable'
}

/** Ignore unrelated app-settings writes and re-check only on a real channel move. */
export function resolveBetaChannelChange(
  currentChannel: WindowsUpdateChannel,
  nextOptIn: boolean
): { channel: WindowsUpdateChannel; changed: boolean } {
  const channel = betaOptInToUpdateChannel(nextOptIn)
  return { channel, changed: channel !== currentChannel }
}
