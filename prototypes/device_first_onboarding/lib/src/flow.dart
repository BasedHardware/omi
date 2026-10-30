import 'package:flutter/material.dart';

import 'content.dart';
import 'screens/buy_screens.dart';
import 'screens/pairing_screens.dart';
import 'screens/paywall_screens.dart';
import 'screens/setup_screens.dart';
import 'screens/start_screens.dart';
import 'theme.dart';
import 'widgets.dart';

/// Every screen in the flow, numbered as in Figma.
enum DfStep {
  welcome('01 Welcome'),
  signIn('02 Sign in'),
  privacy('03 Data & Privacy'),
  fork('04 Do you have your Omi?'),
  find('05 Find your Omi'),
  found('06 Omi found'),
  paired('07 Paired'),
  name('08 Name'),
  language('09 Language'),
  permissions('10 Permissions'),
  voice('11 Voice introduction'),
  setup('12 Setting up'),
  ready('13 Your Omi is ready'),
  paywall('14 Soft paywall'),
  trialStarted('15 Trial started'),
  buy('B1 Get your Omi'),
  checkout('B2 Order summary'),
  waiting('B3 Waiting room'),
  arrival('B4 Delivered push'),
  end('Home');

  const DfStep(this.title);

  final String title;
}

/// The device-first onboarding flow, end to end, in one direction.
///
/// Branches at [DfStep.fork]: pair now, wait for a shipped Omi, or buy one.
/// Without a paired device the flow can't reach the paywall or home.
class DeviceFirstFlow extends StatefulWidget {
  const DeviceFirstFlow({
    super.key,
    required this.direction,
    required this.trial,
    this.initialStep = DfStep.welcome,
    this.searchDuration = const Duration(seconds: 3),
    this.onExit,
    this.onName,
    this.onPermissions,
    this.onEnd,
  });

  final DfDirection direction;
  final TrialLength trial;
  final DfStep initialStep;

  /// How long the fake Bluetooth scan takes before the Omi is "found".
  final Duration searchDuration;

  /// Called when the user backs out of the first screen or leaves the end.
  final VoidCallback? onExit;

  /// Host hooks used when the flow is embedded in the Omi app: the name the user typed, the
  /// moment permissions are requested, and the flow reaching its end.
  final ValueChanged<String>? onName;
  final VoidCallback? onPermissions;
  final VoidCallback? onEnd;

  @override
  State<DeviceFirstFlow> createState() => _DeviceFirstFlowState();
}

class _DeviceFirstFlowState extends State<DeviceFirstFlow> {
  late DfStep _step = widget.initialStep;
  final List<DfStep> _history = <DfStep>[];
  String _name = 'Alex';
  String _language = 'English';
  String _path = 'Has an Omi';
  String _outcome = '';

  void _go(DfStep next) {
    setState(() {
      _history.add(_step);
      _step = next;
    });
    if (next == DfStep.end) widget.onEnd?.call();
  }

  void _back() {
    if (_history.isEmpty) {
      widget.onExit?.call();
      return;
    }
    setState(() => _step = _history.removeLast());
  }

  void _restart() => setState(() {
    _history.clear();
    _step = DfStep.welcome;
    _outcome = '';
    _path = 'Has an Omi';
  });

