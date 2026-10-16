import 'package:flutter/material.dart';

import '../art.dart';
import '../content.dart';
import '../theme.dart';
import '../widgets.dart';

/// B1 — Get your Omi. Users without a device land here instead of a dead end.
class BuyOmiScreen extends StatelessWidget {
  const BuyOmiScreen({super.key, required this.onBuy, required this.onAlreadyOrdered, required this.onBack});

  final VoidCallback onBuy;
  final VoidCallback onAlreadyOrdered;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final top = MediaQuery.paddingOf(context).top;
    return DfPage(
      header: Stack(
        children: <Widget>[
          const DfHeroArt(height: 330, product: true),
          Positioned(
            left: 8,
            top: top + 8,
            child: IconButton(
              tooltip: 'Back',
              onPressed: onBack,
              icon: Icon(Icons.arrow_back_ios_new, size: 20, color: t.text),
            ),
          ),
        ],
      ),
      spacing: 12,
      children: <Widget>[
        const DfEyebrow('Omi pendant'),
        const DfHeadline('Omi works with its pendant.', size: 28),
        const DfBody("You'll need one to finish setting up the app."),
        Row(
          children: <Widget>[
            Text(DfPricing.devicePrice, style: t.headline(28)),
            const SizedBox(width: 10),
            Text(
              DfPricing.deviceList,
              style: t.body(size: 17, color: t.textTertiary).copyWith(decoration: TextDecoration.lineThrough),
            ),
            const SizedBox(width: 10),
            const DfBadge('Save ${DfPricing.deviceDiscount}'),
          ],
        ),
        Row(
          children: <Widget>[
            Icon(Icons.inventory_2_outlined, size: 18, color: t.textTertiary),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Pendant, case, lanyard and magnetic charger',
                style: t.body(size: 14, color: t.textTertiary),
              ),
            ),
          ],
        ),
        const Spacer(),
        DfButton('Buy Omi — ${DfPricing.devicePrice}', onPressed: onBuy),
        DfButton('I already ordered one', onPressed: onAlreadyOrdered, kind: DfButtonKind.text),
      ],
    );
  }
}

/// B2 — Order summary. Physical goods can't use In-App Purchase, so this
/// hands off to Apple Pay / Shop Pay (e.g. the existing store) — no App Store
/// cut on the device.
class CheckoutScreen extends StatelessWidget {
  const CheckoutScreen({super.key, required this.onPay, required this.onBack});

  final VoidCallback onPay;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        DfBackRow(onBack: onBack),
        const DfHeadline('Order summary', size: 30),
        DfCard(
          padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 8),
          child: Row(
            children: <Widget>[
              const _BoxItem(label: 'Pendant', child: DfPendant(size: 48, showCord: false)),
              _BoxItem(
                label: 'Case',
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: t.textTertiary, width: 5),
                  ),
                ),
              ),
              _BoxItem(
                label: 'Lanyard',
                child: Icon(Icons.all_inclusive, size: 40, color: t.textTertiary),
              ),
              _BoxItem(
                label: 'Charger',
                child: Icon(Icons.cable, size: 40, color: t.textTertiary),
              ),
            ],
          ),
        ),
        DfCard(
          child: Column(
            children: <Widget>[
              const DfListRow(label: 'Omi pendant', value: '${DfPricing.deviceList}.00'),
              DfListRow(label: 'Launch discount', value: '–${DfPricing.deviceDiscount}.00', valueColor: t.success),
              // Placeholder: shipping price and delivery window.
              const DfListRow(label: 'Shipping', value: 'Free'),
              DfListRow(label: 'Total', value: '${DfPricing.devicePrice}.00', emphasize: true, valueColor: t.text),
            ],
          ),
        ),
        Row(
          children: <Widget>[
            Icon(Icons.verified_user_outlined, size: 16, color: t.textTertiary),
            const SizedBox(width: 8),
            Expanded(
              child: Text('1-year limited warranty', style: t.body(size: 13, color: t.textTertiary)),
            ),
          ],
        ),
        const Spacer(),
        DfButton('Pay with Apple Pay', onPressed: onPay),
        const DfCaption('Or pay with card'),
      ],
    );
  }
}

