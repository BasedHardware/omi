import 'package:flutter/material.dart';

import '../art.dart';
import '../content.dart';
import '../theme.dart';
import '../widgets.dart';

/// 01 — Welcome. Sign in first; the paywall comes straight after.
class WelcomeV2Screen extends StatelessWidget {
  const WelcomeV2Screen({super.key, required this.onSignIn, required this.onGetDevice});

  final VoidCallback onSignIn;
  final VoidCallback onGetDevice;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      header: const DfHeroArt(height: 380, product: true),
      spacing: 12,
      children: <Widget>[
        Text('Say hello to Omi', textAlign: TextAlign.center, style: t.label(size: 14, color: t.textTertiary)),
        const DfHeadline('Capture your day, remember everything, & act on it', size: 28, align: TextAlign.center),
        const Spacer(),
        DfButton('Continue with Apple', onPressed: onSignIn),
        DfButton('Continue with Google', onPressed: onSignIn),
        DfButton('Continue with email', onPressed: onSignIn, kind: DfButtonKind.text),
        Wrap(
          alignment: WrapAlignment.center,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            Text("Don't have a device? ", style: t.body(size: 13, color: t.textTertiary)),
            GestureDetector(
              onTap: onGetDevice,
              child: Text(
                'Get one now',
                style: t.body(size: 13, color: _linkColor(t), weight: FontWeight.w600),
              ),
            ),
          ],
        ),
        const DfCaption("By continuing you agree to Omi's Terms and acknowledge the Privacy Policy."),
      ],
    );
  }
}

Color _linkColor(DfTheme t) => t.glow?.first ?? t.text;

/// The five things Unlimited does, shown as a swipeable carousel.
const List<(IconData, String, String, String, String)> _features = <(IconData, String, String, String, String)>[
  (
    Icons.notes_rounded,
    'Summary',
    'Never lose what matters from a conversation',
    'Decisions, follow-ups and who said what, written up the moment you stop talking.',
    'Unlimited summaries, saved forever',
  ),
  (
    Icons.graphic_eq_rounded,
    'Live transcript',
    'You: Can we move the launch to Thursday?',
    'Maya: Thursday works if QA signs off by Wednesday.',
    'Real-time transcripts with speaker names',
  ),
  (
    Icons.auto_awesome_rounded,
    'Ask Omi',
    'What did I promise Maya this morning?',
    'To send her the revised deck by Friday, and book QA for Wednesday.',
    'Ask anything about your day',
  ),
  (
    Icons.check_circle_outline_rounded,
    'Tasks',
    'Send the revised deck to Maya · Fri',
    'Book a QA review · Today',
    'Follow-ups pulled out for you',
  ),
  (
    Icons.psychology_outlined,
    'Memories',
    'Prefers deep work in the mornings',
    'Working on the seed round this quarter',
    'A memory that grows with you',
  ),
];

enum PaywallMode { onboarding, capHit }

/// 02 — The paywall, shown right after sign-in and before any setup.
///
/// "Try for $0.00" goes to web checkout (Stripe, no App Store fee);
/// "Try with App Store" uses In-App Purchase. Closing it triggers the winback.
class PaywallV2Screen extends StatefulWidget {
  const PaywallV2Screen({
    super.key,
    required this.trialDays,
    required this.today,
    required this.onTryWeb,
    required this.onTryAppStore,
    required this.onClose,
    this.mode = PaywallMode.onboarding,
  });

  final int trialDays;
  final DateTime today;
  final VoidCallback onTryWeb;
  final VoidCallback onTryAppStore;
  final VoidCallback onClose;
  final PaywallMode mode;

  @override
  State<PaywallV2Screen> createState() => _PaywallV2ScreenState();
}

