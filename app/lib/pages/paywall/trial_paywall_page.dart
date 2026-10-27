import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Variant `trial`: a free-trial paywall shown once right after sign-up. A feature carousel, a
/// timeline of what happens on which date, the Unlimited feature list, month/year, and a
/// "Try for $0.00" button that opens the shared Stripe checkout with a trial. Light canvas on
/// purpose: it sits between the light onboarding steps. Prices come from the catalog.
class TrialPaywallPage extends StatefulWidget {
  const TrialPaywallPage({super.key, required this.source, this.offer, this.checkout, this.now});

  /// Days before the first charge; the backend only honors it for a first-time subscriber.
  static const int trialDays = 7;

  final String source;

  /// Test seam: a fixed offer instead of the provider's catalog.
  final PaywallOffer? offer;

  /// Test seam: replaces [PaywallCheckout.start].
  final Future<PaywallCheckoutOutcome> Function(BuildContext context, PaywallPrice price, String tierId)? checkout;

  /// Test seam: the clock the timeline dates are computed from.
  final DateTime? now;

  @override
  State<TrialPaywallPage> createState() => _TrialPaywallPageState();
}

class _TrialPaywallPageState extends State<TrialPaywallPage> {
  final _slides = PageController(viewportFraction: 0.86);
  int _slide = 0;
  bool _yearly = true;
  bool _busy = false;
  bool _dismissed = false;

