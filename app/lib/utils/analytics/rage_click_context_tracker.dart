import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

typedef RageClickContextCallback = void Function({String? screenName, required String target});

/// Adds Flutter screen and control context to native iOS rage-click events.
///
/// PostHog's iOS detector sees Flutter as one `FlutterView`, so its native
/// element hierarchy cannot name the Dart widget that was tapped. This widget
/// resolves each pointer against Flutter's semantics tree and registers the
/// result as PostHog super properties. A rage click is detected on the third
/// nearby tap, so the matching context from the earlier taps is already native.
class RageClickContextTracker extends StatefulWidget {
  const RageClickContextTracker({super.key, required this.child, this.onContext});

  final Widget child;
  final RageClickContextCallback? onContext;

  @override
  State<RageClickContextTracker> createState() => _RageClickContextTrackerState();
}

class _RageClickContextTrackerState extends State<RageClickContextTracker> {
  late final SemanticsHandle _semanticsHandle;

  @override
  void initState() {
    super.initState();
    _semanticsHandle = SemanticsBinding.instance.ensureSemantics();
  }

  @override
  void dispose() {
    _semanticsHandle.dispose();
    super.dispose();
  }

  void _onPointerDown(PointerDownEvent event) {
    final context = resolveRageClickContext(event.position, viewId: event.viewId);
    if (context == null) return;

    final callback = widget.onContext ?? AnalyticsManager().setInteractionContext;
    callback(screenName: context.screenName, target: context.target);
  }

  @override
  Widget build(BuildContext context) {
    return Listener(behavior: HitTestBehavior.translucent, onPointerDown: _onPointerDown, child: widget.child);
  }
}

@immutable
class RageClickContext {
  const RageClickContext({required this.screenName, required this.target});

  final String? screenName;
  final String target;
}

@visibleForTesting
RageClickContext? resolveRageClickContext(Offset position, {required int viewId}) {
  RenderView? matchingView;
  for (final renderView in RendererBinding.instance.renderViews) {
    if (renderView.flutterView.viewId == viewId) {
      matchingView = renderView;
      break;
    }
  }

  final root = matchingView?.owner?.semanticsOwner?.rootSemanticsNode;
  if (root == null) return null;

  // Pointer events use logical pixels while the root semantics node uses the
  // physical view coordinate space.
  final semanticsPosition = position * matchingView!.flutterView.devicePixelRatio;
  final hitNode = _deepestNodeAt(root, semanticsPosition);
  if (hitNode == null) return null;

  final routeScope = _nearestRouteScope(hitNode);
  final screenName = _findRouteName(routeScope ?? root);
  final target = _findTarget(hitNode, stopAt: routeScope?.parent) ?? 'unlabeled_surface';
  return RageClickContext(screenName: screenName, target: target);
}

SemanticsNode? _deepestNodeAt(SemanticsNode node, Offset positionInParent) {
  var localPosition = positionInParent;
  final transform = node.transform;
  if (transform != null) {
    final inverse = Matrix4.identity();
    if (inverse.copyInverse(transform) == 0) return null;
    localPosition = MatrixUtils.transformPoint(inverse, positionInParent);
  }

  if (!node.rect.contains(localPosition) || node.flagsCollection.isHidden) return null;

  final children = <SemanticsNode>[];
  node.visitChildren((child) {
    children.add(child);
    return true;
  });
  for (final child in children.reversed) {
    final hit = _deepestNodeAt(child, localPosition);
    if (hit != null) return hit;
  }
  return node;
}

SemanticsNode? _nearestRouteScope(SemanticsNode node) {
  SemanticsNode? current = node;
  while (current != null) {
    if (current.flagsCollection.scopesRoute) return current;
    current = current.parent;
  }
  return null;
}

String? _findRouteName(SemanticsNode root) {
  final data = root.getSemanticsData();
  if (data.flagsCollection.namesRoute) {
    final name = _normalize(data.label);
    if (name != null) return name;
  }

  String? result;
  root.visitChildren((child) {
    result ??= _findRouteName(child);
    return result == null;
  });
  return result;
}

String? _findTarget(SemanticsNode node, {SemanticsNode? stopAt}) {
  SemanticsNode? current = node;
  while (current != null && current != stopAt) {
    final data = current.getSemanticsData();
    final identifier = _normalize(data.identifier);
    if (identifier != null) return identifier;

    final label = _normalize(data.label);
    if (label != null &&
        (data.hasAction(SemanticsAction.tap) ||
            data.flagsCollection.isButton ||
            data.flagsCollection.isLink ||
            data.flagsCollection.isTextField)) {
      return label;
    }

    final tooltip = _normalize(data.tooltip);
    if (tooltip != null) return tooltip;
    current = current.parent;
  }

  current = node;
  while (current != null && current != stopAt) {
    final data = current.getSemanticsData();
    if (data.flagsCollection.isButton) return 'button';
    if (data.flagsCollection.isLink) return 'link';
    if (data.flagsCollection.isTextField) return 'text_field';
    if (data.flagsCollection.isSlider) return 'slider';
    if (data.hasAction(SemanticsAction.tap)) return 'tap_target';
    current = current.parent;
  }
  return null;
}

String? _normalize(String value) {
  final normalized = value.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (normalized.isEmpty) return null;
  return normalized.length <= 80 ? normalized : '${normalized.substring(0, 77)}...';
}
