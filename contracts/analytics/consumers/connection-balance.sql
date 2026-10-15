-- Connection-balance presence check for the registered disconnect wires.
-- Mobile denominator: Device Disconnected Detailed.
-- macOS denominator: Device Disconnected.
-- Numerator for both surfaces: Device Connected.
-- This executable query proves the wire is present in one namespace and build.
-- It does not treat event count as unique people. Reconnect volume is a
-- separate count owned by the admin connection-balance reader.
SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Device Connected',
    'Device Disconnected',
    'Device Disconnected Detailed'
  )
GROUP BY event
ORDER BY event;
