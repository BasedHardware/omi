import 'package:flutter/material.dart';

extension FunctionExt on Function {
  void withPostFrameCallback() => WidgetsBinding.instance.addPostFrameCallback((_) {
        this();
      });
}