class _PaywallV2ScreenState extends State<PaywallV2Screen> {
  final PageController _pages = PageController(viewportFraction: 0.9);
  int _page = 0;

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final capHit = widget.mode == PaywallMode.capHit;
    return DfPage(
      wash: true,
      spacing: 12,
      children: <Widget>[
        Row(
          children: <Widget>[
            const SizedBox(width: 48),
            Expanded(
              child: Center(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    DfOmiMark(size: 15, color: t.textTertiary),
                    const SizedBox(width: 6),
                    Text('Unlimited', style: t.label(size: 15, color: t.textTertiary, weight: FontWeight.w600)),
                  ],
                ),
              ),
            ),
            IconButton(
              tooltip: 'Close',
              onPressed: widget.onClose,
              icon: Icon(Icons.close, color: t.textTertiary),
            ),
          ],
        ),
        if (capHit) Center(child: DfEyebrow('300 of 300 free minutes used', color: t.danger)),
        _PaywallTitle(capHit: capHit),
        SizedBox(
          height: 206,
          child: PageView.builder(
            controller: _pages,
            itemCount: _features.length,
            onPageChanged: (i) => setState(() => _page = i),
            itemBuilder: (context, i) => _FeatureCard(feature: _features[i]),
          ),
        ),
        _Dots(count: _features.length, index: _page),
        _TrialTimeline(trialDays: widget.trialDays, today: widget.today),
        const Spacer(),
        DfButton(r'Try for $0.00', onPressed: widget.onTryWeb),
        DfButton('Try with App Store', onPressed: widget.onTryAppStore, kind: DfButtonKind.secondary),
        Text(
          'Cancel anytime, no penalties or fees',
          textAlign: TextAlign.center,
          style: t.body(size: 13, color: t.success, weight: FontWeight.w500),
        ),
      ],
    );
  }
}

class _PaywallTitle extends StatelessWidget {
  const _PaywallTitle({required this.capHit});

  final bool capHit;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final style = t.headline(26);
    if (capHit) {
      return Text('Keep Omi listening in real time.', textAlign: TextAlign.center, style: style);
    }
    return Text.rich(
      TextSpan(
        style: style,
        children: <InlineSpan>[
          const TextSpan(text: 'How your '),
          TextSpan(
            text: 'free',
            style: style.copyWith(
              decoration: TextDecoration.underline,
              decorationStyle: TextDecorationStyle.wavy,
              decorationColor: _linkColor(t),
              decorationThickness: 1.4,
            ),
          ),
          const TextSpan(text: ' trial works.'),
        ],
      ),
      textAlign: TextAlign.center,
    );
  }
}

class _FeatureCard extends StatelessWidget {
  const _FeatureCard({required this.feature});

  final (IconData, String, String, String, String) feature;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final (icon, title, line1, line2, caption) = feature;
    final glow = t.glow;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 5),
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        color: glow == null ? t.surface2 : null,
        gradient: glow == null
            ? null
            : LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: <Color>[glow[0], glow[1], glow[2].withValues(alpha: 0.95)],
              ),
      ),
      child: Column(
        children: <Widget>[
          Expanded(
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                boxShadow: <BoxShadow>[BoxShadow(color: Colors.black.withValues(alpha: 0.12), blurRadius: 12)],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Icon(icon, size: 16, color: const Color(0xFF111114)),
                      const SizedBox(width: 6),
                      Text(
                        title,
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111114)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    line1,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF111114)),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    line2,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 11, height: 1.35, color: Color(0xFF5E5E6A)),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            caption,
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: glow == null ? t.text : Colors.white,
            ),
          ),
        ],
      ),
    );
  }
}

class _Dots extends StatelessWidget {
  const _Dots({required this.count, required this.index});

  final int count;
  final int index;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        for (var i = 0; i < count; i++)
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: i == index ? 16 : 6,
            height: 6,
            margin: const EdgeInsets.symmetric(horizontal: 3),
            decoration: BoxDecoration(
              color: i == index ? t.text : t.border,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
      ],
    );
  }
}

/// Dated trial timeline: today, trial length, reminder, trial end.
class _TrialTimeline extends StatelessWidget {
  const _TrialTimeline({required this.trialDays, required this.today});

