import 'package:flutter/material.dart';

class CollapsibleSection extends StatefulWidget {
  final Widget title;
  final List<Widget> children;

  const CollapsibleSection({
    super.key,
    required this.title,
    required this.children,
  });

  @override
  State<CollapsibleSection> createState() => _CollapsibleSectionState();
}

class _CollapsibleSectionState extends State<CollapsibleSection> {
  bool _isExpanded = false;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () {
            setState(() {
              _isExpanded = !_isExpanded;
            });
          },
          child: Row(
            children: [
              Expanded(child: widget.title),
              Icon(
                _isExpanded ? Icons.expand_less : Icons.expand_more,
                color: Colors.white60,
              ),
            ],
          ),
        ),
        if (_isExpanded) ...widget.children,
      ],
    );
  }
}
