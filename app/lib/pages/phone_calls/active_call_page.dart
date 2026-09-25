import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/models/audio_route.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/phone_calls/call_duration_format.dart';

class ActiveCallPage extends StatefulWidget {
  const ActiveCallPage({super.key});

  @override
  State<ActiveCallPage> createState() => _ActiveCallPageState();
}

class _ActiveCallPageState extends State<ActiveCallPage> {
  bool _popScheduled = false;
  PhoneCallProvider? _provider;

  @override
  void initState() {
    super.initState();
    _provider = context.read<PhoneCallProvider>();
    _provider!.addListener(_onProviderChanged);
  }

  @override
  void dispose() {
    _provider?.removeListener(_onProviderChanged);
    super.dispose();
  }

  void _onProviderChanged() {
    var state = _provider?.callState ?? PhoneCallState.idle;
    if ((state == PhoneCallState.ended || state == PhoneCallState.failed) && !_popScheduled) {
      _popScheduled = true;
      Future.delayed(const Duration(seconds: 2), () {
        if (mounted) {
          Navigator.of(context).pop();
        }
      });
    }
  }

  void _showDtmfDialpad(BuildContext context, PhoneCallProvider provider) {
    PlatformManager.instance.analytics.phoneCallDialpadOpened();
    showOmiSheet<void>(
      context: context,
      showCloseButton: false,
      builder: (_) => _DtmfDialpadSheet(
        onDigitPressed: (digit) {
          PlatformManager.instance.analytics.phoneCallDialpadDigitPressed(digit);
          provider.sendDtmf(digit);
        },
      ),
    );
  }