  final int trialDays;
  final DateTime today;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final reminder = DfOffer.reminderDayFor(trialDays);
    final rows = <(IconData, String, String, DateTime)>[
      (Icons.lock_open_rounded, 'Today', 'Unlock every Unlimited feature.', today),
      (
        Icons.card_giftcard_rounded,
        '+${DfOffer.trialPhrase(trialDays)} free',
        '${DfOffer.trialPhrase(trialDays)} of Unlimited, on us.',
        today.add(Duration(days: trialDays)),
      ),
      (
        Icons.notifications_none_rounded,
        'In $reminder days',
        "We'll remind you before your trial ends.",
        today.add(Duration(days: reminder)),
      ),
      (
        Icons.check_circle_outline_rounded,
        'In $trialDays days',
        "Trial ends. You'll be charged unless you cancel.",
        today.add(Duration(days: trialDays)),
      ),
    ];
    final glow = t.glow;
    return Column(
      children: <Widget>[
        for (var i = 0; i < rows.length; i++)
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Column(
                children: <Widget>[
                  Container(
                    width: 30,
                    height: 30,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: i < 2 && glow != null ? null : t.surface2,
                      gradient: i < 2 && glow != null ? LinearGradient(colors: glow) : null,
                    ),
                    child: Icon(rows[i].$1, size: 16, color: i < 2 && glow != null ? Colors.white : t.text),
                  ),
                  if (i < rows.length - 1)
                    Container(
                      width: 2,
                      height: 18,
                      color: i == 0 && glow != null ? glow[1].withValues(alpha: 0.5) : t.border,
                    ),
                ],
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(rows[i].$2, style: t.label(size: 14, weight: FontWeight.w600)),
                      Text(rows[i].$3, style: t.body(size: 12, color: t.textTertiary, height: 1.3)),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Container(
                margin: const EdgeInsets.only(top: 4),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: t.surface2, borderRadius: BorderRadius.circular(8)),
                child: Text(dfShortDate(rows[i].$4), style: t.label(size: 11, color: t.textSecondary)),
              ),
            ],
          ),
      ],
    );
  }
}

/// 03 — "Pay via web": Stripe checkout with Apple Pay and card, $0 today.
class WebCheckoutSheet extends StatelessWidget {
  const WebCheckoutSheet({
    super.key,
    required this.trialDays,
    required this.today,
    required this.onConfirm,
    required this.onClose,
  });

  final int trialDays;
  final DateTime today;
  final VoidCallback onConfirm;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final ends = dfLongDate(today.add(Duration(days: trialDays)));
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _SheetHeader(title: 'Pay via web', onClose: onClose),
          const SizedBox(height: 8),
          const Align(alignment: Alignment.centerLeft, child: DfOmiMark(size: 20)),
          const SizedBox(height: 14),
          Text('Omi Unlimited · Yearly', style: t.label(size: 16, weight: FontWeight.w600)),
          const SizedBox(height: 2),
          Text('Try free for ${DfOffer.trialPhrase(trialDays)}', style: t.headline(26)),
          Text('${DfPricing.yearly.replaceAll('/yr', '')} per year after trial', style: t.body(size: 14)),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              const Expanded(child: _Field(hint: 'Promo code')),
              const SizedBox(width: 8),
              TextButton(onPressed: () {}, child: Text('Apply', style: t.label(weight: FontWeight.w600))),
            ],
          ),
          const SizedBox(height: 10),
          _AmountRow(label: 'After trial ends on $ends', amount: r'$269.00'),
          _AmountRow(label: 'Total due today', amount: r'$0.00', strong: true),
          const SizedBox(height: 16),
          _ApplePayButton(onPressed: onConfirm),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              Expanded(child: Divider(color: t.border)),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10),
                child: Text('OR PAY BY CARD', style: t.eyebrow()),
              ),
              Expanded(child: Divider(color: t.border)),
            ],
          ),
          const SizedBox(height: 10),
          const _Field(hint: 'Email'),
          const SizedBox(height: 8),
          const _Field(hint: 'Card number', icon: Icons.credit_card),
          const SizedBox(height: 8),
          const Row(
            children: <Widget>[
              Expanded(child: _Field(hint: 'MM / YY')),
              SizedBox(width: 8),
              Expanded(child: _Field(hint: 'CVC')),
            ],
          ),
          const SizedBox(height: 14),
          DfButton('Start trial', onPressed: onConfirm),
          const SizedBox(height: 10),
          DfCaption(
            "You won't be charged today. After your trial ends on $ends you'll pay \$269.00 a year until you "
            'cancel. Secure checkout by Stripe.',
          ),
        ],
      ),
    );
  }
}