  @override
  Widget build(BuildContext context) {
    final theme = DfTheme.of(widget.direction);
    return DfThemeScope(
      theme: theme,
      child: PopScope(
        canPop: false,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) _back();
        },
        child: Scaffold(
          backgroundColor: theme.background,
          body: AnimatedSwitcher(
            duration: const Duration(milliseconds: 250),
            child: KeyedSubtree(key: ValueKey<DfStep>(_step), child: _screen()),
          ),
        ),
      ),
    );
  }

  Widget _screen() {
    final trial = widget.trial;
    switch (_step) {
      case DfStep.welcome:
        return WelcomeScreen(onGetStarted: () => _go(DfStep.signIn));
      case DfStep.signIn:
        return SignInScreen(onContinue: () => _go(DfStep.privacy));
      case DfStep.privacy:
        return PrivacyScreen(onAgree: () => _go(DfStep.fork), onDifferentAccount: _back);
      case DfStep.fork:
        return DeviceForkScreen(
          onPair: () {
            _path = 'Has an Omi';
            _go(DfStep.find);
          },
          onOnTheWay: () {
            _path = 'On the way';
            _go(DfStep.waiting);
          },
          onNoDevice: () {
            _path = 'Bought an Omi';
            _go(DfStep.buy);
          },
        );
      case DfStep.find:
        return FindDeviceScreen(onFound: () => _go(DfStep.found), searchDuration: widget.searchDuration);
      case DfStep.found:
        return DeviceFoundScreen(onPair: () => _go(DfStep.paired), onScanAgain: _back);
      case DfStep.paired:
        return PairedScreen(onContinue: () => _go(DfStep.name));
      case DfStep.name:
        return NameScreen(
          onContinue: (name) {
            _name = name;
            widget.onName?.call(name);
            _go(DfStep.language);
          },
        );
      case DfStep.language:
        return LanguageScreen(
          onContinue: (language) {
            _language = language;
            _go(DfStep.permissions);
          },
        );
      case DfStep.permissions:
        return PermissionsScreen(
          onContinue: () {
            widget.onPermissions?.call();
            _go(DfStep.voice);
          },
        );
      case DfStep.voice:
        return VoiceIntroScreen(onDone: () => _go(DfStep.setup));
      case DfStep.setup:
        return SetupScreen(name: _name, onSeePlan: () => _go(DfStep.ready));
      case DfStep.ready:
        return ReadyScreen(name: _name, language: _language, onContinue: () => _go(DfStep.paywall));
      case DfStep.paywall:
        return SoftPaywallScreen(
          name: _name,
          trial: trial,
          onStartTrial: (plan) {
            _outcome = 'Trial started · ${plan.name} · ${trial.label}';
            _go(DfStep.trialStarted);
          },
          onContinueFree: () {
            _outcome = 'Continued with Free';
            _go(DfStep.end);
          },
        );
      case DfStep.trialStarted:
        return TrialStartedScreen(name: _name, trial: trial, onStart: () => _go(DfStep.end));
      case DfStep.buy:
        return BuyOmiScreen(
          onBuy: () => _go(DfStep.checkout),
          onAlreadyOrdered: () => _go(DfStep.waiting),
          onBack: _back,
        );
      case DfStep.checkout:
        return CheckoutScreen(onPay: () => _go(DfStep.waiting), onBack: _back);
      case DfStep.waiting:
        return WaitingRoomScreen(onArrived: () => _go(DfStep.find), onTrack: () => _go(DfStep.arrival));
      case DfStep.arrival:
        return ArrivalNotificationScreen(onOpen: () => _go(DfStep.find));
      case DfStep.end:
        return _EndScreen(
          direction: widget.direction,
          path: _path,
          trial: trial,
          outcome: _outcome,
          onRestart: _restart,
          onExit: widget.onExit,
        );
    }
  }
}

/// Stands in for `HomePageWrapper` and summarises the run.
class _EndScreen extends StatelessWidget {
  const _EndScreen({
    required this.direction,
    required this.path,
    required this.trial,
    required this.outcome,
    required this.onRestart,
    required this.onExit,
  });

  final DfDirection direction;
  final String path;
  final TrialLength trial;
  final String outcome;
  final VoidCallback onRestart;
  final VoidCallback? onExit;

  @override
  Widget build(BuildContext context) {
    final onExit = this.onExit;
    return DfPage(
      children: <Widget>[
        const DfEyebrow('Prototype'),
        const DfHeadline('Prototype ends here'),
        const DfBody('In the app, this is the home screen.'),
        DfCard(
          child: Column(
            children: <Widget>[
              DfListRow(label: 'Direction', value: direction.label),
              DfListRow(label: 'Path', value: path),
              DfListRow(label: 'Trial arm', value: trial.label),
              DfListRow(label: 'Result', value: outcome.isEmpty ? '—' : outcome),
            ],
          ),
        ),
        const Spacer(),
        DfButton('Restart flow', onPressed: onRestart),
        if (onExit != null) DfButton('Back to launcher', onPressed: onExit, kind: DfButtonKind.text),
      ],
    );
  }
}
