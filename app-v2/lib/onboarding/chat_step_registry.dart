import 'dart:io' show Platform;

import 'package:flutter/material.dart';

import 'package:nooto_v2/companion/companion_signals.dart';
import 'package:nooto_v2/onboarding/widgets/acknowledge_turn.dart';
import 'package:nooto_v2/onboarding/widgets/chip_widget_turn.dart';
import 'package:nooto_v2/onboarding/widgets/device_pairing_turn.dart';
import 'package:nooto_v2/onboarding/widgets/permission_widget_turn.dart';
import 'package:nooto_v2/onboarding/widgets/speech_profile_turn.dart';
import 'package:nooto_v2/onboarding/widgets/text_input_turn.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';

/// Maps a chip step's captured id to a human label for display.
String resolveChipLabel(OnboardingStepId stepId, String id) {
  if (stepId == OnboardingStepId.language) {
    return kLanguageLabelById[id] ?? id;
  }
  return id;
}

enum OnboardingStepId {
  name,
  language,
  microphone,
  notifications,
  backgroundActivity,
  location,
  device,
  speechProfile,
  acknowledge,
}

class ChatStepDef {
  final OnboardingStepId id;
  final bool acceptsTypedAnswer;
  final bool skippable;
  final bool Function() includeForPlatform;
  final String Function(BuildContext context, CompanionSignals signals) fallbackOpener;
  final Widget Function(BuildContext context, String turnId) widgetBuilder;
  final String Function(BuildContext context, dynamic capturedValue) summarize;

  const ChatStepDef({
    required this.id,
    required this.acceptsTypedAnswer,
    required this.skippable,
    required this.includeForPlatform,
    required this.fallbackOpener,
    required this.widgetBuilder,
    required this.summarize,
  });
}

bool _allPlatforms() => true;
bool _androidOnly() => Platform.isAndroid;

List<ChatStepDef> registryForCurrentPlatform() => _registry.where((s) => s.includeForPlatform()).toList();

const _registry = <ChatStepDef>[
  ChatStepDef(
    id: OnboardingStepId.name,
    acceptsTypedAnswer: true,
    skippable: false,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerName,
    widgetBuilder: _buildText,
    summarize: _summarizeText,
  ),
  ChatStepDef(
    id: OnboardingStepId.language,
    acceptsTypedAnswer: false,
    skippable: false,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerLanguage,
    widgetBuilder: _buildLanguageChips,
    summarize: _summarizeLanguage,
  ),
  ChatStepDef(
    id: OnboardingStepId.microphone,
    acceptsTypedAnswer: false,
    skippable: false,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerMicrophone,
    widgetBuilder: _buildMicrophonePermission,
    summarize: _summarizePermission,
  ),
  ChatStepDef(
    id: OnboardingStepId.notifications,
    acceptsTypedAnswer: false,
    skippable: false,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerNotifications,
    widgetBuilder: _buildNotificationsPermission,
    summarize: _summarizePermission,
  ),
  ChatStepDef(
    id: OnboardingStepId.backgroundActivity,
    acceptsTypedAnswer: false,
    skippable: true,
    includeForPlatform: _androidOnly,
    fallbackOpener: _openerBackground,
    widgetBuilder: _buildBackgroundPermission,
    summarize: _summarizePermission,
  ),
  ChatStepDef(
    id: OnboardingStepId.location,
    acceptsTypedAnswer: false,
    skippable: true,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerLocation,
    widgetBuilder: _buildLocationPermission,
    summarize: _summarizePermission,
  ),
  ChatStepDef(
    id: OnboardingStepId.device,
    acceptsTypedAnswer: false,
    skippable: true,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerDevice,
    widgetBuilder: _buildDevicePairing,
    summarize: _summarizeChip,
  ),
  ChatStepDef(
    id: OnboardingStepId.speechProfile,
    acceptsTypedAnswer: false,
    skippable: true,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerSpeechProfile,
    widgetBuilder: _buildSpeechProfile,
    summarize: _summarizeSpeechProfile,
  ),
  ChatStepDef(
    id: OnboardingStepId.acknowledge,
    acceptsTypedAnswer: false,
    skippable: false,
    includeForPlatform: _allPlatforms,
    fallbackOpener: _openerAcknowledge,
    widgetBuilder: _buildAcknowledge,
    summarize: _summarizeAck,
  ),
];

// Openers
String _openerName(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerName;
String _openerLanguage(BuildContext c, CompanionSignals s) =>
    AppLocalizations.of(c).onboardingOpenerLanguage(s.preferredName ?? '');
String _openerMicrophone(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerMicrophone;
String _openerNotifications(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerNotifications;
String _openerBackground(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerBackground;
String _openerLocation(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerLocation;
String _openerDevice(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerDevice;
String _openerSpeechProfile(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerSpeechProfile;
String _openerAcknowledge(BuildContext c, CompanionSignals s) => AppLocalizations.of(c).onboardingOpenerAcknowledge;

// Widget builders
Widget _buildText(BuildContext c, String turnId) => TextInputTurn(turnId: turnId);
Widget _buildLanguageChips(BuildContext c, String turnId) => LanguageChipsTurn(turnId: turnId);
Widget _buildMicrophonePermission(BuildContext c, String turnId) =>
    PermissionWidgetTurn(turnId: turnId, kind: PermissionKind.microphone);
Widget _buildNotificationsPermission(BuildContext c, String turnId) =>
    PermissionWidgetTurn(turnId: turnId, kind: PermissionKind.notifications);
Widget _buildBackgroundPermission(BuildContext c, String turnId) =>
    PermissionWidgetTurn(turnId: turnId, kind: PermissionKind.backgroundActivity);
Widget _buildLocationPermission(BuildContext c, String turnId) =>
    PermissionWidgetTurn(turnId: turnId, kind: PermissionKind.location);
Widget _buildDevicePairing(BuildContext c, String turnId) => DevicePairingTurn(turnId: turnId);
Widget _buildSpeechProfile(BuildContext c, String turnId) => SpeechProfileTurn(turnId: turnId);
Widget _buildAcknowledge(BuildContext c, String turnId) => AcknowledgeTurn(turnId: turnId);

// Summaries
String _summarizeText(BuildContext c, dynamic v) => v is String ? v : '';
String _summarizeChip(BuildContext c, dynamic v) => v is String ? v : '';
String _summarizeLanguage(BuildContext c, dynamic v) =>
    v is String ? (kLanguageLabelById[v] ?? v) : '';
String _summarizePermission(BuildContext c, dynamic v) {
  final l = AppLocalizations.of(c);
  if (v == 'granted') return l.onboardingPermissionGranted;
  if (v == 'denied') return l.onboardingPermissionDenied;
  return l.onboardingSkipped;
}

String _summarizeSpeechProfile(BuildContext c, dynamic v) {
  final l = AppLocalizations.of(c);
  if (v == true) return l.onboardingSpeechCaptured;
  return l.onboardingSkipped;
}

String _summarizeAck(BuildContext c, dynamic v) => AppLocalizations.of(c).onboardingAckLetsGo;