  @override
  void initState() {
    super.initState();
    if (widget.offer == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final usage = context.read<UsageProvider>();
        if (usage.availablePlans == null) usage.loadAvailablePlans();
      });
    }
  }

  @override
  void dispose() {
    _slides.dispose();
    super.dispose();
  }

  /// One operation at a time: a checkout or restore in flight owns the page until it settles, and
  /// nothing that settles after a dismissal may navigate again.
  bool get _locked => _busy || _dismissed;

  void _dismiss() {
    if (_locked) return;
    _dismissed = true;
    PlatformManager.instance.analytics.upgradeModalDismissed();
    Navigator.of(context).pop(false);
  }

  Future<void> _restore() async {
    if (_locked) return;
    setState(() => _busy = true);
    try {
      final usage = context.read<UsageProvider>();
      await usage.fetchSubscription();
      if (!mounted || _dismissed) return;
      final l10n = context.l10n;
      if (usage.subscription?.subscription.plan.isPaid == true) {
        OmiFeedback.confirm(context, l10n.unlimitedPlan);
        _dismissed = true;
        Navigator.of(context).pop(true);
        return;
      }
      OmiFeedback.info(context, l10n.freePlan);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _purchase(PaywallOffer offer) async {
    final price = _yearly ? (offer.yearly ?? offer.monthly) : (offer.monthly ?? offer.yearly);
    if (price == null || _locked) return;
    // Never open a checkout that would charge at once under a $0 trial button.
    if (widget.checkout == null && context.read<UsageProvider>().subscription?.trialEligible != true) {
      OmiFeedback.error(context, context.l10n.couldNotProcessSubscription);
      return;
    }
    setState(() => _busy = true);
    try {
      final start = widget.checkout ??
          (BuildContext context, PaywallPrice price, String tierId) => PaywallCheckout.start(
                context,
                priceId: price.priceId,
                plan: tierId,
                interval: price.interval,
                source: widget.source,
                trialDays: TrialPaywallPage.trialDays,
              );
      final outcome = await start(context, price, offer.tierId);
      if (!mounted || _dismissed) return;
      if (outcome == PaywallCheckoutOutcome.purchased) {
        _dismissed = true;
        Navigator.of(context).pop(true);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  static String _money(int minor, String currency) =>
      NumberFormat.simpleCurrency(name: currency.toUpperCase(), decimalDigits: 2).format(minor / 100);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final top = MediaQuery.paddingOf(context).top;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final now = widget.now ?? DateTime.now();
    final dateFormat = DateFormat.yMMMd(Localizations.localeOf(context).toString());
    String onDay(int days) => dateFormat.format(now.add(Duration(days: days)));
    final slides = _slideSpecs(l10n);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        // Popped from outside (the host navigated away): the widget stays mounted through the exit
        // animation, so mark it dismissed now and let any pending checkout or restore settle silently.
        if (didPop) {
          _dismissed = true;
          return;
        }
        _dismiss();
      },
      child: Scaffold(
        backgroundColor: _Paper.background,
        body: Consumer<UsageProvider>(
          builder: (context, usage, _) {
            final offer = widget.offer ?? PaywallOffer.fromCatalog(usage.availablePlans);
            final loading = offer == null && widget.offer == null && usage.isLoadingPlans;
            final yearly = offer?.yearly;
            final monthly = offer?.monthly;
            final currency = (yearly ?? monthly)?.currency ?? 'usd';
            final zero = _money(0, currency);
            final yearlySaving = yearly != null && monthly != null && monthly.amountMinor * 12 > yearly.amountMinor
                ? monthly.amountMinor * 12 - yearly.amountMinor
                : null;
            return Column(
              children: [
                Expanded(
                  child: ListView(
                    padding: EdgeInsets.fromLTRB(0, top + 8, 0, 16),
                    children: [
                      _Header(onClose: _dismiss, onRestore: _restore, brand: l10n.paywallTrialBrand),
                      const SizedBox(height: 18),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 24),
                        child: Text(l10n.paywallTrialHeadline, textAlign: TextAlign.center, style: _Paper.headline(30)),
                      ),
                      const SizedBox(height: 20),
                      SizedBox(
                        height: 250,
                        child: PageView.builder(
                          controller: _slides,
                          itemCount: slides.length,
                          onPageChanged: (index) => setState(() => _slide = index),
                          itemBuilder: (context, index) => Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 6),
                            child: _SlideCard(spec: slides[index]),
                          ),
                        ),
                      ),
                      const SizedBox(height: 14),
                      _Dots(count: slides.length, current: _slide),
                      const SizedBox(height: 22),
                      _Card(
                        child: Column(
                          children: [
                            _TimelineRow(
                              icon: Icons.lock_open_rounded,
                              title: l10n.paywallTrialTodayTitle,
                              body: l10n.paywallTrialTodayBody,
                              date: onDay(0),
                              emphasis: _TimelineEmphasis.first,
                            ),
                            _TimelineRow(
                              icon: Icons.add_circle_outline_rounded,
                              title: l10n.paywallTrialFreeDaysTitle(TrialPaywallPage.trialDays),
                              body: l10n.paywallTrialFreeDaysBody(TrialPaywallPage.trialDays),
                              date: onDay(TrialPaywallPage.trialDays),
                              emphasis: _TimelineEmphasis.accent,
                            ),
                            _TimelineRow(
                              icon: Icons.check_circle_outline_rounded,
                              title: l10n.paywallTrialInDaysTitle(TrialPaywallPage.trialDays),
                              body: l10n.paywallTrialEndsBody,
                              date: onDay(TrialPaywallPage.trialDays),
                              emphasis: _TimelineEmphasis.plain,
                              last: true,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      _Card(
                        child: Column(
                          children: [
                            _FeatureRow(icon: Icons.description_outlined, label: l10n.paywallTrialSlideSummariesTitle),
                            _FeatureRow(
                                icon: Icons.graphic_eq_rounded, label: l10n.paywallTrialSlideTranscriptionTitle),
                            _FeatureRow(icon: Icons.auto_awesome_outlined, label: l10n.paywallTrialFeatureModels),
                            _FeatureRow(
                                icon: Icons.record_voice_over_outlined, label: l10n.paywallTrialSlideSpeakersTitle),
                            _FeatureRow(
                                icon: Icons.chat_bubble_outline_rounded,
                                label: l10n.paywallTrialFeatureAsk,
                                last: true),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: loading
                            ? const Row(children: [
                                Expanded(child: _Skeleton(height: 96)),
                                SizedBox(width: 10),
                                Expanded(child: _Skeleton(height: 96)),
                              ])
                            : offer == null
                                ? Text(l10n.unableToLoadPlans, textAlign: TextAlign.center, style: _Paper.body())
                                : IntrinsicHeight(
                                    child: Row(
                                      crossAxisAlignment: CrossAxisAlignment.stretch,
                                      children: [
                                        if (monthly != null)
                                          Expanded(
                                            child: _PlanCard(
                                              key: const Key('trial_paywall_monthly'),
                                              title: l10n.billingMonthly,
                                              price: _money(monthly.amountMinor, monthly.currency),
                                              footnote: l10n.paywallTrialBilledMonthly,
                                              selected: !_yearly || yearly == null,
                                              onTap: () => setState(() => _yearly = false),
                                            ),
                                          ),
                                        if (monthly != null && yearly != null) const SizedBox(width: 10),
                                        if (yearly != null)
                                          Expanded(
                                            child: _PlanCard(
                                              key: const Key('trial_paywall_yearly'),
                                              title: l10n.billingYearly,
                                              price: _money(yearly.amountMinor, yearly.currency),
                                              wasPrice: monthly == null
                                                  ? null
                                                  : _money(monthly.amountMinor * 12, monthly.currency),
                                              footnote: l10n.paywallTrialBilledYearly,
                                              saving: yearlySaving == null
                                                  ? null
                                                  : l10n.paywallTrialSaveAmount(_money(yearlySaving, yearly.currency)),
                                              selected: _yearly || monthly == null,
                                              onTap: () => setState(() => _yearly = true),
                                            ),
                                          ),
                                      ],
                                    ),
                                  ),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: EdgeInsets.fromLTRB(20, 8, 20, bottom + 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _Button(
                        key: const Key('trial_paywall_cta'),
                        label: l10n.paywallTrialCta(zero),
                        busy: _busy,
                        onPressed: offer == null || _busy ? null : () => _purchase(offer),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        l10n.paywallTrialCancelNote,
                        textAlign: TextAlign.center,
                        style: _Paper.label(size: 13, color: _Paper.success, weight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  List<_SlideSpec> _slideSpecs(dynamic l10n) => [
        _SlideSpec(
          caption: l10n.paywallTrialSlideSummariesTitle,
          colors: const [Color(0xFF1F2937), Color(0xFF4B5563)], // omi-ux-allow: color-literal -- fixed card gradient
          art: _SummaryArt(title: l10n.paywallTrialSlideSummariesTitle, body: l10n.paywallTrialSlideSummariesBody),
        ),
        _SlideSpec(
          caption: l10n.paywallTrialSlideTranscriptionTitle,
          colors: const [Color(0xFF5CC8F5), Color(0xFF5B7CF0)], // omi-ux-allow: color-literal -- fixed card gradient
          art: _ChipArt(labels: [
            l10n.paywallTrialChipDetails,
            l10n.paywallTrialChipSpeakers,
            l10n.paywallTrialChipNoise,
            l10n.paywallTrialChipAccents,
            l10n.paywallTrialChipJargon,
          ]),
        ),
        _SlideSpec(
          caption: l10n.paywallTrialSlideSpeakersTitle,
          colors: const [Color(0xFF7ED957), Color(0xFF2FB24C)], // omi-ux-allow: color-literal -- fixed card gradient
          art: const _SpeakersArt(),
        ),
        _SlideSpec(
          caption: l10n.paywallTrialSlideAskTitle,
          colors: const [Color(0xFFF5A35C), Color(0xFFE85D5D)], // omi-ux-allow: color-literal -- fixed card gradient
          art: _BubbleArt(lines: [
            l10n.paywallTrialBubbleFollowUp,
            l10n.paywallTrialBubbleConflicts,
            l10n.paywallTrialBubbleBlockers,
          ]),
        ),
        _SlideSpec(
          caption: l10n.paywallTrialSlideAppsTitle,
          colors: const [Color(0xFFD8E25A), Color(0xFFE2B23A)], // omi-ux-allow: color-literal -- fixed card gradient
          art: const _AppsArt(),
        ),
      ];
}

/// Light paper tokens for this one screen: it sits between the light onboarding pages.
abstract final class _Paper {
  static const background = Color(0xFFF5F5F7); // omi-ux-allow: color-literal -- fixed light design canvas
  static const card = Color(0xFFFFFFFF); // omi-ux-allow: color-literal -- fixed light design canvas
  static const border = Color(0xFFE5E5EA); // omi-ux-allow: color-literal -- fixed light design canvas
  static const text = Color(0xFF111111); // omi-ux-allow: color-literal -- fixed light design canvas
  static const textSecondary = Color(0xFF6E6E73); // omi-ux-allow: color-literal -- fixed light design canvas
  static const textTertiary = Color(0xFF9A9AA0); // omi-ux-allow: color-literal -- fixed light design canvas
  static const accent = Color(0xFF111111); // omi-ux-allow: color-literal -- fixed light design canvas
  static const onAccent = Color(0xFFFFFFFF); // omi-ux-allow: color-literal -- fixed light design canvas
  static const success = Color(0xFF2E9E4F); // omi-ux-allow: color-literal -- fixed light design canvas
  static const dateChip = Color(0xFFE8F0FE); // omi-ux-allow: color-literal -- fixed light design canvas
  static const dateText = Color(0xFF2F6FDB); // omi-ux-allow: color-literal -- fixed light design canvas
  static const ink = Color(0xFF1F2937); // omi-ux-allow: color-literal -- fixed light design canvas
  static const peach = Color(0xFFF59E8B); // omi-ux-allow: color-literal -- fixed light design canvas

  static TextStyle headline(double size) => TextStyle(
        fontSize: size,
        height: 1.1,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.02 * size,
        color: text,
      );

  static TextStyle body({double size = 15, Color? color, double height = 1.4}) =>
      TextStyle(fontSize: size, height: height, fontWeight: FontWeight.w400, color: color ?? textSecondary);

  static TextStyle label({double size = 15, Color? color, FontWeight weight = FontWeight.w500}) =>
      TextStyle(fontSize: size, fontWeight: weight, color: color ?? text);
}

class _Header extends StatelessWidget {
  const _Header({required this.onClose, required this.onRestore, required this.brand});

  final VoidCallback onClose;
  final VoidCallback onRestore;
  final String brand;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return SizedBox(
      height: 44,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(brand, style: _Paper.label(size: 19, color: _Paper.textTertiary, weight: FontWeight.w600)),
            ],
          ),
          Positioned(
            left: 8,
            child: TextButton(
              key: const Key('trial_paywall_restore'),
              onPressed: onRestore,
              child: Text(l10n.restoreAction, style: _Paper.label(size: 13, color: _Paper.textTertiary)),
            ),
          ),
          Positioned(
            right: 16,
            child: Material(
              color: _Paper.card,
              shape: const CircleBorder(),
              elevation: 0.5,
              child: IconButton(
                key: const Key('trial_paywall_close'),
                tooltip: l10n.useFreePlan,
                onPressed: onClose,
                icon: const Icon(Icons.close, color: _Paper.text, size: 20),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SlideSpec {
  const _SlideSpec({required this.caption, required this.colors, required this.art});

  final String caption;
  final List<Color> colors;
  final Widget art;
}

class _SlideCard extends StatelessWidget {
  const _SlideCard({required this.spec});

  final _SlideSpec spec;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(OmiRadius.xl),
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: spec.colors),
          ),
          child: Column(
            children: [
              // The art is designed at a fixed 280pt width and scaled down to whatever room the card
              // has, so a narrow phone or a three-line caption never overflows it.
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 18, 16, 0),
                  child: FittedBox(fit: BoxFit.scaleDown, child: SizedBox(width: 280, child: spec.art)),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 6, 16, 18),
                child: Text(
                  spec.caption,
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  style: _Paper.label(size: 21, color: _Paper.onAccent, weight: FontWeight.w700),
                ),
              ),
            ],
          ),
        ),
      );
}

class _SummaryArt extends StatelessWidget {
  const _SummaryArt({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.topCenter,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(OmiRadius.lg),
          child: Container(
            constraints: const BoxConstraints(maxWidth: 240),
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
            decoration: const BoxDecoration(color: _Paper.card),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: _Paper.label(size: 14, weight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(body, maxLines: 4, overflow: TextOverflow.fade, style: _Paper.body(size: 11, height: 1.35)),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      );
}

class _ChipArt extends StatelessWidget {
  const _ChipArt({required this.labels});

  final List<String> labels;

  @override
  Widget build(BuildContext context) => Center(
        child: Wrap(
          alignment: WrapAlignment.center,
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final label in labels)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(color: _Paper.card, borderRadius: BorderRadius.circular(OmiRadius.pill)),
                child: Text(label, style: _Paper.label(size: 12, weight: FontWeight.w600)),
              ),
          ],
        ),
      );
}

class _SpeakersArt extends StatelessWidget {
  const _SpeakersArt();

  @override
  Widget build(BuildContext context) {
    Widget bar(double fraction) => FractionallySizedBox(
          alignment: Alignment.centerLeft,
          widthFactor: fraction,
          child: Container(
            height: 7,
            decoration: BoxDecoration(
              color: _Paper.card.withValues(alpha: 0.55),
              borderRadius: BorderRadius.circular(OmiRadius.pill),
            ),
          ),
        );
    Widget row(String initial, String name, String time, Alignment pill) => Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              height: 54,
              padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
              decoration: BoxDecoration(
                color: _Paper.card.withValues(alpha: 0.35),
                borderRadius: BorderRadius.circular(OmiRadius.md),
              ),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [bar(0.85), const SizedBox(height: 6), bar(0.55)]),
            ),
            Positioned(
              right: 12,
              top: 6,
              child: Text(time, style: _Paper.label(size: 11, weight: FontWeight.w600)),
            ),
            Positioned(
              left: pill == Alignment.topLeft ? 8 : null,
              right: pill == Alignment.topRight ? 8 : null,
              top: -12,
              child: Container(
                padding: const EdgeInsets.fromLTRB(4, 3, 10, 3),
                decoration: BoxDecoration(color: _Paper.card, borderRadius: BorderRadius.circular(OmiRadius.pill)),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  CircleAvatar(
                    radius: 8,
                    backgroundColor: _Paper.success,
                    child: Text(initial, style: _Paper.label(size: 9, color: _Paper.onAccent, weight: FontWeight.w700)),
                  ),
                  const SizedBox(width: 5),
                  Text(name, style: _Paper.label(size: 12, weight: FontWeight.w700)),
                ]),
              ),
            ),
          ],
        );
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        row('J', 'John', '0:06', Alignment.topLeft), // omi-ux-allow: hardcoded-text -- illustration sample names
        const SizedBox(height: 22),
        row('A', 'Alex', '0:09', Alignment.topRight), // omi-ux-allow: hardcoded-text -- illustration sample names
      ],
    );
  }
}

class _BubbleArt extends StatelessWidget {
  const _BubbleArt({required this.lines});

  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    Widget bubble(String text, {double size = 12}) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
          decoration: BoxDecoration(color: _Paper.card, borderRadius: BorderRadius.circular(OmiRadius.lg)),
          child: Text(text, style: _Paper.label(size: size, weight: FontWeight.w500)),
        );
    // Two small bubbles share the row; the big one takes the width it has. Nothing here is a fixed
    // pixel width, so a 320pt phone lays out the same as a 430pt one.
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Flexible(child: bubble(lines[0], size: 11)),
            const SizedBox(width: 10),
            Flexible(child: bubble(lines[1], size: 11)),
          ],
        ),
        const SizedBox(height: 10),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 8), child: bubble(lines[2], size: 14)),
      ],
    );
  }
}

