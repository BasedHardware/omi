const functions = require("firebase-functions");
const admin = require("firebase-admin");

exports.notifyUsersToStartRecurrentNew = functions.pubsub
  .schedule("every 60 minutes")
  .onRun(async (data, context) => {
    const hours = 1; // Default to 1 if not provided
    const firestore = admin.firestore();
    const usersRef = firestore.collection("users");
    const memoriesRef = firestore.collection("memories");

    try {
      const usersSnapshot = await usersRef.get();
      const allUsers = usersSnapshot.docs.map((doc) => doc.id);
      console.log(`Number of users: ${allUsers.length}`);
      const xHoursAgoMillis =
        admin.firestore.Timestamp.now().toMillis() - hours * 60 * 60 * 1000;
      const xHoursAgoSeconds = Math.floor(xHoursAgoMillis / 1000);
      const xHoursAgoTimestamp = new admin.firestore.Timestamp(
        xHoursAgoSeconds,
        0,
      );
      const recentMemoriesSnapshot = await memoriesRef
        .where("date", ">", xHoursAgoTimestamp)
        .get();
      const activeUsers = new Set();
      const userPromises = recentMemoriesSnapshot.docs.map(async (doc) => {
        const memoryData = doc.data();
        const userDocRef = memoryData.user;
        const userDocSnapshot = await userDocRef.get();

        if (userDocSnapshot.exists) {
          const userData = userDocSnapshot.data();
          const userId = userData.uid;
          activeUsers.add(userId);
        }
      });

      await Promise.all(userPromises);

      const inactiveUsers = allUsers.filter(
        (userId) => !activeUsers.has(userId),
      );

      for (const userId of inactiveUsers) {
        const fcmTokensRef = admin
          .firestore()
          .collection("users")
          .doc(userId)
          .collection("fcm_tokens");
        const tokensSnapshot = await fcmTokensRef.get();

        let lastFcmToken = null;
        tokensSnapshot.forEach((doc) => {
          const tokenData = doc.data();
          if (tokenData.fcm_token) {
            lastFcmToken = tokenData.fcm_token; // Set to the last token found
          }
        });

        if (lastFcmToken != null) {
          const payload = {
            notification: {
              title: "Sama",
              body: `Your transcription has been off for ${hours} hour(s). Open the app and turn on perfect memory again!`,
            },
            token: lastFcmToken,
          };

          try {
            await admin.messaging().send(payload);
            console.log(`Notification sent to user: ${userId}`);
          } catch (error) {
            console.error(
              `Failed to send notification to user: ${userId}`,
              error,
            );
          }
        }
      }

      return {
        result: `Notifications sent to ${inactiveUsers.length} inactive users`,
      };
    } catch (error) {
      console.error("Error processing users:", error);
      throw new functions.https.HttpsError(
        "internal",
        "Error processing users",
      );
    }
  });

exports.scheduleUserNotification = functions.pubsub
  .schedule("35 * * * *")
  .timeZone("America/Los_Angeles")
  .onRun((context) => {
    console.log("Scheduler function triggered");

    try {
      const data = { hours: 1 };
      exports.notifyUsersToStart(data, context);
      console.log("Scheduled notification function executed successfully");
    } catch (error) {
      console.error("Error executing scheduled function:", error);
    }
  });
