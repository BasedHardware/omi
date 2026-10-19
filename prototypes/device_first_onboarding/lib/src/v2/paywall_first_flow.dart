import 'package:flutter/material.dart';

import '../app/app_shell.dart';
import '../content.dart';
import '../screens/buy_screens.dart';
import '../screens/pairing_screens.dart';
import '../screens/setup_screens.dart';
import '../theme.dart';
import '../widgets.dart';
import 'paywall_first_screens.dart';

/// Every screen in the paywall-first flow, numbered as in the review deck.
enum V2Step {
  welcome('01 Welcome'),
  paywall('02 Paywall'),
  webCheckout('03 Pay via web'),
  appStore('04 App Store'),
  winback('05 Winback · 30 days'),
  permissions('06 Permissions'),
  setupIntro("07 Let's get your Omi set up"),
  find('08 Find your Omi'),
  found('09 Omi found'),
  paired('10 Paired'),
  name('11 Name'),
  voice('12 Voice introduction'),
  finishing('13 Setting up'),
  ready('14 Your Omi is ready'),
  buy('B1 Get your Omi'),
  checkout('B2 Order summary'),
  waiting('B3 Waiting room'),
  arrival('B4 Delivered push'),
  app('Home');

  const V2Step(this.title);

  final String title;
}

/// Pocket-style, paywall-first onboarding:
///
/// Welcome → **Paywall** → (close) **Winback, 30 days** → (no thanks)
/// soft onboarding → pair the Omi → the app.
///
/// Subscribing on either the paywall or the winback skips straight to
/// setup with a trial; declining both lands on Free. Pairing is still
/// required: without an Omi the user is sent to buy one.
class PaywallFirstFlow extends StatefulWidget {
  const PaywallFirstFlow({
    super.key,
    this.direction = DfDirection.auroraLight,
    required this.trial,
    this.today,
    this.initialStep = V2Step.welcome,
    this.searchDuration = const Duration(seconds: 3),
    this.onExit,
  });

  final DfDirection direction;

  /// Trial-length arm shown on the first paywall (the winback is always 30 days).
  final TrialLength trial;

  /// "Today" for the dated trial timeline; defaults to the real date.
  final DateTime? today;
  final V2Step initialStep;
  final Duration searchDuration;
  final VoidCallback? onExit;

  @override
  State<PaywallFirstFlow> createState() => _PaywallFirstFlowState();
}

class _PaywallFirstFlowState extends State<PaywallFirstFlow> {
  late V2Step _step = widget.initialStep;
  final List<V2Step> _history = <V2Step>[];
  late int _offerDays = widget.trial.days;
  bool _winbackShown = false;
  DfPlanState _plan = const DfPlanState.free();
  String _name = 'Alex';

  DateTime get _today => dfDay(widget.today ?? DateTime.now());

  void _go(V2Step next) => setState(() {
        _history.add(_step);
        _step = next;
      });

  void _back() {
    if (_history.isEmpty) {
      widget.onExit?.call();
      return;
    }
    setState(() => _step = _history.removeLast());
  }

  /// Subscribed: the paywall and winback are behind us, so drop them from
  /// history and go on to setup.
  void _subscribed() => setState(() {
        _plan = DfPlanState.trial(_offerDays);
        _history
          ..clear()
          ..add(V2Step.welcome);
        _step = V2Step.permissions;
      });

  void _closePaywall() {
    if (_winbackShown) {
      _declined();
      return;
    }
    _winbackShown = true;
    _go(V2Step.winback);
  }

  void _declined() => setState(() {
        _plan = const DfPlanState.free();
        _history
          ..clear()
          ..add(V2Step.welcome);
        _step = V2Step.permissions;
      });

