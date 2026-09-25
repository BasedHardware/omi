import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_icon_button.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one search field: a 48pt [OmiColors.surface1] capsule with a magnifier, the placeholder,
/// and a clear X that appears once there is text.
///
/// The placeholder says what it searches ("Search conversations", "Search memories"), sentence
/// case, with no trailing ellipsis.
///
/// The field owns a controller when none is passed. Clearing empties the text, calls [onChanged]
/// with `''`, then [onCleared]; keyboard focus is kept so the user can type again.
class OmiSearchField extends StatefulWidget {
  const OmiSearchField({
    super.key,
    required this.placeholder,
    this.controller,
    this.focusNode,
    this.onChanged,
    this.onSubmitted,
    this.onCleared,
    this.onTap,
    this.autofocus = false,
    this.textInputAction = TextInputAction.search,
  });

  final String placeholder;
  final TextEditingController? controller;
  final FocusNode? focusNode;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;

  /// Called after the clear X empties the field.
  final VoidCallback? onCleared;

  final VoidCallback? onTap;
  final bool autofocus;
  final TextInputAction textInputAction;

  @override
  State<OmiSearchField> createState() => _OmiSearchFieldState();
}

class _OmiSearchFieldState extends State<OmiSearchField> {
  TextEditingController? _ownController;

  TextEditingController get _controller => widget.controller ?? (_ownController ??= TextEditingController());

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onTextChanged);
  }

  @override
  void didUpdateWidget(OmiSearchField oldWidget) {
    super.didUpdateWidget(oldWidget);
    final oldController = oldWidget.controller ?? _ownController;
    if (oldController != _controller) {
      oldController?.removeListener(_onTextChanged);
      _controller.addListener(_onTextChanged);
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_onTextChanged);
    _ownController?.dispose();
    super.dispose();
  }

  void _onTextChanged() => setState(() {});

  void _clear() {
    _controller.clear();
    widget.onChanged?.call('');
    widget.onCleared?.call();
  }

  @override
  Widget build(BuildContext context) {
    const border = OutlineInputBorder(borderRadius: OmiRadius.xlAll, borderSide: BorderSide.none);
    return SizedBox(
      height: 48,
      child: TextField(
        controller: _controller,
        focusNode: widget.focusNode,
        autofocus: widget.autofocus,
        onChanged: widget.onChanged,
        onSubmitted: widget.onSubmitted,
        onTap: widget.onTap,
        textInputAction: widget.textInputAction,
        style: OmiType.subhead,
        cursorColor: OmiColors.accent,
        decoration: InputDecoration(
          hintText: widget.placeholder,
          hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
          filled: true,
          fillColor: OmiColors.surface1,
          border: border,
          enabledBorder: border,
          focusedBorder: border,
          contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
          prefixIcon: const ExcludeSemantics(child: Icon(Icons.search, color: OmiColors.textTertiary, size: 20)),
          suffixIcon: _controller.text.isEmpty
              ? null
              : OmiIconButton(
                  icon: const Icon(Icons.close, size: 18),
                  label: context.l10n.clearSearch,
                  color: OmiColors.textSecondary,
                  onPressed: _clear,
                ),
        ),
      ),
    );
  }
}
