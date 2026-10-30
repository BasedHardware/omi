import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

typedef RageClickContextCallback = void Function({String? screenName, required String target});

/// Adds Flutter screen and control context to native iOS rage-click events.
///
/// PostHog's iOS detector sees Flutter as one `FlutterView`, so its native
/// element hierarchy cannot name the Dart widget that was tapped. This widget
/// resolves each pointer against the render objects under it and registers the
/// result as PostHog super properties. A rage click is detected on the third
/// nearby tap, so the matching context from the earlier taps is already native.
///
/// It reads the semantics annotations already present in the render tree
/// instead of holding a `SemanticsHandle`: a held handle makes every frame of
/// the app compile the semantics tree (about 15% of UI-thread frame work while
/// scrolling a list, measured in `test/perf/rage_click_semantics_cost_test.dart`).
class RageClickContextTracker extends StatelessWidget {
  const RageClickContextTracker({super.key, required this.child, this.onContext});

  final Widget child;
  final RageClickContextCallback? onContext;

  void _onPointerDown(PointerDownEvent event) {
    final context = resolveRageClickContext(event.position, viewId: event.viewId);
    if (context == null) return;

    final callback = onContext ?? AnalyticsManager().setInteractionContext;
    callback(screenName: context.screenName, target: context.target);
  }

  @override
  Widget build(BuildContext context) {
    return Listener(behavior: HitTestBehavior.translucent, onPointerDown: _onPointerDown, child: child);
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
  final result = HitTestResult();
  RendererBinding.instance.hitTestInView(result, position, viewId);
  // Deepest first; the root is last.
  final path = <RenderObject>[
    for (final entry in result.path)
      if (entry.target is RenderObject) entry.target as RenderObject,
  ];
  if (path.isEmpty) return null;

  final routeIndex = path.indexWhere((o) => o is SemanticsAnnotationsMixin && o.properties.scopesRoute == true);
  final inRoute = routeIndex < 0 ? path : path.sublist(0, routeIndex);
  final screenName = _findRouteName(routeIndex < 0 ? path.last : path[routeIndex]);
  final target = _findTarget(inRoute) ?? 'unlabeled_surface';
  return RageClickContext(screenName: screenName, target: target);
}

const int _routeNameSearchBudget = 3000;

/// The label of the route's title (the app bar marks it with `namesRoute`).
String? _findRouteName(RenderObject scope) {
  var budget = _routeNameSearchBudget;
  String? found;
  void visit(RenderObject node) {
    if (found != null || budget-- <= 0) return;
    if (node is SemanticsAnnotationsMixin && node.properties.namesRoute == true) {
      found = _normalize(node.properties.label ?? '') ?? _textBelow(node);
      if (found != null) return;
    }
    // App bars follow the body in a Scaffold's children; walk the last child first.
    final children = <RenderObject>[];
    node.visitChildren(children.add);
    for (final child in children.reversed) {
      visit(child);
      if (found != null) return;
    }
  }

  visit(scope);
  return found;
}

String? _findTarget(List<RenderObject> path) {
  for (final node in path) {
    if (node is! SemanticsAnnotationsMixin) continue;
    final p = node.properties;
    final identifier = _normalize(p.identifier ?? '');
    if (identifier != null) return identifier;

    final interactive = p.button == true || p.link == true || p.textField == true || p.onTap != null;
    final label = _normalize(p.label ?? '');
    if (label != null && interactive) return label;
    // Buttons and links are named by their own text, as their semantics node would be.
    if (p.button == true || p.link == true) {
      final text = _textBelow(node);
      if (text != null) return text;
    }

    final tooltip = _normalize(p.tooltip ?? '');
    if (tooltip != null) return tooltip;
  }

  for (final node in path) {
    if (node is SemanticsAnnotationsMixin) {
      final p = node.properties;
      if (p.button == true) return 'button';
      if (p.link == true) return 'link';
      if (p.textField == true) return 'text_field';
      if (p.slider == true) return 'slider';
      if (p.onTap != null) return 'tap_target';
    }
    if (node is RenderSemanticsGestureHandler && node.onTap != null) return 'tap_target';
    if (node is RenderEditable) return 'text_field';
  }
  return null;
}

/// Up to a few visible text runs inside a button or title, never a whole subtree.
String? _textBelow(RenderObject root) {
  final parts = <String>[];
  var budget = 200;
  void visit(RenderObject node) {
    if (parts.length >= 3 || budget-- <= 0) return;
    // Icons draw a font glyph under ExcludeSemantics; their own label is the tooltip.
    if (node is RenderExcludeSemantics && node.excluding) return;
    if (node is RenderParagraph) {
      final text = node.text.toPlainText(includeSemanticsLabels: true, includePlaceholders: false);
      if (!text.runes.every(_isIconGlyph)) parts.add(text);
      return;
    }
    node.visitChildren(visit);
  }

  visit(root);
  return _normalize(parts.join(' '));
}

bool _isIconGlyph(int rune) => (rune >= 0xE000 && rune <= 0xF8FF) || rune >= 0xF0000;

final RegExp _whitespace = RegExp(r'\s+');

String? _normalize(String value) {
  final normalized = value.replaceAll(_whitespace, ' ').trim();
  if (normalized.isEmpty) return null;
  return normalized.length <= 80 ? normalized : '${normalized.substring(0, 77)}...';
}
