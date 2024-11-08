import 'package:flutter/material.dart';

class AnimatedLoadingButton extends StatefulWidget {
  final String text;
  final Future<void> Function() onPressed;
  final double width;
  final double height;
  final Color color;
  final Color loaderColor;
  final TextStyle textStyle;
  final Duration animationDuration;

  const AnimatedLoadingButton({
    super.key,
    required this.text,
    required this.onPressed,
    this.width = 200,
    this.height = 40,
    required this.color,
    this.loaderColor = Colors.white,
    this.textStyle = const TextStyle(fontSize: 16, color: Colors.white),
    this.animationDuration = const Duration(milliseconds: 300),
  });

  @override
  State<AnimatedLoadingButton> createState() => _AnimatedLoadingButtonState();
}

class _AnimatedLoadingButtonState extends State<AnimatedLoadingButton> {
  bool _isLoading = false;

  void _handleOnPressed() async {
    setState(() {
      _isLoading = true;
    });
    await widget.onPressed();
    setState(() {
      _isLoading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: widget.animationDuration,
      width: _isLoading ? widget.height : widget.width,
      height: widget.height,
      decoration: BoxDecoration(
        color: widget.color,
        borderRadius: BorderRadius.circular(widget.height / 2),
      ),
      child: InkWell(
        onTap: _isLoading ? null : _handleOnPressed,
        borderRadius: BorderRadius.circular(widget.height / 2),
        child: Center(
          child: AnimatedSwitcher(
            duration: widget.animationDuration,
            child: _isLoading
                ? SizedBox(
                    width: widget.height / 2,
                    height: widget.height / 2,
                    child: CircularProgressIndicator(
                      key: const ValueKey('loader'),
                      color: widget.loaderColor,
                      strokeWidth: 3.0,
                    ),
                  )
                : Text(
                    widget.text,
                    key: const ValueKey('buttonText'),
                    style: widget.textStyle,
                  ),
          ),
        ),
      ),
    );
  }
}
