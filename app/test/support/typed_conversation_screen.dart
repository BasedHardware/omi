import 'package:flutter/widgets.dart';
import 'package:omi/providers/conversation_provider.dart';

/// Builder-owned fixture composition only: supply inert explicit collaborators
/// around the real ConversationsPage and this exact real provider. Never replace
/// its build method, use an offstage decoy, or construct default CaptureProvider.
/// Include real MaterialApp localization delegates. Spine tests check actual page
/// ancestry and behavior; fixture wiring is deliberately editable by the builder.
Future<Widget> buildTypedConversationScreen(ConversationProvider provider) =>
    throw UnimplementedError('C3 real-page fixture composition');
