import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_edit_sheet.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'ios_native_home.dart';
import 'ios_native_surface.dart';

/// Uses the same explicit-save and discard guard as the existing editor.
class IosNativeEdit extends StatefulWidget {
  const IosNativeEdit(
      {super.key,
      required this.title,
      required this.sections,
      required this.fallback,
      required this.isDirty,
      this.enabled = true,
      this.toolbar = const [],
      this.failed = false});
  final String title;
  final List<NativeSection> sections;
  final List<NativeRow> toolbar;
  final Widget fallback;
  final bool isDirty, enabled, failed;

  @override
  State<IosNativeEdit> createState() => _IosNativeEditState();
}

class _IosNativeEditState extends State<IosNativeEdit> {
  bool _asking = false;
  Future<void> _blocked() async {
    if (_asking || !widget.enabled || !mounted) return;
    _asking = true;
    final discard = await confirmDiscardChanges(context);
    _asking = false;
    if (discard && mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    if (!iosSwiftUiEnabled) return widget.fallback;
    return PopScope<Object?>(
      canPop: !widget.isDirty && widget.enabled,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _blocked();
      },
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * .88,
        child: IosNativeSurface(
            title: widget.title,
            sections: widget.sections,
            fallback: widget.fallback,
            failed: widget.failed,
            toolbar: [
              NativeRow('editor_close', context.l10n.close, symbol: 'xmark', enabled: widget.enabled,
                  action: (_) async {
                await Navigator.of(context).maybePop();
              }),
              ...widget.toolbar,
            ]),
      ),
    );
  }
}