/// 04 — The App Store purchase sheet (In-App Purchase).
class AppStoreSheet extends StatelessWidget {
  const AppStoreSheet({
    super.key,
    required this.trialDays,
    required this.today,
    required this.onConfirm,
    required this.onClose,
  });

  final int trialDays;
  final DateTime today;
  final VoidCallback onConfirm;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final glow = t.glow;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _SheetHeader(title: 'App Store', onClose: onClose, leftAligned: true),
          const SizedBox(height: 8),
          DfCard(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Container(
                      width: 46,
                      height: 46,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(11),
                        color: glow == null ? t.text : null,
                        gradient: glow == null ? null : LinearGradient(colors: glow),
                      ),
                      padding: const EdgeInsets.all(6),
                      child: const FittedBox(child: DfOmiMark(size: 11, color: Colors.white)),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text('Omi Unlimited', style: t.label(weight: FontWeight.w600)),
                          Text('Omi – AI wearable', style: t.body(size: 13, color: t.textTertiary)),
                          Text('Subscription', style: t.body(size: 13, color: t.textTertiary)),
                        ],
                      ),
                    ),
                  ],
                ),
                Divider(height: 24, color: t.border),
                Text('${DfOffer.trialPhrase(trialDays)} free trial', style: t.label(weight: FontWeight.w600)),
                Text('Starting today', style: t.body(size: 13, color: t.textTertiary)),
                const SizedBox(height: 8),
                Text(r'$269.00 per year', style: t.label(weight: FontWeight.w600)),
                Text(
                  'Starting ${dfLongDate(today.add(Duration(days: trialDays)))}',
                  style: t.body(size: 13, color: t.textTertiary),
                ),
                const SizedBox(height: 10),
                Text(
                  'No commitment. Cancel anytime in Settings > Apple Account at least a day before each '
                  'renewal date. Plan automatically renews until cancelled.',
                  style: t.body(size: 12, color: t.textTertiary, height: 1.35),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          DfButton('Subscribe', onPressed: onConfirm),
          const SizedBox(height: 8),
          const DfCaption('Confirm with Side Button'),
        ],
      ),
    );
  }
}

/// 05 — Winback, shown once when the paywall is closed: the trial is
/// "upgraded" to 30 days.
class WinbackCard extends StatelessWidget {
  const WinbackCard({
    super.key,
    required this.originalDays,
    required this.today,
    required this.onClaim,
    required this.onClaimAppStore,
    required this.onDecline,
    required this.onViewPlans,
  });

  final int originalDays;
  final DateTime today;
  final VoidCallback onClaim;
  final VoidCallback onClaimAppStore;
  final VoidCallback onDecline;
  final VoidCallback onViewPlans;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    const days = DfOffer.winbackDays;
    final until = dfLongDate(today.add(const Duration(days: days)));
    return Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _Ticket(originalDays: originalDays, until: until),
          const SizedBox(height: 20),
          DfHeadline("You've been upgraded to\n$days days free", size: 26, align: TextAlign.center),
          const SizedBox(height: 6),
          Text(
            'No charge until $until, then ${DfPricing.yearly}.',
            textAlign: TextAlign.center,
            style: t.body(size: 13, color: t.textTertiary),
          ),
          Center(
            child: TextButton(
              onPressed: onViewPlans,
              child: Text(
                'View all plans',
                style: t.body(size: 13, color: t.textSecondary).copyWith(decoration: TextDecoration.underline),
              ),
            ),
          ),
          const SizedBox(height: 4),
          DfButton('Claim my $days-day trial', onPressed: onClaim),
          const SizedBox(height: 10),
          DfButton('Claim with App Store', onPressed: onClaimAppStore, kind: DfButtonKind.secondary),
          DfButton('No thanks', onPressed: onDecline, kind: DfButtonKind.text),
        ],
      ),
    );
  }
}

