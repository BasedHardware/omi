/**
 * Connection-balance mapping.
 * Mobile disconnects are Device Disconnected Detailed.
 * macOS disconnects are Device Disconnected.
 * Device Connected is the connect side for both.
 * Unique people and reconnection volume are separate numbers.
 */

export type ConnectionSurface = "mobile" | "macos";

export const CONNECTION_EVENTS = {
  mobile: {
    connected: "Device Connected",
    disconnected: "Device Disconnected Detailed",
  },
  macos: {
    connected: "Device Connected",
    disconnected: "Device Disconnected",
  },
} as const;

export interface ConnectionObservation {
  event: string;
  personId: string;
  /** ios and android are the mobile surface. macos is its own surface. */
  platform: "ios" | "android" | "macos";
}

export interface ConnectionBalance {
  surface: ConnectionSurface;
  connectedEvent: string;
  disconnectedEvent: string;
  uniquePeopleConnected: number;
  uniquePeopleDisconnected: number;
  /** Unique connected people / unique disconnected people. Null when the denominator is 0. */
  uniquePeopleRatio: number | null;
  connectVolume: number;
  /** Disconnect event count. One person reconnecting many times counts many times. */
  reconnectVolume: number;
}

function surfaceOf(
  platform: ConnectionObservation["platform"]
): ConnectionSurface {
  return platform === "macos" ? "macos" : "mobile";
}

export function connectionBalance(
  observations: ConnectionObservation[],
  surface: ConnectionSurface
): ConnectionBalance {
  const events = CONNECTION_EVENTS[surface];
  const connectedPeople = new Set<string>();
  const disconnectedPeople = new Set<string>();
  let connectVolume = 0;
  let reconnectVolume = 0;
  for (const observation of observations) {
    if (surfaceOf(observation.platform) !== surface) continue;
    if (!observation.personId) continue;
    if (observation.event === events.connected) {
      connectedPeople.add(observation.personId);
      connectVolume += 1;
    } else if (observation.event === events.disconnected) {
      disconnectedPeople.add(observation.personId);
      reconnectVolume += 1;
    }
  }
  const uniquePeopleConnected = connectedPeople.size;
  const uniquePeopleDisconnected = disconnectedPeople.size;
  return {
    surface,
    connectedEvent: events.connected,
    disconnectedEvent: events.disconnected,
    uniquePeopleConnected,
    uniquePeopleDisconnected,
    uniquePeopleRatio:
      uniquePeopleDisconnected > 0
        ? Math.round(
            (uniquePeopleConnected / uniquePeopleDisconnected) * 1000
          ) / 1000
        : null,
    connectVolume,
    reconnectVolume,
  };
}