class _BoxItem extends StatelessWidget {
  const _BoxItem({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Expanded(
      child: Column(
        children: <Widget>[
          SizedBox(height: 52, child: Center(child: child)),
          const SizedBox(height: 8),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: t.body(size: 12, color: t.textTertiary),
            ),
          ),
        ],
      ),
    );
  }
}

/// B3 — Waiting room. Where "It's on the way" and every buyer land, and where
/// the app opens until a device is paired. The only way forward is pairing.
class WaitingRoomScreen extends StatelessWidget {
  const WaitingRoomScreen({super.key, required this.onArrived, required this.onTrack});

  final VoidCallback onArrived;
  final VoidCallback onTrack;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        const Center(child: DfPendant(size: 120, showCord: false, glow: true)),
        const DfHeadline('Your Omi is on its way.'),
        const DfBody("You'll finish setting up as soon as it arrives. Pairing takes about a minute."),
        DfCard(
          child: Column(
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(
                  children: <Widget>[
                    // Placeholder: real order number and dates come from the store.
                    Text(
                      'Order #1042',
                      style: t.label(size: 13, weight: FontWeight.w600, color: t.textTertiary),
                    ),
                  ],
                ),
              ),
              DfListRow(icon: Icons.check_circle, iconColor: t.success, label: 'Ordered', value: 'Today'),
              DfListRow(
                icon: Icons.local_shipping_outlined,
                label: 'Shipped',
                value: 'Expected tomorrow',
                labelColor: t.textSecondary,
              ),
              DfListRow(icon: Icons.home_outlined, label: 'Delivered', value: 'In 3 days', labelColor: t.textSecondary),
            ],
          ),
        ),
        Row(
          children: <Widget>[
            Icon(Icons.notifications_none, size: 18, color: t.textTertiary),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                "We'll notify you the moment it's delivered.",
                style: t.body(size: 14, color: t.textTertiary),
              ),
            ),
          ],
        ),
        const Spacer(),
        DfButton('It arrived — pair my Omi', onPressed: onArrived),
        DfButton('Track order', onPressed: onTrack, kind: DfButtonKind.text),
      ],
    );
  }
}

/// B4 — Delivery push on the lock screen. Deep-links straight to pairing.
class ArrivalNotificationScreen extends StatelessWidget {
  const ArrivalNotificationScreen({super.key, required this.onOpen});

  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        ColoredBox(color: t.background),
        const Align(alignment: Alignment(0, 0.45), child: DfHeroArt(height: 420)),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Column(
              children: <Widget>[
                const SizedBox(height: 12),
                Text('Thursday, October 16', style: t.label(size: 17)),
                Text('9:41', style: t.headline(84)),
                const SizedBox(height: 12),
                Semantics(
                  button: true,
                  child: GestureDetector(
                    onTap: onOpen,
                    child: Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: t.surface.withValues(alpha: 0.9),
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Container(
                            width: 38,
                            height: 38,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: t.background,
                              borderRadius: BorderRadius.circular(9),
                              border: Border.all(color: t.border),
                            ),
                            child: Container(
                              width: 16,
                              height: 16,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(color: t.text, width: 3),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Row(
                                  children: <Widget>[
                                    Expanded(
                                      child: Text('Omi', style: t.label(size: 14, weight: FontWeight.w600)),
                                    ),
                                    Text('now', style: t.body(size: 13, color: t.textTertiary)),
                                  ],
                                ),
                                Text('Your Omi has arrived', style: t.label(weight: FontWeight.w600)),
                                Text(
                                  'Pair it in about a minute and start remembering.',
                                  style: t.body(size: 14, height: 1.35),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const Spacer(),
                const DfCaption('Tap the notification to open pairing'),
                const SizedBox(height: 12),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
