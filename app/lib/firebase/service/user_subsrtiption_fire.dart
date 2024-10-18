import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../../backend/preferences.dart';
import '../model/user_subscription_model.dart';

class UserSubscriptionFire {
  UserSubscriptionFire() {
    _fs.settings = const Settings(persistenceEnabled: true);
  }

  final _fs = FirebaseFirestore.instance;
  final _coll = "user_subscription";

  Future<List<UserSubscriptionModel>> getUserSubscription() async {
    QuerySnapshot<Map<String, dynamic>> snapshot = await _fs
        .collection(_coll)
        .where("user_id",
            isEqualTo: FirebaseAuth.instance.currentUser?.uid ?? "")
        .get();

    final userSubscriptionModels = <UserSubscriptionModel>[];
    if (snapshot.docs.isNotEmpty) {
      for (final f in snapshot.docs) {
        final userSubscriptionModel = UserSubscriptionModel.fromJson(f.data())
          ..userId = SharedPreferencesUtil().uid;
        userSubscriptionModels.add(userSubscriptionModel);
      }
      return userSubscriptionModels;
    }

    return [];
  }

  List<UserSubscriptionModel> userSubscriptionList = [];
}
