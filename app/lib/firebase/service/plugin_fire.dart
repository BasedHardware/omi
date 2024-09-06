import "package:cloud_firestore/cloud_firestore.dart";
import "package:friend_private/firebase/model/plugin_model.dart";

class PluginService {
  PluginService() {
    _fs.settings = const Settings(persistenceEnabled: true);
  }

  final _fs = FirebaseFirestore.instance;

  final _coll = "plugins";

  Future<List<PluginModel>?> getPluginsList() async =>
      _fs.collection(_coll).get(const GetOptions()).then((snapshot) {
        final pluginsModels = <PluginModel>[];
        if (snapshot.docs.isNotEmpty) {
          for (final f in snapshot.docs) {
            //debugPrint("getPluginsList -> ${jsonEncode(f.data())}");
            final pluginsModel = PluginModel.fromJson(f.data())..refId = f.id;
            pluginsModels.add(pluginsModel);
          }
          return pluginsModels;
        } else {
          return null;
        }
      });

  Future<PluginModel?> getPluginsByReferences(String refId) async {
    final DocumentReference reference = _fs.doc(
      "$_coll/$refId",
    );
    final DocumentSnapshot snapshot = await _fs.doc(reference.path).get();
    if (snapshot.data() != null) {
      final pluginsModel =
          PluginModel.fromJson(snapshot.data() as Map<String, dynamic>)
            ..refId = snapshot.id;
      return pluginsModel;
    } else {
      return null;
    }
  }

  Future<bool> updatePlugins(PluginModel pluginsModel) async {
    try {
      return await _fs
          .collection("/$_coll")
          .doc(pluginsModel.refId)
          .set(pluginsModel.toJson())
          .then((value) => true);
    } catch (e) {
      return false;
    }
  }

  Future<bool> deletePlugins(PluginModel pluginsModel) async {
    try {
      if (pluginsModel.refId != null) {
        await _fs.collection("/$_coll").doc(pluginsModel.refId).delete();
        return true;
      } else {
        return false;
      }
    } catch (e) {
      return false;
    }
  }
}
