import 'package:flutter/material.dart';

import 'package:clock/clock.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/payment.dart' as payment_api;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/widgets/yearly_switch.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// How long a paying reader's Omi can go without a conversation before Home says so.
const quietPayerAfter = Duration(days: 5);

/// Whether the reader pays for a monthly price: no trial, no discount or prepaid coupon. Null when unknown.
typedef MonthlyPayerLoader = Future<bool?> Function();

/// The yearly-switch answer (backend `utils/yearly_switch.py` `refusal`) checks trial, discount, a
/// renewing status and a paid price before it checks the interval, so these answers all mean a paid,
/// undiscounted, non-trial monthly price. Any other answer, or none, is not proof.
const _paidMonthlyAnswers = {'eligible', 'currency', 'not_offered', 'no_yearly_price', 'no_savings'};

/// True for a paid monthly price, false for anything else (yearly, trial, discounted, free), null unread.
bool? paidMonthlyFromYearlySwitch(wire.GeneratedYearlySwitchResponse? offer) =>
    offer == null ? null : offer.eligible || _paidMonthlyAnswers.contains(offer.reason);

Future<bool?> _loadMonthlyPayer() async => paidMonthlyFromYearlySwitch(await payment_api.getYearlySwitch());

/// Home's quiet row for a paying monthly reader whose Omi has recorded nothing for 5 days.
///
/// Shown only when all hold: a paid monthly subscription with subscription UI allowed and no
/// payment issue (that row wins); an Omi pendant is paired and not connected; the conversation list
/// has loaded, unfiltered, and its newest conversation is older than [quietPayerAfter]. Unknown
/// answers show nothing. The row leaves by itself when a conversation arrives or the Omi connects.
/// Check opens the device page, the one the Home device chip opens for a paired Omi.
class QuietPayerRow extends StatelessWidget {
  const QuietPayerRow({super.key, this.loadMonthlyPayer, this.rememberedDevice, this.devicePage});

  /// Tests swap in a fake; defaults to the yearly-switch read.
  final MonthlyPayerLoader? loadMonthlyPayer;

  /// The pairing the app remembers before the device provider has read it; tests swap in a fake.
  final BtDevice Function()? rememberedDevice;

  /// The page Check opens; tests swap in a plain page. Defaults to [DeviceSettings].
  final Widget Function()? devicePage;

  static final Map<String, Future<bool?>> _monthlyBySubscription = {};
  static bool _shownThisSession = false;

  @visibleForTesting
  static void resetSession() {
    _monthlyBySubscription.clear();
    _shownThisSession = false;
  }

  @override
  Widget build(BuildContext context) {
    final subscriptionId = context.select<UsageProvider?, String?>(
      (usage) => usage?.subscription?.paymentIssue == null ? yearlySwitchCandidate(usage) : null,
    );
    final omiOffline = context.select<DeviceProvider?, bool>((device) {
      if (device == null || device.connectedDevice != null || device.isConnecting) return false;
      final paired = device.pairedDevice;
      final omi = paired != null && paired.id.isNotEmpty
          ? paired
          : (rememberedDevice ?? () => SharedPreferencesUtil().btDevice)();
      return omi.id.isNotEmpty && omi.type == DeviceType.omi;
    });
    final newest = context.select<ConversationProvider?, DateTime?>((list) {
      if (list == null ||
          list.isLoadingConversations ||
          list.conversationsLoadFailed ||
          list.hasActiveSearch ||
          list.showStarredOnly ||
          list.selectedFolderId != null ||
          list.selectedStartDate != null ||
          list.conversations.isEmpty) {
        return null;
      }
      final first = list.conversations.first;
      return first.startedAt ?? first.createdAt;
    });
    if (subscriptionId == null || !omiOffline || newest == null) return const SizedBox.shrink();
    if (clock.now().difference(newest) <= quietPayerAfter) return const SizedBox.shrink();
    final monthly = _monthlyBySubscription.putIfAbsent(
      subscriptionId,
      loadMonthlyPayer ?? _loadMonthlyPayer,
    );
    return FutureBuilder<bool?>(
      future: monthly,
      builder: (context, snapshot) =>
          snapshot.data == true ? _QuietRow(devicePage: devicePage) : const SizedBox.shrink(),
    );
  }
}

class _QuietRow extends StatefulWidget {
  const _QuietRow({this.devicePage});

  final Widget Function()? devicePage;

  @override
  State<_QuietRow> createState() => _QuietRowState();
}

class _QuietRowState extends State<_QuietRow> {
  @override
  void initState() {
    super.initState();
    if (!QuietPayerRow._shownThisSession) {
      QuietPayerRow._shownThisSession = true;
      const TypedEvents().emit(const SubscriptionQuietRowShown());
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final headlineSize = OmiType.headline.fontSize!;
    final largeText = MediaQuery.textScalerOf(context).scale(headlineSize) > headlineSize * 1.3;
    final message = Row(
      children: [
        ExcludeSemantics(
          child: SizedBox.square(
            dimension: 10,
            child: DecoratedBox(decoration: BoxDecoration(color: OmiColors.textTertiary, shape: BoxShape.circle)),
          ),
        ),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(l10n.quietPayerTitle, style: OmiType.headline),
              Text(l10n.quietPayerMessage, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
          ),
        ),
      ],
    );
    final check = OmiButton(
      key: const ValueKey('quiet_payer_check'),
      label: l10n.quietPayerCheck,
      size: OmiButtonSize.compact,
      pill: true,
      onPressed: () {
        const TypedEvents().emit(const SubscriptionQuietRowTapped());
        routeToPage(context, widget.devicePage?.call() ?? const DeviceSettings());
      },
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
      child: MergeSemantics(
        child: DecoratedBox(
          key: const ValueKey('quiet_payer_row'),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.sm, OmiSpacing.sm),
            child: largeText
                ? Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [message, const SizedBox(height: OmiSpacing.sm), check],
                  )
                : Row(children: [Expanded(child: message), const SizedBox(width: OmiSpacing.sm), check]),
          ),
        ),
      ),
    );
  }
}
