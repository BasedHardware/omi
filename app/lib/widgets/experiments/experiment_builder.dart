import 'package:flutter/material.dart';
import 'package:omi/services/experiments/experiment_service.dart';

typedef ExperimentVariantBuilder<T> = Widget Function(BuildContext context, T variant, Widget? child);

/// One selection per mounted surface. Put Navigator/providers above this widget
/// when variants replace entire pages. Use a loading placeholder, never an
/// interactive control that would be replaced once the flag arrives.
class ExperimentBuilder<T> extends StatefulWidget {
  const ExperimentBuilder(
      {super.key,
      required this.service,
      required this.definition,
      required this.surface,
      required this.builder,
      required this.loadingBuilder,
      this.child,
      this.visible = true});
  final ExperimentService service;
  final ExperimentDefinition<T> definition;
  final String surface;
  final ExperimentVariantBuilder<T> builder;
  final WidgetBuilder loadingBuilder;
  final Widget? child;

  /// Caller owns visibility for tab/offstage/list surfaces. Route visibility is
  /// also checked automatically. Never set true for a prefetched hidden page.
  final bool visible;
  @override
  State<ExperimentBuilder<T>> createState() => _ExperimentBuilderState<T>();
}

class _ExperimentBuilderState<T> extends State<ExperimentBuilder<T>> {
  ExperimentLease<T>? _lease;
  int _request = 0;
  int _generation = -1;
  @override
  void initState() {
    super.initState();
    widget.service.addListener(_contextChanged);
    _open();
  }

  void _contextChanged() {
    if (_generation != widget.service.generation) {
      _release();
      _open();
      if (mounted) setState(() {});
    }
  }

  void _open() {
    _generation = widget.service.generation;
    final request = ++_request;
    widget.service.open(widget.definition, surface: widget.surface).then((lease) {
      if (!mounted || request != _request) {
        lease.dispose();
        return;
      }
      setState(() {
        _lease = lease;
        lease.addListener(_changed);
      });
    });
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  void _release() {
    _request++;
    _lease?.removeListener(_changed);
    _lease?.dispose();
    _lease = null;
  }

  @override
  void didUpdateWidget(covariant ExperimentBuilder<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.service != widget.service ||
        oldWidget.definition != widget.definition ||
        oldWidget.surface != widget.surface) {
      oldWidget.service.removeListener(_contextChanged);
      widget.service.addListener(_contextChanged);
      _release();
      _open();
    }
  }

  @override
  Widget build(BuildContext context) {
    final lease = _lease;
    if (lease == null) return widget.loadingBuilder(context);
    final visible = widget.visible && TickerMode.valuesOf(context).enabled && (ModalRoute.isCurrentOf(context) ?? true);
    if (visible) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted ||
            _lease != lease ||
            !widget.visible ||
            !TickerMode.valuesOf(context).enabled ||
            !(ModalRoute.isCurrentOf(context) ?? true)) {
          return;
        }
        final render = context.findRenderObject();
        if (render is RenderBox && render.attached && render.hasSize && !render.size.isEmpty) lease.expose();
      });
    }
    return widget.builder(context, lease.variant, widget.child);
  }

  @override
  void dispose() {
    widget.service.removeListener(_contextChanged);
    _release();
    super.dispose();
  }
}
