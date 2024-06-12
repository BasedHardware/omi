import 'dart:ui';

import 'package:flutter/material.dart';

class BlurWidget extends StatefulWidget {
  const BlurWidget({super.key});

  @override
  State<BlurWidget> createState() => _BlurWidgetState();
}

class _BlurWidgetState extends State<BlurWidget> {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: const BoxDecoration(),
      child: Align(
        alignment: const AlignmentDirectional(0.0, 1.0),
        child: ClipRect(
          child: ImageFiltered(
            imageFilter: ImageFilter.blur(
              sigmaX: 48.0,
              sigmaY: 48.0,
            ),
            child: Container(
              width: double.infinity,
              height: double.infinity,
              decoration: BoxDecoration(
                color: Theme.of(context).primaryColor,
              ),
              child: SizedBox(
                width: double.infinity,
                height: double.infinity,
                child: Stack(
                  alignment: const AlignmentDirectional(0.0, 0.0),
                  children: [
                    Align(
                      alignment: const AlignmentDirectional(1.0, 0.0),
                      child: Container(
                        width: 240.0,
                        height: 240.0,
                        decoration: const BoxDecoration(
                          color: Color(0xFFFE480D),
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                    Align(
                      alignment: const AlignmentDirectional(-1.0, 0.0),
                      child: Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 40.0),
                        child: Container(
                          width: 200.0,
                          height: 200.0,
                          decoration: const BoxDecoration(
                            color: Color(0xFF97ADAA),
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
