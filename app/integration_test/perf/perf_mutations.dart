// Test-only fault injection. Never change production wrappers for mutation tests.
import 'dart:io';
import 'package:flutter/widgets.dart';
import 'package:flutter/semantics.dart';

Widget injectPerfMutation(Widget child) =>
    Platform.environment['PERF_GATE_MUTATION'] == 'held_semantics' ? _HeldSemantics(child: child) : child;

class _HeldSemantics extends StatefulWidget {
  const _HeldSemantics({required this.child});
  final Widget child;
  @override
  State<_HeldSemantics> createState() => _HeldSemanticsState();
}

class _HeldSemanticsState extends State<_HeldSemantics> {
  late final SemanticsHandle handle;
  @override
  void initState() {
    super.initState();
    handle = WidgetsBinding.instance.ensureSemantics();
  }

  @override
  void dispose() {
    handle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
