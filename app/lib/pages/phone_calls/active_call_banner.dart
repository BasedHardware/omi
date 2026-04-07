import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Compact call banner shown on the home screen when a phone call is active.
/// Displays contact info, live transcript snippet, and inline call controls.
/// Tapping the banner navigates back to the full [ActiveCallPage].
class ActiveCallBanner extends StatelessWidget {
  const ActiveCallBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PhoneCallProvider>(
      builder: (context, provider, _) {
        bool isCallInProgress = provider.callState == PhoneCallState.active ||
            provider.callState == PhoneCallState.connecting ||
            provider.callState == PhoneCallState.ringing;

        if (!isCallInProgress) return const SizedBox.shrink();

        return GestureDetector(
          onTap: () {
            MixpanelManager().track('Phone Call Banner Tapped');
            Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ActiveCallPage()));
          },
          child: Container(
            margin: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25),
              borderRadius: BorderRadius.circular(24),
            ),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Row 1: Call info + duration + expand icon
                  _CallInfoRow(
                    contactName: provider.contactName,
                    phoneNumber: provider.remoteNumber ?? '',
                    duration: provider.callDuration,
                    state: provider.callState,
                  ),
                  // Row 2: Transcript snippet (if any)
                  if (provider.transcriptSegments.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: _TranscriptSnippet(
                        text: provider.transcriptSegments.last.text,
                        speakerLabel: provider.getSpeakerLabel(provider.transcriptSegments.last),
                      ),
                    ),
                  // Row 3: Compact call controls
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: _CompactCallControls(
                      state: provider.callState,
                      isMuted: provider.isMuted,
                      isSpeakerOn: provider.isSpeakerOn,
                      onMuteToggle: provider.toggleMute,
                      onSpeakerToggle: provider.toggleSpeaker,
                      onEndCall: () => provider.endCall(),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _CallInfoRow extends StatelessWidget {
  final String? contactName;
  final String phoneNumber;
  final Duration duration;
  final PhoneCallState state;

  const _CallInfoRow({
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

  @override
  Widget build(BuildContext context) {
    String statusText;
    switch (state) {
      case PhoneCallState.connecting:
        statusText = context.l10n.callStateConnecting;
        break;
      case PhoneCallState.ringing:
        statusText = context.l10n.callStateRinging;
        break;
      case PhoneCallState.active:
        statusText = _formatDuration(duration);
        break;
      default:
        statusText = '';
    }

    return Row(
      children: [
        // Phone icon — green when transcribing, orange when reconnecting, red when failed
        Builder(builder: (context) {
          final provider = context.watch<PhoneCallProvider>();
          Color iconColor;
          switch (provider.transcriptionStatus) {
            case TranscriptionStatus.reconnecting:
              iconColor = Colors.orange;
              break;
            case TranscriptionStatus.failed:
              iconColor = Colors.red;
              break;
            default:
              iconColor = const Color(0xFF34C759);
          }
          return Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(color: iconColor, shape: BoxShape.circle),
            child: const Icon(Icons.phone_in_talk, color: Colors.white, size: 16),
          );
        }),
        const SizedBox(width: 10),
        // Contact name / number
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                contactName ?? phoneNumber,
                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (contactName != null && phoneNumber.isNotEmpty)
                Text(
                  phoneNumber,
                  style: TextStyle(color: Colors.grey[500], fontSize: 12),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
            ],
          ),
        ),
        // Duration / status
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(color: const Color(0xFF35343B), borderRadius: BorderRadius.circular(12)),
          child: Text(
            statusText,
            style: const TextStyle(color: Color(0xFF34C759), fontSize: 13, fontWeight: FontWeight.w500),
          ),
        ),
        const SizedBox(width: 6),
        // Expand icon
        const Icon(Icons.keyboard_arrow_up, color: Colors.grey, size: 22),
      ],
    );
  }
}

class _TranscriptSnippet extends StatelessWidget {
  final String text;
  final String speakerLabel;