class _Ticket extends StatelessWidget {
  const _Ticket({required this.originalDays, required this.until});

  final int originalDays;
  final String until;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final glow = t.glow;
    return Stack(
      children: <Widget>[
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            color: glow == null ? t.surface2 : null,
            gradient: glow == null
                ? null
                : LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: glow),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      'Free trial',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: _onTicket(t)),
                    ),
                  ),
                  Text('Until $until', style: TextStyle(fontSize: 12, color: _onTicket(t))),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                '$originalDays days',
                style: TextStyle(
                  fontSize: 18,
                  color: _onTicket(t).withValues(alpha: 0.75),
                  decoration: TextDecoration.lineThrough,
                  decorationColor: _onTicket(t),
                ),
              ),
              Text(
                '${DfOffer.winbackDays} days',
                style: t.headline(40).copyWith(color: _onTicket(t)),
              ),
            ],
          ),
        ),
        for (final side in <double>[-1, 1])
          Positioned.fill(
            child: Align(
              alignment: Alignment(side * 1.06, 0.15),
              child: Container(
                width: 20,
                height: 20,
                decoration: BoxDecoration(color: t.surface, shape: BoxShape.circle),
              ),
            ),
          ),
      ],
    );
  }
}

Color _onTicket(DfTheme t) => t.hasGlow ? Colors.white : t.text;

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({required this.title, required this.onClose, this.leftAligned = false});

  final String title;
  final VoidCallback onClose;
  final bool leftAligned;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final close = IconButton(
      tooltip: 'Close',
      onPressed: onClose,
      icon: Icon(Icons.close, color: t.textSecondary),
    );
    if (leftAligned) {
      return Row(
        children: <Widget>[
          Expanded(child: Text(title, style: t.label(size: 20, weight: FontWeight.w700))),
          close,
        ],
      );
    }
    return Row(
      children: <Widget>[
        close,
        Expanded(
          child: Text(title, textAlign: TextAlign.center, style: t.label(weight: FontWeight.w600)),
        ),
        const SizedBox(width: 48),
      ],
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.hint, this.icon});

  final String hint;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final icon = this.icon;
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: t.border),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: TextField(
              cursorColor: t.accent,
              style: t.label(),
              decoration: InputDecoration(
                border: InputBorder.none,
                isCollapsed: true,
                hintText: hint,
                hintStyle: t.label(color: t.textTertiary),
              ),
            ),
          ),
          if (icon != null) Icon(icon, size: 18, color: t.textTertiary),
        ],
      ),
    );
  }
}

class _AmountRow extends StatelessWidget {
  const _AmountRow({required this.label, required this.amount, this.strong = false});

  final String label;
  final String amount;
  final bool strong;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final weight = strong ? FontWeight.w600 : FontWeight.w400;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: <Widget>[
          Expanded(
              child: Text(label, style: t.label(size: 14, weight: weight, color: strong ? t.text : t.textSecondary))),
          Text(amount, style: t.label(size: 14, weight: weight)),
        ],
      ),
    );
  }
}

