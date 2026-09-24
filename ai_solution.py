```javascript
import { Firestore } from "google-cloud firestore";
// ... (other imports)

export async function publish.desktop().preview() {
  const db = new Firestore({ projectId: "your-project-id" });
  const manifestRef = db.collection("desktop_manifests").doc("current");
  const slugsRef = db.collection("slugs").doc("slug");

  let manifest;
  let slug;

  try {
    const transaction = db.runTransaction(async (transaction) => {
      const snapshot = await transaction.get(manifestRef);
      manifest = snapshot.data();

      const slugsSnapshot = await transaction.get(slugsRef);
      slug = slugsSnapshot.data().slug;
      
      await transaction.set(manifestRef, {
        ...manifest,
        version: (manifest.version || 0) + 1,
        builds: {
          ...(manifest.builds || {}),
          [slug]: {
            commitHash: process.env.CIRCLE_SHA1,
            timestamp: new Date().toISOString()
          }
        }
      });
    });

    return {
      slug: slug,
      manifest: manifest
    };
  } catch (error) {
    console.error("Failed to publish desktop preview:", error);
    throw error;
  }
}
```