import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';

import 'package:nooto_v2/plan/plan_storage.dart';
import 'package:nooto_v2/plan/widgets/plan_pivot_picker.dart';

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('plan_pivot_picker_test');
    Hive.init(tempDir.path);
    await Hive.openBox<dynamic>(PlanBoxes.prefs);
  });

  setUp(() async {
    await Hive.box<dynamic>(PlanBoxes.prefs).clear();
  });

  tearDownAll(() async {
    await Hive.deleteFromDisk();
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  group('PlanPivotPicker (storage)', () {
    test('persist writes string name to Hive', () async {
      await PlanPivotPicker.persist(PlanPivot.byStatus);
      final raw = Hive.box<dynamic>(PlanBoxes.prefs).get(PlanBoxes.pivotKey);
      expect(raw, 'byStatus');
    });

    test('loadSaved round-trips persisted value', () async {
      await PlanPivotPicker.persist(PlanPivot.byProject);
      expect(PlanPivotPicker.loadSaved(), PlanPivot.byProject);
    });

    test('loadSaved defaults to byDate when nothing saved', () async {
      expect(PlanPivotPicker.loadSaved(), PlanPivot.byDate);
    });

    test('loadSaved defaults to byDate when stored value is unknown', () async {
      await Hive.box<dynamic>(PlanBoxes.prefs).put(PlanBoxes.pivotKey, 'someGarbageValue');
      expect(PlanPivotPicker.loadSaved(), PlanPivot.byDate);
    });
  });

  group('PlanPivotLabel', () {
    test('label getter is human-readable for each enum value', () {
      expect(PlanPivot.byDate.label, 'By Date');
      expect(PlanPivot.byProject.label, 'By Project');
      expect(PlanPivot.byStatus.label, 'By Status');
    });
  });
}
