const functions = require("firebase-functions");
const admin = require("firebase-admin");
// To avoid deployment errors, do not call admin.initializeApp() in your code
exports.checkUserMemory = functions.pubsub
  .schedule("every 5 minutes")
  .onRun(async (context) => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
    const memoriesRef = admin.firestore().collection("memories");
    const usersRef = admin.firestore().collection("users");

    const usersSnapshot = await usersRef.get();
    for (const userDoc of usersSnapshot.docs) {
      const userId = userDoc.id;
      const userMemoriesSnapshot = await memoriesRef
        .where("userId", "==", userId)
        .orderBy("date", "desc")
        .limit(1)
        .get();

      // Assuming you would have a function to get the token for a user
      const userNotificationToken = await getUserNotificationToken(userId);

      if (
        userMemoriesSnapshot.empty ||
        userMemoriesSnapshot.docs[0].data().date.toDate() < oneHourAgo
      ) {
        // It's been more than an hour since the last memory or no memories exist
        if (userNotificationToken) {
          await sendNotification(userNotificationToken, userId);
        } else {
          console.log(`No notification token for user ${userId}`);
        }
      }
    }
  });

async function getUserNotificationToken(userId) {
  // Placeholder: Implement the logic to retrieve the user's notification token
  // For example, it might be stored in a 'tokens' subcollection or in the user document
  // const tokenDoc = await admin.firestore().collection('users').doc(userId).collection('tokens').doc('notification').get();
  // return tokenDoc.exists ? tokenDoc.data().token : null;

  return "user-device-token"; // Replace this with the actual token retrieval logic
}

async function sendNotification(token, userId) {
  const payload = {
    notification: {
      title: "Check your mic",
      body: "Re-enable your AI mentor to continue recordings",
    },
    token: token,
    data: {
      userID: userId, // Send user ID in the payload if needed for client-side handling
    },
  };

  try {
    const response = await admin.messaging().send(payload);
    console.log("Successfully sent message:", response);
  } catch (error) {
    console.error("Error sending message to user", userId, error);
  }
}
