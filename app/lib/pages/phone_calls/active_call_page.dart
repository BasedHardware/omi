import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/phone_call_provider.dart';

class ActiveCallPage extends StatefulWidget {
  const ActiveCallPage({super.key});

  @override
  State<ActiveCallPage> createState() => _ActiveCallPageState();
}

class _ActiveCallPageState extends State<ActiveCallPage> {
  bool _popScheduled = false;

  @override
  void initState() {
    super.initState();
    context.read<PhoneCallProvider>().addListener(_onProviderChanged);
  }

  @override
  void dispose() {
    context.read<PhoneCallProvider>().removeListener(_onProviderChanged);
    super.dispose();
  }

  void _onProviderChanged() {
    var state = context.read<PhoneCallProvider>().callState;
    if ((state == PhoneCallState.ended || state == PhoneCallState.failed) && !_popScheduled) {
      _popScheduled = true;
      Future.delayed(const Duration(seconds: 2), () {
        if (mounted) {
          Navigator.of(context).pop();
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PhoneCallProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: provider.callState == PhoneCallState.idle || provider.callState == PhoneCallState.ended,
          child: Scaffold(
            backgroundColor: Colors.black,
            body: SafeArea(
              child: Column(
                children: [
                  const SizedBox(height: 32),
                  _CallInfoHeader(
                    contactName: provider.contactName,
                    phoneNumber: provider.remoteNumber ?? '',
                    duration: provider.callDuration,
                    state: provider.callState,
                  ),
                  const SizedBox(height: 16),
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
                  ),
                  const SizedBox(height: 32),
                ],
              ),
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

  String _stateLabel() {
    switch (state) {
      case PhoneCallState.connecting:
        return 'Connecting...';
      case PhoneCallState.ringing:
        return 'Ringing...';
      case PhoneCallState.active:
        return _formatDuration(duration);
      case PhoneCallState.ended:
        return 'Call Ended';
      case PhoneCallState.failed:
        return 'Call Failed';
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
            child: Text(
              phoneNumber,
              style: TextStyle(fontSize: 14, color: Colors.grey[400]),
            ),
          ),
        const SizedBox(height: 8),
        Text(
          _stateLabel(),
          style: TextStyle(
            fontSize: 16,
            color: state == PhoneCallState.failed ? Colors.red[300] : Colors.grey[400],
          ),
        ),
      ],
    );
  }
}

class _LiveTranscriptView extends StatelessWidget {
  final List<PhoneTranscriptSegment> segments;
  final String Function(PhoneTranscriptSegment) getSpeakerLabel;

  const _LiveTranscriptView({
    required this.segments,
    required this.getSpeakerLabel,
  });

  @override
  Widget build(BuildContext context) {
    if (segments.isEmpty) {
      return Center(
        child: Text(
          'Transcript will appear here...',
          style: TextStyle(color: Colors.grey[600], fontSize: 14),
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
          isFinal: segment.isFinal,
        );
      },
    );
  }
}

class _TranscriptBubble extends StatelessWidget {
  final String text;
  final String speakerLabel;
  final bool isUser;
  final bool isFinal;

  const _TranscriptBubble({
    required this.text,
    required this.speakerLabel,
    required this.isUser,
    required this.isFinal,
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
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey[500],
                    fontWeight: FontWeight.w500,
                  ),
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
                child: Text(
                  text,
                  style: TextStyle(
                    fontSize: 15,
                    color: Colors.white,
                    fontStyle: isFinal ? FontStyle.normal : FontStyle.italic,
                    height: 1.4,
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

class _CallControls extends StatelessWidget {
  final PhoneCallState state;
  final bool isMuted;
  final bool isSpeakerOn;
  final VoidCallback onMuteToggle;
  final VoidCallback onSpeakerToggle;
  final VoidCallback onEndCall;

  const _CallControls({
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

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _ControlButton(
            icon: isMuted ? Icons.mic_off : Icons.mic,
            label: isMuted ? 'Unmute' : 'Mute',
            isActive: isMuted,
            onTap: isActive ? onMuteToggle : null,
          ),
          _EndCallButton(
            onTap: state != PhoneCallState.ended ? onEndCall : null,
          ),
          _ControlButton(
            icon: isSpeakerOn ? Icons.volume_up : Icons.volume_down,
            label: 'Speaker',
            isActive: isSpeakerOn,
            onTap: isActive ? onSpeakerToggle : null,
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

  const _ControlButton({
    required this.icon,
    required this.label,
    this.isActive = false,
    this.onTap,
  });

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
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isActive ? Colors.white : Colors.grey[800],
            ),
            child: Icon(
              icon,
              color: isActive ? Colors.black : (onTap != null ? Colors.white : Colors.grey[600]),
              size: 28,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            label,
            style: TextStyle(fontSize: 12, color: onTap != null ? Colors.white : Colors.grey[600]),
          ),
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
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: onTap != null ? Colors.red : Colors.grey[800],
            ),
            child: Icon(
              Icons.call_end,
              color: onTap != null ? Colors.white : Colors.grey[600],
              size: 32,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'End',
            style: TextStyle(fontSize: 12, color: onTap != null ? Colors.white : Colors.grey[600]),
          ),
        ],
      ),
    );
  }
}
