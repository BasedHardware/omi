/// Pure native-custody gate shared by the live Listen host and conformance.
/// A page cannot mint this decision; the host supplies the checked values.
bool listenPreflightCanOpen(Map<Object?, Object?> payload) =>
    payload['permission'] == 'granted' && payload['deviceState'] == 'available';
