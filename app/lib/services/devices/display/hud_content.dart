/// Device-agnostic HUD content model.
///
/// Display glasses differ in renderer (Meta DAT ships FlexBox/Text/Button;
/// other vendors ship text lines), so nothing here names a vendor type. A
/// connector translates [HudScreen] into whatever its SDK draws.
library;

enum HudScreenKind { idle, tasks, capture, answer }

enum HudLineStyle { heading, body, meta }

class HudLine {
  final String text;
  final HudLineStyle style;
  final bool muted;

  const HudLine(this.text, {this.style = HudLineStyle.body, this.muted = false});

  @override
  bool operator ==(Object other) =>
      other is HudLine && other.text == text && other.style == style && other.muted == muted;

  @override
  int get hashCode => Object.hash(text, style, muted);

  @override
  String toString() => 'HudLine($text, $style, muted=$muted)';
}

class HudAction {
  final String id;
  final String label;

  const HudAction(this.id, this.label);

  @override
  bool operator ==(Object other) => other is HudAction && other.id == id && other.label == label;

  @override
  int get hashCode => Object.hash(id, label);
}

class HudScreen {
  final HudScreenKind kind;
  final String title;
  final List<HudLine> lines;
  final List<HudAction> actions;

  const HudScreen({
    required this.kind,
    required this.title,
    this.lines = const [],
    this.actions = const [],
  });

  static const HudScreen idle = HudScreen(kind: HudScreenKind.idle, title: 'Omi');

  bool get isEmpty => lines.isEmpty && actions.isEmpty;

  @override
  bool operator ==(Object other) {
    if (other is! HudScreen) return false;
    if (other.kind != kind || other.title != title) return false;
    if (other.lines.length != lines.length || other.actions.length != actions.length) return false;
    for (var i = 0; i < lines.length; i++) {
      if (other.lines[i] != lines[i]) return false;
    }
    for (var i = 0; i < actions.length; i++) {
      if (other.actions[i] != actions[i]) return false;
    }
    return true;
  }

  @override
  int get hashCode => Object.hash(kind, title, Object.hashAll(lines), Object.hashAll(actions));

  @override
  String toString() => 'HudScreen($kind, "$title", ${lines.length} lines)';
}