class _AppsArt extends StatelessWidget {
  const _AppsArt();

  @override
  Widget build(BuildContext context) {
    Widget tile(Widget child) => Container(
          width: 52,
          height: 52,
          decoration: BoxDecoration(color: _Paper.card, borderRadius: BorderRadius.circular(OmiRadius.md)),
          child: Center(child: child),
        );
    return Center(
      child: Wrap(
        spacing: 14,
        runSpacing: 14,
        alignment: WrapAlignment.center,
        children: [
          tile(Assets.images.googleLogo.image(width: 28, height: 28)),
          tile(Assets.images.calendarLogo.image(width: 30, height: 30)),
          tile(Assets.images.appleRemindersLogo.image(width: 30, height: 30)),
          tile(Assets.images.emailLogo.image(width: 28, height: 28)),
          tile(Assets.images.appleLogo.image(width: 26, height: 26)),
          tile(Assets.images.instagramLogo.image(width: 28, height: 28)),
        ],
      ),
    );
  }
}

class _Dots extends StatelessWidget {
  const _Dots({required this.count, required this.current});

  final int count;
  final int current;

  @override
  Widget build(BuildContext context) => Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          for (var i = 0; i < count; i++)
            AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              margin: const EdgeInsets.symmetric(horizontal: 4),
              width: 9,
              height: 9,
              decoration: BoxDecoration(shape: BoxShape.circle, color: i == current ? _Paper.text : _Paper.border),
            ),
        ],
      );
}