  void _showAudioRoutePicker(BuildContext context, PhoneCallProvider provider) async {
    await provider.loadAudioRoutes();
    if (!context.mounted) return;
    showOmiSheet<void>(
      context: context,
      title: context.l10n.audioOutput,
      builder: (sheetContext) => _AudioRouteSheet(
        routes: provider.availableRoutes,
        selectedRoute: provider.selectedRoute,
        onRouteSelected: (route) {
          provider.selectAudioRoute(route);
          Navigator.of(sheetContext).pop();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PhoneCallProvider>(
      builder: (context, provider, _) {
        bool isCallInProgress = provider.callState == PhoneCallState.active ||
            provider.callState == PhoneCallState.connecting ||
            provider.callState == PhoneCallState.ringing;

        return Scaffold(
          // A pushed page: the leading back control minimizes the call by stepping back one page,
          // exactly like system back and the iOS edge swipe (the call keeps running and the call
          // banner returns here). Hidden once the call is over, when the page closes itself.
          appBar: AppBar(
            automaticallyImplyLeading: false,
            leading: isCallInProgress
                ? OmiBackButton(
                    onPressed: () {
                      PlatformManager.instance.analytics.track('Phone Call Minimized');
                      Navigator.of(context).maybePop();
                    },
                  )
                : null,
          ),
          body: SafeArea(
            top: false,
            child: Column(
              children: [
                _CallInfoHeader(
                  contactName: provider.contactName,
                  phoneNumber: provider.remoteNumber ?? '',
                  duration: provider.callDuration,
                  state: provider.callState,
                ),
                const SizedBox(height: 16),
                // Transcription status indicator
                if (provider.callState == PhoneCallState.active)
                  _TranscriptionStatusIndicator(status: provider.transcriptionStatus),
                Expanded(
                  child: _LiveTranscriptView(
                    segments: provider.transcriptSegments,
                    getSpeakerLabel: provider.getSpeakerLabel,
                    status: provider.transcriptionStatus,
                  ),
                ),
                _CallControls(
                  state: provider.callState,
                  isMuted: provider.isMuted,
                  isSpeakerOn: provider.isSpeakerOn,
                  onMuteToggle: provider.toggleMute,
                  onSpeakerToggle: provider.toggleSpeaker,
                  onEndCall: () => provider.endCall(),
                  onKeypad: () => _showDtmfDialpad(context, provider),
                  onAudioRoute: () => _showAudioRoutePicker(context, provider),
                ),
                const SizedBox(height: OmiSpacing.xxl),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _CallInfoHeader extends StatelessWidget {
  final String? contactName;
  final String phoneNumber;
  final Duration duration;
  final PhoneCallState state;

  const _CallInfoHeader({
    required this.contactName,
    required this.phoneNumber,
    required this.duration,
    required this.state,
  });

  String _stateLabel(BuildContext context) {
    switch (state) {
      case PhoneCallState.connecting:
        return context.l10n.callStateConnecting;
      case PhoneCallState.ringing:
        return context.l10n.callStateRinging;
      case PhoneCallState.active:
        return formatPhoneCallDuration(duration);
      case PhoneCallState.ended:
        return context.l10n.callStateEnded;
      case PhoneCallState.failed:
        final provider = context.read<PhoneCallProvider>();
        return provider.lastError?.message ?? context.l10n.callStateFailed;
      default:
        return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        ExcludeSemantics(
          child: CircleAvatar(
            radius: 40,
            backgroundColor: OmiColors.surface3,
            child: Text(
              contactName != null && contactName!.isNotEmpty ? contactName![0].toUpperCase() : '#',
              style: OmiType.title1.copyWith(fontWeight: FontWeight.w400),
            ),
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
        Text(contactName ?? phoneNumber, style: OmiType.title2.copyWith(fontWeight: FontWeight.w500)),
        if (contactName != null)
          Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.xxs),
            child: Text(phoneNumber, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ),
        const SizedBox(height: OmiSpacing.xs),
        Semantics(
          liveRegion: state != PhoneCallState.active,
          child: Text(
            _stateLabel(context),
            style: OmiType.callout.copyWith(
              color: state == PhoneCallState.failed ? OmiColors.danger : OmiColors.textSecondary,
            ),
          ),
        ),
      ],
    );
  }
}

class _LiveTranscriptView extends StatelessWidget {
  final List<TranscriptSegment> segments;
  final String Function(TranscriptSegment) getSpeakerLabel;
  final TranscriptionStatus status;

  const _LiveTranscriptView({required this.segments, required this.getSpeakerLabel, required this.status});

  @override
  Widget build(BuildContext context) {
    if (segments.isEmpty) {
      if (status == TranscriptionStatus.noAudio) {
        // Do not promise a transcript the session is not receiving audio for.
        return Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              context.l10n.transcriptionNoAudio,
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.warning),
            ),
          ),
        );
      }
      return Center(
        child: Text(
          context.l10n.transcriptPlaceholder,
          style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      reverse: true,
      itemCount: segments.length,
      itemBuilder: (context, index) {
        var segment = segments[segments.length - 1 - index];
        var label = getSpeakerLabel(segment);

        return _TranscriptBubble(
          text: segment.text,
          speakerLabel: label,
          isUser: segment.isUser,
          translations: segment.translations,
        );
      },
    );
  }
}

class _TranscriptBubble extends StatelessWidget {
  final String text;
  final String speakerLabel;
  final bool isUser;
  final List<Translation> translations;

  const _TranscriptBubble({
    required this.text,
    required this.speakerLabel,
    required this.isUser,
    this.translations = const [],
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Align(
        alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
          child: Column(
            crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  speakerLabel,
                  style: OmiType.caption.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w500),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: isUser ? OmiColors.surface2 : OmiColors.surface1,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(OmiRadius.lg),
                    topRight: const Radius.circular(OmiRadius.lg),
                    bottomLeft: Radius.circular(isUser ? OmiRadius.lg : OmiSpacing.xxs),
                    bottomRight: Radius.circular(isUser ? OmiSpacing.xxs : OmiRadius.lg),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(text, style: OmiType.subhead.copyWith(height: 1.4)),
                    if (translations.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      ...translations.map(
                        (t) => Text(
                          t.text,
                          style: OmiType.subhead.copyWith(
                            color: OmiColors.textSecondary,
                            fontStyle: FontStyle.italic,
                            height: 1.3,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CallControls extends StatelessWidget {
  final PhoneCallState state;
  final bool isMuted;
  final bool isSpeakerOn;
  final VoidCallback onMuteToggle;
  final VoidCallback onSpeakerToggle;
  final VoidCallback onEndCall;
  final VoidCallback onKeypad;
  final VoidCallback? onAudioRoute;

  const _CallControls({
    required this.state,
    required this.isMuted,
    required this.isSpeakerOn,
    required this.onMuteToggle,
    required this.onSpeakerToggle,
    required this.onEndCall,
    required this.onKeypad,
    this.onAudioRoute,
  });

  @override
  Widget build(BuildContext context) {
    bool isActive = state == PhoneCallState.active || state == PhoneCallState.ringing;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _ControlButton(
            icon: isMuted ? Icons.mic_off : Icons.mic,
            label: isMuted ? context.l10n.phoneUnmute : context.l10n.phoneMute,
            isActive: isMuted,
            onTap: isActive ? onMuteToggle : null,
          ),
          _ControlButton(icon: Icons.dialpad, label: context.l10n.phoneKeypad, onTap: isActive ? onKeypad : null),
          _EndCallButton(onTap: state != PhoneCallState.ended ? onEndCall : null),
          Semantics(
            button: true,
            toggled: isSpeakerOn,
            enabled: isActive,
            onLongPressHint: onAudioRoute != null ? context.l10n.audioOutput : null,
            child: GestureDetector(
              onTap: isActive ? onSpeakerToggle : null,
              onLongPress: isActive ? onAudioRoute : null,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isSpeakerOn ? OmiColors.accent : OmiColors.surface2,
                    ),
                    child: Icon(
                      isSpeakerOn ? Icons.volume_up : Icons.volume_down,
                      color: isSpeakerOn
                          ? OmiColors.onAccent
                          : (isActive ? OmiColors.textPrimary : OmiColors.textDisabled),
                      size: 28,
                    ),
                  ),
                  const SizedBox(height: OmiSpacing.xs),
                  Text(
                    context.l10n.phoneSpeaker,
                    style: OmiType.caption.copyWith(color: isActive ? OmiColors.textPrimary : OmiColors.textDisabled),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ControlButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final VoidCallback? onTap;

  const _ControlButton({required this.icon, required this.label, this.isActive = false, this.onTap});

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return Semantics(
      button: true,
      enabled: enabled,
      child: GestureDetector(
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              decoration:
                  BoxDecoration(shape: BoxShape.circle, color: isActive ? OmiColors.accent : OmiColors.surface2),
              child: Icon(
                icon,
                color: isActive ? OmiColors.onAccent : (enabled ? OmiColors.textPrimary : OmiColors.textDisabled),
                size: 28,
              ),
            ),
            const SizedBox(height: OmiSpacing.xs),
            Text(
              label,
              style: OmiType.caption.copyWith(color: enabled ? OmiColors.textPrimary : OmiColors.textDisabled),
            ),
          ],
        ),
      ),
    );
  }
}

class _EndCallButton extends StatelessWidget {
  final VoidCallback? onTap;

  const _EndCallButton({this.onTap});

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    // Red is state (hang up), not decoration.
    return Semantics(
      button: true,
      enabled: enabled,
      child: GestureDetector(
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(shape: BoxShape.circle, color: enabled ? OmiColors.danger : OmiColors.surface2),
              child: Icon(Icons.call_end, color: enabled ? OmiColors.textPrimary : OmiColors.textDisabled, size: 32),
            ),
            const SizedBox(height: OmiSpacing.xs),
            Text(
              context.l10n.phoneEndCall,
              style: OmiType.caption.copyWith(color: enabled ? OmiColors.textPrimary : OmiColors.textDisabled),
            ),
          ],
        ),
      ),
    );
  }
}

class _DtmfDialpadSheet extends StatefulWidget {
  final void Function(String digit) onDigitPressed;

  const _DtmfDialpadSheet({required this.onDigitPressed});

  @override
  State<_DtmfDialpadSheet> createState() => _DtmfDialpadSheetState();
}

class _DtmfDialpadSheetState extends State<_DtmfDialpadSheet> {
  String _digits = '';

  static const _keys = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['*', '0', '#'],
  ];
  static const _subtexts = [
    ['', 'ABC', 'DEF'],
    ['GHI', 'JKL', 'MNO'],
    ['PQRS', 'TUV', 'WXYZ'],
    ['', '+', ''],
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Semantics(
            liveRegion: true,
            child: Text(
              _digits.isEmpty ? ' ' : _digits,
              textAlign: TextAlign.center,
              style: OmiType.title1.copyWith(fontWeight: FontWeight.w300, letterSpacing: 2),
            ),
          ),
          const SizedBox(height: OmiSpacing.md),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(_keys.length, (row) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: List.generate(_keys[row].length, (col) {
                      return _DtmfKey(
                        digit: _keys[row][col],
                        subtext: _subtexts[row][col],
                        onTap: () {
                          HapticFeedback.lightImpact();
                          widget.onDigitPressed(_keys[row][col]);
                          setState(() {
                            _digits += _keys[row][col];
                          });
                        },
                      );
                    }),
                  ),
                );
              }),
            ),
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiButton.tertiary(label: context.l10n.phoneHideKeypad, onPressed: () => Navigator.of(context).pop()),
        ],
      ),
    );
  }
}

class _DtmfKey extends StatelessWidget {
  final String digit;
  final String subtext;
  final VoidCallback onTap;

  const _DtmfKey({required this.digit, required this.subtext, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: digit,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        splashColor: OmiColors.textPrimary.withValues(alpha: 0.08),
        highlightColor: OmiColors.textPrimary.withValues(alpha: 0.05),
        child: Container(
          width: 72,
          height: 72,
          decoration: const BoxDecoration(shape: BoxShape.circle, color: OmiColors.surface2),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(digit, style: OmiType.title1.copyWith(fontWeight: FontWeight.w300)),
              if (subtext.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 1),
                  child: Text(
                    subtext,
                    style: OmiType.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: OmiColors.textTertiary,
                      letterSpacing: 1.5,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TranscriptionStatusIndicator extends StatelessWidget {
  final TranscriptionStatus status;

  const _TranscriptionStatusIndicator({required this.status});

  @override
  Widget build(BuildContext context) {
    if (status == TranscriptionStatus.idle || status == TranscriptionStatus.active) {
      return const SizedBox.shrink();
    }

    Color dotColor;
    String label;

    switch (status) {
      case TranscriptionStatus.connecting:
        dotColor = OmiColors.warning;
        label = context.l10n.transcriptionConnecting;
        break;
      case TranscriptionStatus.reconnecting:
        dotColor = OmiColors.warning;
        label = context.l10n.transcriptionReconnecting;
        break;
      case TranscriptionStatus.failed:
        dotColor = OmiColors.danger;
        label = context.l10n.transcriptionUnavailable;
        break;
      case TranscriptionStatus.noAudio:
        dotColor = OmiColors.warning;
        label = context.l10n.transcriptionNoAudio;
        break;
      default:
        return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(shape: BoxShape.circle, color: dotColor),
          ),
          const SizedBox(width: 6),
          Semantics(
            liveRegion: true,
            child: Text(label, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
          ),
        ],
      ),
    );
  }
}

class _AudioRouteSheet extends StatelessWidget {
  final List<AudioRoute> routes;
  final AudioRoute? selectedRoute;
  final void Function(AudioRoute route) onRouteSelected;

  const _AudioRouteSheet({required this.routes, required this.selectedRoute, required this.onRouteSelected});

  IconData _iconForType(AudioRouteType type) {
    switch (type) {
      case AudioRouteType.iPhone:
        return Icons.phone_android;
      case AudioRouteType.speaker:
        return Icons.volume_up;
      case AudioRouteType.airPods:
        return Icons.headphones;
      case AudioRouteType.bluetoothHeadset:
        return Icons.bluetooth_audio;
      case AudioRouteType.headphones:
        return Icons.headset;
      case AudioRouteType.carPlay:
        return Icons.directions_car;
      default:
        return Icons.speaker;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: OmiSpacing.md),
      child: OmiSettingsGroup(
        children: [
          for (final route in routes)
            Semantics(
              selected: selectedRoute?.id == route.id,
              child: OmiSettingsRow(
                leading: Icon(_iconForType(route.type)),
                title: route.name,
                trailing: selectedRoute?.id == route.id
                    ? const Icon(Icons.check, color: OmiColors.textPrimary, size: 20)
                    : null,
                showChevron: false,
                onTap: () => onRouteSelected(route),
              ),
            ),
        ],
      ),
    );
  }
}
