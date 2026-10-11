import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A chat app's brand mark.
class ChatAppLogo extends StatelessWidget {
  const ChatAppLogo(this.channel, {super.key, this.size = 40});

  final ChatChannel channel;
  final double size;

  @override
  Widget build(BuildContext context) {
    final Widget mark = switch (channel) {
      ChatChannel.telegram => Assets.images.telegramLogo.image(
          width: size,
          height: size,
        ),
      ChatChannel.whatsapp => Assets.images.whatsappLogo.image(
          width: size,
          height: size,
        ),
      ChatChannel.imessage => SvgPicture.asset(
          Assets.images.imessageLogo,
          width: size,
          height: size,
        ),
    };
    return ExcludeSemantics(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(size * 0.22),
        child: SizedBox.square(dimension: size, child: mark),
      ),
    );
  }
}

/// Telegram, iMessage and WhatsApp marks overlapping, for the Integrations entry.
class StackedChatAppLogos extends StatelessWidget {
  const StackedChatAppLogos({super.key, this.size = 32});

  final double size;

  @override
  Widget build(BuildContext context) {
    const channels = [
      ChatChannel.telegram,
      ChatChannel.imessage,
      ChatChannel.whatsapp,
    ];
    final step = size - 10;
    return SizedBox(
      width: step * (channels.length - 1) + size + 4,
      height: size + 4,
      child: Stack(
        children: [
          for (var i = 0; i < channels.length; i++)
            Positioned(
              left: step * i,
              child: Container(
                padding: const EdgeInsets.all(2),
                decoration: BoxDecoration(
                  color: OmiColors.surface1,
                  borderRadius: BorderRadius.circular(size * 0.22 + 2),
                ),
                child: ChatAppLogo(channels[i], size: size),
              ),
            ),
        ],
      ),
    );
  }
}

/// The Omi mark: a ring in the primary text colour.
class OmiRingMark extends StatelessWidget {
  const OmiRingMark({super.key, this.size = 28});

  final double size;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: OmiColors.textPrimary, width: size / 9),
        ),
      ),
    );
  }
}

/// An outlined capsule label ("INCLUDED WITH OMI PRO").
class ChatAppsOutlineTag extends StatelessWidget {
  const ChatAppsOutlineTag(this.label, {super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: OmiSpacing.xs,
        vertical: 3,
      ),
      decoration: BoxDecoration(
        border: Border.all(color: OmiColors.border),
        borderRadius: OmiRadius.pillAll,
      ),
      child: Text(
        label,
        style: OmiType.caption.copyWith(
          color: OmiColors.textSecondary,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}

/// A filled capsule label ("NEW", "OMI PRO") in the accent colours.
class ChatAppsFilledTag extends StatelessWidget {
  const ChatAppsFilledTag(this.label, {super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: OmiSpacing.xs,
        vertical: 3,
      ),
      decoration: BoxDecoration(
        color: OmiColors.accent,
        borderRadius: OmiRadius.pillAll,
      ),
      child: Text(
        label,
        style: OmiType.caption.copyWith(
          color: OmiColors.onAccent,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}

/// A line with a leading glyph, used for the capability list and the sheets' notes.
class ChatAppsBullet extends StatelessWidget {
  const ChatAppsBullet({
    super.key,
    required this.icon,
    required this.text,
    this.iconColor,
    this.style,
  });

  final IconData icon;
  final String text;
  final Color? iconColor;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 1),
          child: ExcludeSemantics(
            child: Icon(
              icon,
              size: 18,
              color: iconColor ?? OmiColors.textSecondary,
            ),
          ),
        ),
        const SizedBox(width: OmiSpacing.xs),
        Expanded(
          child: Text(
            text,
            style: style ?? OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          ),
        ),
      ],
    );
  }
}

/// A quiet inline note on a surface2 fill: the privacy note, the waitlist tip.
class ChatAppsNote extends StatelessWidget {
  const ChatAppsNote({super.key, this.icon, this.title, required this.message});

