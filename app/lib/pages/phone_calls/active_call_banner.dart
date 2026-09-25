import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/pages/phone_calls/call_duration_format.dart';

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
            PlatformManager.instance.analytics.track('Phone Call Banner Tapped');
            routeToPage(context, const ActiveCallPage());
          },
          child: Container(
            margin: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xxs),
            decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 14, OmiSpacing.sm, 9),
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
                  // The controls carry 5pt of their own vertical padding (44pt targets).
                  Padding(
                    padding: const EdgeInsets.only(top: 7),
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
        statusText = formatPhoneCallDuration(duration);
        break;
      default:
        statusText = '';
    }

    return Row(
      children: [
        // Phone icon — green when transcribing, orange when reconnecting, red when failed
        Builder(
          builder: (context) {
            final provider = context.watch<PhoneCallProvider>();
            Color iconColor;
            switch (provider.transcriptionStatus) {
              case TranscriptionStatus.reconnecting:
                iconColor = OmiColors.warning;
                break;
              case TranscriptionStatus.failed:
                iconColor = OmiColors.danger;
                break;
              default:
                iconColor = OmiColors.success;
            }
            return ExcludeSemantics(
              child: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(color: iconColor, shape: BoxShape.circle),
                child: const Icon(Icons.phone_in_talk, color: OmiColors.textPrimary, size: 16),
              ),
            );
          },
        ),
        const SizedBox(width: 10),
        // Contact name / number
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                contactName ?? phoneNumber,
                style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (contactName != null && phoneNumber.isNotEmpty)
                Text(
                  phoneNumber,
                  style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
            ],
          ),
        ),
        // Duration / status
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
          child: Text(
            statusText,
            style: OmiType.footnote.copyWith(color: OmiColors.success, fontWeight: FontWeight.w500),
          ),
        ),
        const SizedBox(width: 6),
        // Expand icon
        const ExcludeSemantics(child: Icon(Icons.keyboard_arrow_up, color: OmiColors.textTertiary, size: 22)),
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
      decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
      child: Text(
        '$speakerLabel: $text',
        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.3),
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
        // Red is state (hang up), not decoration.
        Semantics(
          button: true,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              HapticFeedback.heavyImpact();
              onEndCall();
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.xs),
                decoration: const BoxDecoration(color: OmiColors.danger, borderRadius: OmiRadius.pillAll),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.call_end, color: OmiColors.textPrimary, size: 18),
                    const SizedBox(width: 6),
                    Text(context.l10n.phoneEndCall, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
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
    final foreground = isActive ? OmiColors.onAccent : (onTap != null ? OmiColors.textPrimary : OmiColors.textDisabled);
    return Semantics(
      button: true,
      enabled: onTap != null,
      toggled: isActive,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap == null
            ? null
            : () {
                HapticFeedback.mediumImpact();
                onTap!();
              },
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
            decoration: BoxDecoration(
              color: isActive ? OmiColors.accent : OmiColors.surface2,
              borderRadius: OmiRadius.pillAll,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, color: foreground, size: 18),
                const SizedBox(width: 6),
                Text(label, style: OmiType.caption.copyWith(color: foreground, fontWeight: FontWeight.w500)),
              ],
            ),
          ),
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

        String timeStr = formatPhoneCallDuration(provider.callDuration);

        String displayName = provider.contactName ?? provider.remoteNumber ?? '';

        return GestureDetector(
          onTap: () {
            PlatformManager.instance.analytics.track('Phone Call Top Bar Tapped');
            routeToPage(context, const ActiveCallPage());
          },
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 10),
            // The in-call green is state (a call is live), as in the system call bar. Black on it
            // keeps text legible (white on this green is under 2:1).
            color: OmiColors.success,
            child: Row(
              children: [
                const ExcludeSemantics(child: Icon(Icons.phone_in_talk, color: OmiColors.onAccent, size: 16)),
                const SizedBox(width: OmiSpacing.xs),
                Expanded(
                  child: Text(
                    displayName,
                    style: OmiType.subhead.copyWith(color: OmiColors.onAccent, fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Text(
                  timeStr,
                  style: OmiType.subhead.copyWith(color: OmiColors.onAccent, fontWeight: FontWeight.w500),
                ),
                const SizedBox(width: 6),
                const ExcludeSemantics(child: Icon(Icons.keyboard_arrow_up, color: OmiColors.onAccent, size: 18)),
              ],
            ),
          ),
        );
      },
    );
  }
}
