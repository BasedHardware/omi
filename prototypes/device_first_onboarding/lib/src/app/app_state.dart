import 'package:flutter/widgets.dart';

import '../content.dart';
import 'mock_data.dart';

/// Shared state for the app screens: plan, tasks, listening, enabled apps.
class OmiAppState extends ChangeNotifier {
  OmiAppState({required DfPlanState plan, required this.userName, required DateTime today})
      : _plan = plan,
        data = MockData(today);

  final String userName;
  final MockData data;

  DateTime get today => data.today;

  DfPlanState _plan;
  DfPlanState get plan => _plan;
  bool get unlimited => _plan.unlimited;

  bool _listening = true;
  bool get listening => _listening;

  final Set<String> _enabledApps = <String>{'Google Calendar'};
  bool isEnabled(MockApp app) => _enabledApps.contains(app.name);

  /// Day the current trial converts, if on a trial.
  DateTime? get trialEnds {
    final days = _plan.trialDays;
    return days == null ? null : today.add(Duration(days: days));
  }

  void upgrade(int trialDays) {
    _plan = DfPlanState.trial(trialDays);
    notifyListeners();
  }

  void toggleListening() {
    _listening = !_listening;
    notifyListeners();
  }

  void toggleTask(MockTask task) {
    task.done = !task.done;
    notifyListeners();
  }

  void addTask(String title, DateTime? due) {
    data.tasks.add(MockTask(title, due: due));
    notifyListeners();
  }

  void toggleApp(MockApp app) {
    if (!_enabledApps.remove(app.name)) _enabledApps.add(app.name);
    notifyListeners();
  }
}

class OmiAppScope extends InheritedNotifier<OmiAppState> {
  const OmiAppScope({super.key, required OmiAppState state, required super.child}) : super(notifier: state);

  static OmiAppState of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<OmiAppScope>()!.notifier!;
}