  final IconData? icon;
  final String? title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: OmiSpacing.sm + 2,
        vertical: OmiSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: OmiColors.surface2,
        borderRadius: OmiRadius.mdAll,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: ExcludeSemantics(
                child: Icon(icon, size: 18, color: OmiColors.textSecondary),
              ),
            ),
            const SizedBox(width: OmiSpacing.xs + 2),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title != null) ...[
                  Text(
                    title!,
                    style: OmiType.subhead.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: OmiSpacing.xxs),
                ],
                Text(
                  message,
                  style: OmiType.footnote.copyWith(
                    color: OmiColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The sheets' centred heading and description.
class ChatAppsSheetHeading extends StatelessWidget {
  const ChatAppsSheetHeading({
    super.key,
    required this.title,
    required this.message,
  });

  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Semantics(
          header: true,
          child: Text(
            title,
            textAlign: TextAlign.center,
            style: OmiType.title2.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(height: OmiSpacing.xs),
        Text(
          message,
          textAlign: TextAlign.center,
          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
        ),
      ],
    );
  }
}

/// The "Connected" capsule with a green dot.
class ChatAppsConnectedChip extends StatelessWidget {
  const ChatAppsConnectedChip({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: OmiSpacing.sm,
        vertical: 6,
      ),
      decoration: BoxDecoration(
        color: OmiColors.surface2,
        borderRadius: OmiRadius.pillAll,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(
              color: OmiColors.success,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            context.l10n.connected,
            style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }
}

/// Opens Omi's chat in [channel] at [endpoint]. Returns false when nothing could open it.
///
/// Telegram opens `https://t.me/<bot>` (with `?start=<token>` while linking), which the
/// Telegram app claims when installed. iMessage opens the Messages composer through `sms:`,
/// prefilled with [body]; iOS reads the body after `&`, Android after `?`.
Future<bool> openChatApp(
  ChatChannel channel,
  ChatChannelEndpoint endpoint, {
  String? startToken,
  String? body,
}) {
  final uri = chatAppUri(
    channel,
    endpoint,
    startToken: startToken,
    body: body,
    platform: defaultTargetPlatform,
  );
  if (uri == null) return Future.value(false);
  return chatAppLauncher(uri);
}

/// Opens the minted deep link when the server sent one, otherwise the flag address.
Future<bool> openChatAppProof(
  ChatChannel channel,
  ChatChannelEndpoint? endpoint, {
  String? deepLink,
  String? address,
  String? startToken,
  String? body,
}) {
  final uri = chatAppProofUri(
    channel: channel,
    endpoint: endpoint,
    deepLink: deepLink,
    address: address,
    startToken: startToken,
    body: body,
    platform: defaultTargetPlatform,
  );
  if (uri == null) return Future.value(false);
  return chatAppLauncher(uri);
}

/// Test seam for [openChatApp].
@visibleForTesting
Future<bool> Function(Uri uri) chatAppLauncher = _launch;

Future<bool> _launch(Uri uri) async {
  try {
    return await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (_) {
    return false;
  }
}

/// Prefer the mint response. [deepLink] is a full `https` or `sms` URI. [address] replaces the
/// flag payload's address. When neither is present, [endpoint] is the fallback.
Uri? chatAppProofUri({
  required ChatChannel channel,
  required ChatChannelEndpoint? endpoint,
  String? deepLink,
  String? address,
  String? startToken,
  String? body,
  required TargetPlatform platform,
}) {
  final deep = deepLink?.trim();
  if (deep != null && deep.isNotEmpty) {
    final uri = Uri.tryParse(deep);
    if (uri != null && (uri.isScheme('https') || uri.isScheme('sms'))) return uri;
  }
  if (endpoint == null) return null;
  final override = address?.trim();
  final resolved = override == null || override.isEmpty
      ? endpoint
      : ChatChannelEndpoint(provider: endpoint.provider, address: override);
  return chatAppUri(
    channel,
    resolved,
    startToken: channel == ChatChannel.telegram ? startToken : null,
    body: channel == ChatChannel.imessage ? body : null,
    platform: platform,
  );
}

@visibleForTesting
Uri? chatAppUri(
  ChatChannel channel,
  ChatChannelEndpoint endpoint, {
  String? startToken,
  String? body,
  required TargetPlatform platform,
}) {
  switch (channel) {
    case ChatChannel.telegram:
      final bot = endpoint.address.replaceFirst(RegExp(r'^@'), '');
      return Uri(
        scheme: 'https',
        host: 't.me',
        path: bot,
        queryParameters: startToken == null ? null : {'start': startToken},
      );
    case ChatChannel.imessage:
      final number = endpoint.address.replaceAll(RegExp(r'[\s()-]'), '');
      if (body == null) return Uri(scheme: 'sms', path: number);
      final separator = platform == TargetPlatform.iOS ? '&' : '?';
      return Uri.parse(
        'sms:$number${separator}body=${Uri.encodeComponent(body)}',
      );
    case ChatChannel.whatsapp:
      return null;
  }
}

/// `t.me/<bot>?start=<token>`: the link a person can open on another device.
String telegramLinkText(ChatChannelEndpoint endpoint, String token) => chatAppUri(
      ChatChannel.telegram,
      endpoint,
      startToken: token,
      platform: TargetPlatform.iOS,
    ).toString();

/// The one-time code in four-character groups, for reading aloud or retyping.
String groupedLinkCode(String code) {
  final buffer = StringBuffer();
  for (var i = 0; i < code.length; i++) {
    if (i > 0 && i % 4 == 0) buffer.write(' ');
    buffer.write(code[i]);
  }
  return buffer.toString();
}
