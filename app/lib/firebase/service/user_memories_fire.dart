import "package:cloud_firestore/cloud_firestore.dart";
import "package:firebase_auth/firebase_auth.dart";
import "package:flutter/material.dart";
import "package:friend_private/firebase/model/user_memories_model.dart";

class UserMemoriesService {
  UserMemoriesService() {
    _fs.settings = const Settings(persistenceEnabled: true);
  }

  final _fs = FirebaseFirestore.instance;

  final _coll = "users";
  final _subColl = "memories";

  Future<List<UserMemoriesModel>?> getUserMemoriesList() async => _fs
          .collection(_coll)
          .doc(FirebaseAuth.instance.currentUser!.uid)
          .collection(_subColl)
          .get(const GetOptions())
          .then((snapshot) {
        final userMemoriesModels = <UserMemoriesModel>[];
        if (snapshot.docs.isNotEmpty) {
          for (final f in snapshot.docs) {
            //debugPrint("getUserMemoriesList -> ${jsonEncode(f.data())}");
            try {
              final userMemoriesModel = UserMemoriesModel.fromJson(f.data())
                ..refId = f.id;
              userMemoriesModels.add(userMemoriesModel);
            } catch (e) {
              debugPrint(e.toString());
            }
          }
          return userMemoriesModels;
        } else {
          return null;
        }
      });

  Future<UserMemoriesModel?> getUserMemoriesByReferences(String refId) async {
    final DocumentReference reference = _fs.doc(
      "$_coll/${FirebaseAuth.instance.currentUser!.uid}/$_subColl/$refId",
    );
    final DocumentSnapshot snapshot = await _fs.doc(reference.path).get();
    if (snapshot.data() != null) {
      final userMemoriesModel =
          UserMemoriesModel.fromJson(snapshot.data() as Map<String, dynamic>)
            ..refId = snapshot.id;
      return userMemoriesModel;
    } else {
      return null;
    }
  }

  Future<bool> updateUserMemories(
    UserMemoriesModel userMemoriesModel,
  ) async {
    try {
      return await _fs
          .collection("/$_coll")
          .doc(FirebaseAuth.instance.currentUser!.uid)
          .collection(_subColl)
          .doc(userMemoriesModel.refId)
          .set(userMemoriesModel.toJsonTimeStamp())
          .then((value) => true);
    } catch (e) {
      return false;
    }
  }

  Future<bool> deleteUserMemories(
    UserMemoriesModel userMemoriesModel,
  ) async {
    try {
      if (userMemoriesModel.refId != null) {
        await _fs
            .collection("/$_coll")
            .doc(FirebaseAuth.instance.currentUser!.uid)
            .collection(_subColl)
            .doc(userMemoriesModel.refId)
            .delete();
        return true;
      } else {
        return false;
      }
    } catch (e) {
      return false;
    }
  }
}