  const _TranscriptSnippet({required this.text, required this.speakerLabel});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(color: const Color(0xFF2A2A30), borderRadius: BorderRadius.circular(12)),
      child: Text(
        '$speakerLabel: $text',
        style: TextStyle(color: Colors.grey[400], fontSize: 13, height: 1.3),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

class _CompactCallControls extends StatelessWidget {
  final PhoneCallState state;
  final bool isMuted;
  final bool isSpeakerOn;
  final VoidCallback onMuteToggle;
  final VoidCallback onSpeakerToggle;
  final VoidCallback onEndCall;

  const _CompactCallControls({
    required this.state,
    required this.isMuted,
    required this.isSpeakerOn,
    required this.onMuteToggle,
    required this.onSpeakerToggle,
    required this.onEndCall,
  });

  @override
  Widget build(BuildContext context) {
    bool isActive = state == PhoneCallState.active || state == PhoneCallState.ringing;

    return Row(
      children: [
        // Mute button
        _CompactControlButton(
          icon: isMuted ? Icons.mic_off : Icons.mic,
          label: isMuted ? context.l10n.phoneUnmute : context.l10n.phoneMute,
          isActive: isMuted,
          onTap: isActive ? onMuteToggle : null,
        ),
        const SizedBox(width: 8),
        // Speaker button
        _CompactControlButton(
          icon: isSpeakerOn ? Icons.volume_up : Icons.volume_down,
          label: context.l10n.phoneSpeaker,
          isActive: isSpeakerOn,
          onTap: isActive ? onSpeakerToggle : null,
        ),
        const Spacer(),
        // End call button
        GestureDetector(
          onTap: () {
            HapticFeedback.heavyImpact();
            onEndCall();
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            decoration: BoxDecoration(color: Colors.red, borderRadius: BorderRadius.circular(20)),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.call_end, color: Colors.white, size: 18),
                const SizedBox(width: 6),
                Text(
                  context.l10n.phoneEndCall,
                  style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _CompactControlButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final VoidCallback? onTap;

  const _CompactControlButton({required this.icon, required this.label, this.isActive = false, this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap == null
          ? null
          : () {
              HapticFeedback.mediumImpact();
              onTap!();
            },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: isActive ? Colors.white : const Color(0xFF35343B),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: isActive ? Colors.black : (onTap != null ? Colors.white : Colors.grey[600]), size: 18),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                color: isActive ? Colors.black : (onTap != null ? Colors.white : Colors.grey[600]),
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Slim bar shown at the top of non-home tabs when a call is active.
/// Tapping it navigates to the full [ActiveCallPage].
class ActiveCallTopBar extends StatelessWidget {
  const ActiveCallTopBar({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PhoneCallProvider>(
      builder: (context, provider, _) {
        bool isCallInProgress = provider.callState == PhoneCallState.active ||
            provider.callState == PhoneCallState.connecting ||
            provider.callState == PhoneCallState.ringing;

        if (!isCallInProgress) return const SizedBox.shrink();

        String twoDigits(int n) => n.toString().padLeft(2, '0');
        Duration d = provider.callDuration;
        String timeStr = d.inHours > 0
            ? '${twoDigits(d.inHours)}:${twoDigits(d.inMinutes.remainder(60))}:${twoDigits(d.inSeconds.remainder(60))}'
            : '${twoDigits(d.inMinutes)}:${twoDigits(d.inSeconds.remainder(60))}';

        String displayName = provider.contactName ?? provider.remoteNumber ?? '';

        return GestureDetector(
          onTap: () {
            MixpanelManager().track('Phone Call Top Bar Tapped');
            Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ActiveCallPage()));
          },
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            color: const Color(0xFF34C759),
            child: Row(
              children: [
                const Icon(Icons.phone_in_talk, color: Colors.white, size: 16),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    displayName,
                    style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Text(
                  timeStr,
                  style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
                ),
                const SizedBox(width: 6),
                const Icon(Icons.keyboard_arrow_up, color: Colors.white, size: 18),
              ],
            ),
          ),
        );
      },
    );
  }
}