class _Card extends StatelessWidget {
  const _Card({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.symmetric(horizontal: 16),
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 6),
        decoration: BoxDecoration(color: _Paper.card, borderRadius: BorderRadius.circular(OmiRadius.xl)),
        child: child,
      );
}

enum _TimelineEmphasis { first, accent, plain }

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.icon,
    required this.title,
    required this.body,
    required this.date,
    required this.emphasis,
    this.last = false,
  });

  final IconData icon;
  final String title;
  final String body;
  final String date;
  final _TimelineEmphasis emphasis;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final ring = switch (emphasis) {
      _TimelineEmphasis.first => Border.all(color: _Paper.text, width: 1.2),
      _TimelineEmphasis.accent => null,
      _TimelineEmphasis.plain => Border.all(color: _Paper.border, width: 1),
    };
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 48,
            child: Column(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _Paper.card,
                    border: ring,
                    gradient: emphasis == _TimelineEmphasis.accent
                        ? const LinearGradient(colors: [_Paper.ink, _Paper.peach])
                        : null,
                  ),
                  child: emphasis == _TimelineEmphasis.accent
                      ? Container(
                          margin: const EdgeInsets.all(1.5),
                          decoration: const BoxDecoration(shape: BoxShape.circle, color: _Paper.card),
                          child: Icon(icon, size: 22, color: _Paper.ink),
                        )
                      : Icon(icon, size: 22, color: _Paper.text),
                ),
                if (!last)
                  Expanded(
                    child: Container(
                      width: 1.5,
                      color: emphasis == _TimelineEmphasis.first ? _Paper.text : _Paper.border,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Container(
              padding: const EdgeInsets.fromLTRB(0, 10, 0, 14),
              decoration: last ? null : const BoxDecoration(border: Border(bottom: BorderSide(color: _Paper.border))),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title, style: _Paper.label(size: 17, weight: FontWeight.w600)),
                        const SizedBox(height: 3),
                        Text(body, style: _Paper.body(size: 13)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration:
                        BoxDecoration(color: _Paper.dateChip, borderRadius: BorderRadius.circular(OmiRadius.sm)),
                    child: Text(date, style: _Paper.label(size: 12, color: _Paper.dateText, weight: FontWeight.w600)),
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

class _FeatureRow extends StatelessWidget {
  const _FeatureRow({required this.icon, required this.label, this.last = false});

  final IconData icon;
  final String label;
  final bool last;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: last ? null : const BoxDecoration(border: Border(bottom: BorderSide(color: _Paper.border))),
        child: Row(
          children: [
            Icon(icon, size: 24, color: _Paper.text),
            const SizedBox(width: 14),
            Expanded(child: Text(label, style: _Paper.label(size: 16, weight: FontWeight.w600))),
            const Icon(Icons.check_rounded, color: _Paper.success, size: 24),
          ],
        ),
      );
}

class _PlanCard extends StatelessWidget {
  const _PlanCard({
    super.key,
    required this.title,
    required this.price,
    required this.footnote,
    required this.selected,
    required this.onTap,
    this.wasPrice,
    this.saving,
  });

  final String title;
  final String price;
  final String? wasPrice;
  final String footnote;
  final String? saving;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final wasPrice = this.wasPrice;
    final saving = this.saving;
    return Semantics(
      selected: selected,
      button: true,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
          decoration: BoxDecoration(
            color: _Paper.card,
            borderRadius: BorderRadius.circular(OmiRadius.lg),
            border: Border.all(color: selected ? _Paper.text : _Paper.card, width: selected ? 1.5 : 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(title, style: _Paper.label(size: 14, weight: FontWeight.w500))),
                  Container(
                    width: 22,
                    height: 22,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: selected ? _Paper.text : _Paper.card,
                      border: Border.all(color: _Paper.text, width: 1.5),
                    ),
                    child: selected ? const Icon(Icons.check, size: 14, color: _Paper.onAccent) : null,
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.end,
                spacing: 6,
                children: [
                  if (wasPrice != null)
                    Text(
                      wasPrice,
                      style: _Paper.label(size: 14, color: _Paper.textTertiary)
                          .copyWith(decoration: TextDecoration.lineThrough),
                    ),
                  Text(price, style: _Paper.label(size: 22, weight: FontWeight.w700)),
                ],
              ),
              const SizedBox(height: 14),
              Text.rich(
                TextSpan(children: [
                  TextSpan(text: footnote, style: _Paper.body(size: 12, color: _Paper.textTertiary)),
                  if (saving != null) TextSpan(text: ' · ', style: _Paper.body(size: 12, color: _Paper.textTertiary)),
                  if (saving != null)
                    TextSpan(
                        text: saving, style: _Paper.label(size: 12, color: _Paper.success, weight: FontWeight.w600)),
                ]),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Button extends StatelessWidget {
  const _Button({super.key, required this.label, required this.onPressed, this.busy = false});

  final String label;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(OmiRadius.pill);
    return Opacity(
      opacity: onPressed == null && !busy ? 0.35 : 1,
      child: Material(
        color: _Paper.accent,
        shape: RoundedRectangleBorder(borderRadius: radius),
        child: InkWell(
          borderRadius: radius,
          onTap: onPressed,
          child: SizedBox(
            height: 56,
            child: Center(
              child: busy
                  ? const OmiSpinner(size: OmiSpinnerSize.small, color: _Paper.onAccent)
                  : Text(
                      label,
                      style: _Paper.label(size: 17, color: _Paper.onAccent, weight: FontWeight.w600),
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Skeleton extends StatelessWidget {
  const _Skeleton({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) => Container(
        height: height,
        decoration: BoxDecoration(color: _Paper.card, borderRadius: BorderRadius.circular(OmiRadius.lg)),
      );
}
