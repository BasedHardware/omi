import 'package:flutter/material.dart';

import 'src/bridge.dart';
import 'src/content.dart';
import 'src/flow.dart';
import 'src/launcher.dart';
import 'src/theme.dart';

/// Design prototype of the device-first onboarding flow and soft paywall.
/// See README.md for how to run it.
///
/// On the web, `?embed=1&direction=graphite|aurora&trial=3|7|14|30` skips the launcher and
/// plays the flow for the Omi app's onboarding webview, starting after sign-in and consent
/// (which the app already did) and reporting name, permissions and completion to the app.
void main() => runApp(const DeviceFirstPrototypeApp());

class DeviceFirstPrototypeApp extends StatelessWidget {
  const DeviceFirstPrototypeApp({super.key});

  @override
  Widget build(BuildContext context) {
    final params = Uri.base.queryParameters;
    final embed = params['embed'] == '1';
    return MaterialApp(
      title: 'Omi device-first prototype',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(brightness: Brightness.dark, useMaterial3: true),
      home: embed ? _EmbeddedFlow(params: params) : const PrototypeLauncher(),
    );
  }
}

class _EmbeddedFlow extends StatefulWidget {
  const _EmbeddedFlow({required this.params});

  final Map<String, String> params;

  @override
  State<_EmbeddedFlow> createState() => _EmbeddedFlowState();
}

class _EmbeddedFlowState extends State<_EmbeddedFlow> {
  @override
  void initState() {
    super.initState();
    OmiBridge.ready();
  }

  @override
  Widget build(BuildContext context) {
    final direction = widget.params['direction'] == 'aurora' ? DfDirection.aurora : DfDirection.graphite;
    final trialParam = widget.params['trial'] ?? '30';
    final trial = TrialLength.values.firstWhere(
      (t) => t.label.startsWith('$trialParam '),
      orElse: () => TrialLength.oneMonth,
    );
    // Inside the app the webview runs under the status bar; keep the first line of every screen
    // clear of it (and of the home indicator) on iOS.
    final ios = widget.params['platform'] == 'ios';
    return Padding(
      padding: EdgeInsets.only(top: ios ? 54 : 0, bottom: ios ? 20 : 0),
      child: DeviceFirstFlow(
        direction: direction,
        trial: trial,
        initialStep: DfStep.fork,
        onExit: OmiBridge.fallback,
        onName: OmiBridge.setName,
        onPermissions: () => OmiBridge.permission('notifications'),
        onEnd: OmiBridge.complete,
      ),
    );
  }
}