class _ApplePayButton extends StatelessWidget {
  const _ApplePayButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Semantics(
      button: true,
      label: 'Pay with Apple Pay',
      child: Material(
        color: t.accent,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onPressed,
          child: SizedBox(
            height: 50,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Icon(Icons.apple, color: t.onAccent, size: 22),
                const SizedBox(width: 2),
                Text('Pay', style: t.label(size: 19, weight: FontWeight.w600, color: t.onAccent)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 06 — Permissions, after the paywall ("Let's set you up for the best Omi
/// experience"). Bluetooth is required to pair.
class SetupPermissionsScreen extends StatefulWidget {
  const SetupPermissionsScreen({super.key, required this.onContinue});

  final VoidCallback onContinue;

  @override
  State<SetupPermissionsScreen> createState() => _SetupPermissionsScreenState();
}

class _SetupPermissionsScreenState extends State<SetupPermissionsScreen> {
  static const List<(String, IconData, String, String, bool)> _items = <(String, IconData, String, String, bool)>[
    ('bluetooth', Icons.bluetooth, 'Bluetooth', 'Connect instantly to your Omi', true),
    ('location', Icons.near_me_outlined, 'Location', 'Notes where conversations happened', false),
    ('notifications', Icons.notifications_none, 'Notifications', 'Summaries, reminders and replies', false),
  ];

  final Set<String> _on = <String>{};

  Future<void> _toggle(String id, bool value) async {
    if (!value) {
      setState(() => _on.remove(id));
      return;
    }
    if (id == 'bluetooth') {
      final allowed = await _askBluetooth();
      if (allowed != true) return;
    }
    if (mounted) setState(() => _on.add(id));
  }

  /// Stands in for the iOS system prompt.
  Future<bool?> _askBluetooth() {
    final t = DfThemeScope.of(context);
    return showDialog<bool>(
      context: context,
      builder: (dialogContext) => DfThemeScope(
        theme: t,
        child: Dialog(
          backgroundColor: t.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(Icons.bluetooth, size: 32, color: t.text),
                const SizedBox(height: 10),
                Text(
                  'Allow “Omi” to find Bluetooth devices?',
                  textAlign: TextAlign.center,
                  style: t.label(size: 16, weight: FontWeight.w600),
                ),
                const SizedBox(height: 6),
                Text(
                  'Omi uses Bluetooth to connect to your pendant and sync recordings when a conversation ends.',
                  textAlign: TextAlign.center,
                  style: t.body(size: 13),
                ),
                const SizedBox(height: 16),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: DfButton(
                        "Don't Allow",
                        onPressed: () => Navigator.of(dialogContext).pop(false),
                        kind: DfButtonKind.secondary,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(child: DfButton('Allow', onPressed: () => Navigator.of(dialogContext).pop(true))),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      wash: true,
      children: <Widget>[
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Text('Set up your', style: t.label(size: 14, color: t.textTertiary)),
            const SizedBox(width: 6),
            DfOmiMark(size: 13, color: t.textTertiary),
          ],
        ),
        const DfHeadline("Let's set you up for the best Omi experience", size: 28, align: TextAlign.center),
        DfCard(
          child: Column(
            children: <Widget>[
              for (final (id, icon, title, detail, required) in _items)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  child: Row(
                    children: <Widget>[
                      Icon(icon, size: 20, color: t.text),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(required ? '$title *' : title, style: t.label(weight: FontWeight.w600)),
                            Text(detail, style: t.body(size: 12, color: t.textTertiary)),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      DfToggle(value: _on.contains(id), onChanged: (value) => _toggle(id, value)),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const Spacer(),
        DfButton('Continue', onPressed: _on.contains('bluetooth') ? widget.onContinue : null),
        const DfCaption('* Bluetooth is needed to connect your Omi.'),
      ],
    );
  }
}

/// 07 — Dark interstitial before pairing: "Let's get your Omi set up".
class SetupIntroScreen extends StatelessWidget {
  const SetupIntroScreen({super.key, required this.onContinue, required this.onNoDevice});

  final VoidCallback onContinue;
  final VoidCallback onNoDevice;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final glow = t.glow ?? DfTheme.aurora.glow!;
    return DfThemeScope(
      theme: DfTheme.aurora,
      child: DfStatusBar(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: <Color>[
                const Color(0xFF050507),
                const Color(0xFF050507),
                glow[0].withValues(alpha: 0.55),
                glow[1].withValues(alpha: 0.85),
              ],
              stops: const <double>[0, 0.5, 0.82, 1],
            ),
          ),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 16, 24, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const Spacer(flex: 3),
                  Text(
                    "Let's get your Omi set up",
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: DfTheme.serifFamily,
                      fontSize: 34,
                      height: 1.1,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    "We'll walk you through turning it on and connecting it to your phone.",
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 15, height: 1.4, color: Colors.white.withValues(alpha: 0.7)),
                  ),
                  const Spacer(flex: 4),
                  DfButton('Continue', onPressed: onContinue),
                  const SizedBox(height: 8),
                  DfButton("I don't have my Omi yet", onPressed: onNoDevice, kind: DfButtonKind.text),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
