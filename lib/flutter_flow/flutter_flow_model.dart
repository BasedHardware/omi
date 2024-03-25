import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:provider/provider.dart';

Widget wrapWithModel<T extends FlutterFlowModel>({
  required T model,
  required Widget child,
  required VoidCallback updateCallback,
  bool updateOnChange = false,
}) {
  // Set the component to optionally update the page on updates.
  model.setOnUpdate(
    onUpdate: updateCallback,
    updateOnChange: updateOnChange,
  );
  // Models for components within a page will be disposed by the page's model,
  // so we don't want the component widget to dispose them until the page is
  // itself disposed.
  model.disposeOnWidgetDisposal = false;
  // Wrap in a Provider so that the model can be accessed by the component.
  return Provider<T>.value(
    value: model,
    child: child,
  );
}

T createModel<T extends FlutterFlowModel>(
  BuildContext context,
  T Function() defaultBuilder,
) {
  final model = context.read<T?>() ?? defaultBuilder();
  model._init(context);
  return model;
}

abstract class FlutterFlowModel<W extends Widget> {
  // Initialization methods
  bool _isInitialized = false;
  void initState(BuildContext context);
  void _init(BuildContext context) {
    if (!_isInitialized) {
      initState(context);
      _isInitialized = true;
    }
    if (context.widget is W) _widget = context.widget as W;
  }

  // The widget associated with this model. This is useful for accessing the
  // parameters of the widget, for example.
  W? _widget;
  // This will always be non-null when used, but is nullable to allow us to
  // dispose of the widget in the [dispose] method (for garbage collection).
  W get widget => _widget!;

  // Dispose methods
  // Whether to dispose this model when the corresponding widget is
  // disposed. By default this is true for pages and false for components,
  // as page/component models handle the disposal of their children.
  bool disposeOnWidgetDisposal = true;
  void dispose();
  void maybeDispose() {
    if (disposeOnWidgetDisposal) {
      dispose();
    }
    // Remove reference to widget for garbage collection purposes.
    _widget = null;
  }

  // Whether to update the containing page / component on updates.
  bool updateOnChange = false;
  // Function to call when the model receives an update.
  VoidCallback _updateCallback = () {};
  void onUpdate() => updateOnChange ? _updateCallback() : () {};
  FlutterFlowModel setOnUpdate({
    bool updateOnChange = false,
    required VoidCallback onUpdate,
  }) =>
      this
        .._updateCallback = onUpdate
        ..updateOnChange = updateOnChange;
  // Update the containing page when this model received an update.
  void updatePage(VoidCallback callback) {
    callback();
    _updateCallback();
  }
}

class FlutterFlowDynamicModels<T extends FlutterFlowModel> {
  FlutterFlowDynamicModels(this.defaultBuilder);

  final T Function() defaultBuilder;
  final Map<String, T> _childrenModels = {};
  final Map<String, int> _childrenIndexes = {};
  Set<String>? _activeKeys;

  T getModel(String uniqueKey, int index) {
    _updateActiveKeys(uniqueKey);
    _childrenIndexes[uniqueKey] = index;
    return _childrenModels[uniqueKey] ??= defaultBuilder();
  }

  List<S> getValues<S>(S? Function(T) getValue) {
    return _childrenIndexes.entries
        // Sort keys by index.
        .sorted((a, b) => a.value.compareTo(b.value))
        .where((e) => _childrenModels[e.key] != null)
        // Map each model to the desired value and return as list. In order
        // to preserve index order, rather than removing null values we provide
        // default values (for types with reasonable defaults).
        .map((e) => getValue(_childrenModels[e.key]!) ?? _getDefaultValue<S>()!)
        .toList();
  }

  S? getValueAtIndex<S>(int index, S? Function(T) getValue) {
    final uniqueKey =
        _childrenIndexes.entries.firstWhereOrNull((e) => e.value == index)?.key;
    return getValueForKey(uniqueKey, getValue);
  }

  S? getValueForKey<S>(String? uniqueKey, S? Function(T) getValue) {
    final model = _childrenModels[uniqueKey];
    return model != null ? getValue(model) : null;
  }

  void dispose() => _childrenModels.values.forEach((model) => model.dispose());

  void _updateActiveKeys(String uniqueKey) {
    final shouldResetActiveKeys = _activeKeys == null;
    _activeKeys ??= {};
    _activeKeys!.add(uniqueKey);

    if (shouldResetActiveKeys) {
      // Add a post-frame callback to remove and dispose of unused models after
      // we're done building, then reset `_activeKeys` to null so we know to do
      // this again next build.
      SchedulerBinding.instance.addPostFrameCallback((_) {
        _childrenIndexes.removeWhere((k, _) => !_activeKeys!.contains(k));
        _childrenModels.keys
            .toSet()
            .difference(_activeKeys!)
            // Remove and dispose of unused models since they are  not being used
            // elsewhere and would not otherwise be disposed.
            .forEach((k) => _childrenModels.remove(k)?.dispose());
        _activeKeys = null;
      });
    }
  }
}

T? _getDefaultValue<T>() {
  switch (T) {
    case int:
      return 0 as T;
    case double:
      return 0.0 as T;
    case String:
      return '' as T;
    case bool:
      return false as T;
    default:
      return null as T;
  }
}

extension TextValidationExtensions on String? Function(BuildContext, String?)? {
  String? Function(String?)? asValidator(BuildContext context) =>
      this != null ? (val) => this!(context, val) : null;
}