  @override
  Widget build(BuildContext context) {
    final theme = DfTheme.of(widget.direction);
    return DfThemeScope(
      theme: theme,
      child: DfStatusBar(
        child: PopScope(
          canPop: false,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop) _back();
          },
          child: Scaffold(
            backgroundColor: theme.background,
            body: AnimatedSwitcher(
              duration: const Duration(milliseconds: 250),
              child: KeyedSubtree(key: ValueKey<V2Step>(_step), child: _screen()),
            ),
          ),
        ),
      ),
    );
  }

  Widget _paywall() => PaywallV2Screen(
        trialDays: widget.trial.days,
        today: _today,
        onTryWeb: () {
          _offerDays = widget.trial.days;
          _go(V2Step.webCheckout);
        },
        onTryAppStore: () {
          _offerDays = widget.trial.days;
          _go(V2Step.appStore);
        },
        onClose: _closePaywall,
      );

  Widget _screen() {
    const pairing = 4;
    switch (_step) {
      case V2Step.welcome:
        return WelcomeV2Screen(onSignIn: () => _go(V2Step.paywall), onGetDevice: () => _go(V2Step.buy));
      case V2Step.paywall:
        return _paywall();
      case V2Step.webCheckout:
        return DfSheetOver(
          behind: _paywall(),
          sheet: WebCheckoutSheet(trialDays: _offerDays, today: _today, onConfirm: _subscribed, onClose: _back),
        );
      case V2Step.appStore:
        return DfSheetOver(
          behind: _paywall(),
          sheet: AppStoreSheet(trialDays: _offerDays, today: _today, onConfirm: _subscribed, onClose: _back),
        );
      case V2Step.winback:
        return DfSheetOver(
          floating: true,
          behind: _paywall(),
          sheet: WinbackCard(
            originalDays: widget.trial.days,
            today: _today,
            onClaim: () {
              _offerDays = DfOffer.winbackDays;
              _go(V2Step.webCheckout);
            },
            onClaimAppStore: () {
              _offerDays = DfOffer.winbackDays;
              _go(V2Step.appStore);
            },
            onDecline: _declined,
            onViewPlans: () => dfNotInPrototype(context, 'The full plan list'),
          ),
        );
      case V2Step.permissions:
        return SetupPermissionsScreen(onContinue: () => _go(V2Step.setupIntro));
      case V2Step.setupIntro:
        return SetupIntroScreen(onContinue: () => _go(V2Step.find), onNoDevice: () => _go(V2Step.buy));
      case V2Step.find:
        return FindDeviceScreen(
          progress: (step: 1, total: pairing),
          onFound: () => _go(V2Step.found),
          searchDuration: widget.searchDuration,
        );
      case V2Step.found:
        return DeviceFoundScreen(
          progress: (step: 1, total: pairing),
          onPair: () => _go(V2Step.paired),
          onScanAgain: _back,
        );
      case V2Step.paired:
        return PairedScreen(progress: (step: 2, total: pairing), onContinue: () => _go(V2Step.name));
      case V2Step.name:
        return NameScreen(
          progress: (step: 3, total: pairing),
          onContinue: (name) {
            _name = name;
            _go(V2Step.voice);
          },
        );
      case V2Step.voice:
        return VoiceIntroScreen(progress: (step: 4, total: pairing), onDone: () => _go(V2Step.finishing));
      case V2Step.finishing:
        return SetupScreen(name: _name, ctaLabel: 'Continue', onSeePlan: () => _go(V2Step.ready));
      case V2Step.ready:
        return ReadyScreen(
          name: _name,
          language: 'English',
          ctaLabel: 'Open Omi',
          onContinue: () => _go(V2Step.app),
        );
      case V2Step.buy:
        return BuyOmiScreen(
          onBuy: () => _go(V2Step.checkout),
          onAlreadyOrdered: () => _go(V2Step.waiting),
          onBack: _back,
        );
      case V2Step.checkout:
        return CheckoutScreen(onPay: () => _go(V2Step.waiting), onBack: _back);
      case V2Step.waiting:
        return WaitingRoomScreen(onArrived: () => _go(V2Step.find), onTrack: () => _go(V2Step.arrival));
      case V2Step.arrival:
        return ArrivalNotificationScreen(onOpen: () => _go(V2Step.find));
      case V2Step.app:
        return OmiApp(plan: _plan, userName: _name, today: _today, onExit: widget.onExit);
    }
  }
}
