/// What the built-in server says about itself, in one place because the card
/// and its sheet have to agree.
///
/// None of it names the loopback endpoint. The address is an implementation
/// detail of how Omi reaches its own tools, and printing it on a card reads as
/// an invitation to point something else at it.
enum CuaControlCopy {
  /// The card's detail line, where every other server prints its endpoint.
  static let cardDetail =
    "Let Omi see your screen and work your Mac — reading what is on screen, clicking, and typing."

  /// The sheet's description, under the switch.
  static let description =
    """
    Omi can look at your screen, find controls in your apps, and click and type \
    for you, so it can finish a task instead of describing one. Everything runs \
    on this Mac and stays under the permissions you grant below. Turn it off \
    here at any time.
    """
}
