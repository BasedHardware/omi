import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/models/audio_route.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
    MixpanelManager().phoneCallDialpadOpened();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => _DtmfDialpadSheet(
        onDigitPressed: (digit) {
          MixpanelManager().phoneCallDialpadDigitPressed(digit);
          provider.sendDtmf(digit);
        },
      ),
    );
  }

  void _showAudioRoutePicker(BuildContext context, PhoneCallProvider provider) async {
    await provider.loadAudioRoutes();
    if (!mounted) return;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => _AudioRouteSheet(
        routes: provider.availableRoutes,
        selectedRoute: provider.selectedRoute,
        onRouteSelected: (route) {
          provider.selectAudioRoute(route);
          Navigator.of(context).pop();
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
          backgroundColor: Colors.black,
          body: SafeArea(
            child: Column(
              children: [
                // Top bar with minimize button — always visible so user can return to app
                Padding(
                  padding: const EdgeInsets.only(left: 8, right: 8, top: 4),
                  child: Row(
                    children: [
                      if (isCallInProgress)
                        IconButton(
                          onPressed: () {
                            MixpanelManager().track('Phone Call Minimized');
                            Navigator.of(context).popUntil((route) => route.isFirst);
                          },
                          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 22),
                          padding: const EdgeInsets.all(12),
                          constraints: const BoxConstraints(),
                        )
                      else
                        const SizedBox(width: 46),
                      const Spacer(),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
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
                const SizedBox(height: 32),
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

  String _formatDuration(Duration d) {
    String twoDigits(int n) => n.toString().padLeft(2, '0');
    if (d.inHours > 0) {
      return '${twoDigits(d.inHours)}:${twoDigits(d.inMinutes.remainder(60))}:${twoDigits(d.inSeconds.remainder(60))}';
    }
    return '${twoDigits(d.inMinutes)}:${twoDigits(d.inSeconds.remainder(60))}';
  }

  String _stateLabel(BuildContext context) {
    switch (state) {
      case PhoneCallState.connecting:
        return context.l10n.callStateConnecting;
      case PhoneCallState.ringing:
        return context.l10n.callStateRinging;
      case PhoneCallState.active:
        return _formatDuration(duration);
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
        CircleAvatar(
          radius: 40,
          backgroundColor: Colors.grey[800],
          child: Text(
            contactName != null && contactName!.isNotEmpty ? contactName![0].toUpperCase() : '#',
            style: const TextStyle(fontSize: 32, color: Colors.white),
          ),
        ),
        const SizedBox(height: 16),
        Text(
          contactName ?? phoneNumber,
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w500, color: Colors.white),
        ),
        if (contactName != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(phoneNumber, style: TextStyle(fontSize: 14, color: Colors.grey[400])),
          ),
        const SizedBox(height: 8),
        Text(
          _stateLabel(context),
          style: TextStyle(fontSize: 16, color: state == PhoneCallState.failed ? Colors.red[300] : Colors.grey[400]),
        ),
      ],
    );
  }
}

class _LiveTranscriptView extends StatelessWidget {
  final List<TranscriptSegment> segments;
  final String Function(TranscriptSegment) getSpeakerLabel;

  const _LiveTranscriptView({required this.segments, required this.getSpeakerLabel});

  @override
  Widget build(BuildContext context) {
    if (segments.isEmpty) {
      return Center(
        child: Text(context.l10n.transcriptPlaceholder, style: TextStyle(color: Colors.grey[600], fontSize: 14)),
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
                  style: TextStyle(fontSize: 12, color: Colors.grey[500], fontWeight: FontWeight.w500),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: isUser ? const Color(0xFF2A2A30) : Colors.grey[850],
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(16),
                    topRight: const Radius.circular(16),
                    bottomLeft: isUser ? const Radius.circular(16) : const Radius.circular(4),
                    bottomRight: isUser ? const Radius.circular(4) : const Radius.circular(16),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(text, style: const TextStyle(fontSize: 15, color: Colors.white, height: 1.4)),
                    if (translations.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      ...translations.map(
                        (t) => Text(
                          t.text,
                          style: TextStyle(
                            fontSize: 14,
                            color: Colors.white.withValues(alpha: 0.7),
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
          GestureDetector(
            onTap: isActive ? onSpeakerToggle : null,
            onLongPress: isActive ? onAudioRoute : null,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration:
                      BoxDecoration(shape: BoxShape.circle, color: isSpeakerOn ? Colors.white : Colors.grey[800]),
                  child: Icon(
                    isSpeakerOn ? Icons.volume_up : Icons.volume_down,
                    color: isSpeakerOn ? Colors.black : (isActive ? Colors.white : Colors.grey[600]),
                    size: 28,
                  ),
                ),
                const SizedBox(height: 8),
                Text(context.l10n.phoneSpeaker,
                    style: TextStyle(fontSize: 12, color: isActive ? Colors.white : Colors.grey[600])),
              ],
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
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(shape: BoxShape.circle, color: isActive ? Colors.white : Colors.grey[800]),
            child: Icon(
              icon,
              color: isActive ? Colors.black : (onTap != null ? Colors.white : Colors.grey[600]),
              size: 28,
            ),
          ),
          const SizedBox(height: 8),
          Text(label, style: TextStyle(fontSize: 12, color: onTap != null ? Colors.white : Colors.grey[600])),
        ],
      ),
    );
  }
}

class _EndCallButton extends StatelessWidget {
  final VoidCallback? onTap;

  const _EndCallButton({this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(shape: BoxShape.circle, color: onTap != null ? Colors.red : Colors.grey[800]),
            child: Icon(Icons.call_end, color: onTap != null ? Colors.white : Colors.grey[600], size: 32),
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.phoneEndCall,
            style: TextStyle(fontSize: 12, color: onTap != null ? Colors.white : Colors.grey[600]),
          ),
        ],
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
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: const EdgeInsets.only(top: 12, bottom: 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 36,
            height: 4,
            decoration: BoxDecoration(color: Colors.grey[700], borderRadius: BorderRadius.circular(2)),
          ),
          const SizedBox(height: 16),
          Text(
            _digits.isEmpty ? ' ' : _digits,
            style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w300, color: Colors.white, letterSpacing: 2),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
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
          const SizedBox(height: 16),
          GestureDetector(
            onTap: () => Navigator.of(context).pop(),
            child: Text(context.l10n.phoneHideKeypad, style: TextStyle(fontSize: 16, color: Colors.grey[400])),
          ),
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
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(36),
      splashColor: Colors.white.withValues(alpha: 0.08),
      highlightColor: Colors.white.withValues(alpha: 0.05),
      child: Container(
        width: 72,
        height: 72,
        decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFF2A2A30)),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              digit,
              style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w300, color: Colors.white),
            ),
            if (subtext.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 1),
                child: Text(
                  subtext,
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w500,
                    color: Colors.grey[600],
                    letterSpacing: 1.5,
                  ),
                ),
              ),
          ],
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
        dotColor = Colors.yellow;
        label = context.l10n.transcriptionConnecting;
        break;
      case TranscriptionStatus.reconnecting:
        dotColor = Colors.orange;
        label = context.l10n.transcriptionReconnecting;
        break;
      case TranscriptionStatus.failed:
        dotColor = Colors.red;
        label = context.l10n.transcriptionUnavailable;
        break;
      default:
        return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(shape: BoxShape.circle, color: dotColor),
          ),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(fontSize: 12, color: Colors.grey[500])),
        ],
      ),
    );
  }
}

class _AudioRouteSheet extends StatelessWidget {
  final List<AudioRoute> routes;
  final AudioRoute? selectedRoute;
  final void Function(AudioRoute route) onRouteSelected;

  const _AudioRouteSheet({
    required this.routes,
    required this.selectedRoute,
    required this.onRouteSelected,
  });

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
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: const EdgeInsets.only(top: 12, bottom: 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 36,
            height: 4,
            decoration: BoxDecoration(color: Colors.grey[700], borderRadius: BorderRadius.circular(2)),
          ),
          const SizedBox(height: 16),
          Text(context.l10n.audioOutput,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white)),
          const SizedBox(height: 12),
          ...routes.map((route) {
            bool isSelected = selectedRoute?.id == route.id;
            return ListTile(
              leading: Icon(_iconForType(route.type), color: isSelected ? Colors.blue : Colors.white, size: 24),
              title: Text(route.name, style: TextStyle(color: isSelected ? Colors.blue : Colors.white, fontSize: 16)),
              trailing: isSelected ? const Icon(Icons.check, color: Colors.blue, size: 20) : null,
              onTap: () => onRouteSelected(route),
            );
          }),
        ],
      ),
    );
  }
}
