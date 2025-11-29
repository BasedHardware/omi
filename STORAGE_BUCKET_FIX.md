# Fix Google Cloud Storage Bucket Access for App Logos

## Issue
The `nooto-plugins-logos` bucket is private, causing app logo images to return 403 Forbidden errors in the admin panel.

## Solution: Make the Bucket Public

### Option 1: Using Google Cloud Console (Web UI)

1. Go to [Google Cloud Console Storage](https://console.cloud.google.com/storage/browser)
2. Select your project (e.g., `nooto-e2d27` or `based-hardware`)
3. Find and click on the `nooto-plugins-logos` bucket
4. Click on the **Permissions** tab
5. Click **+ GRANT ACCESS**
6. In "New principals", enter: `allUsers`
7. In "Role", select: **Storage Object Viewer**
8. Click **SAVE**
9. Confirm the warning about making the bucket public

### Option 2: Using gcloud CLI

```bash
# Authenticate to Google Cloud
gcloud auth login

# Set your project
gcloud config set project nooto-e2d27

# Make the bucket publicly readable
gsutil iam ch allUsers:objectViewer gs://nooto-plugins-logos

# Verify the change
gsutil iam get gs://nooto-plugins-logos
```

### Option 3: Using Python (in your backend)

Add this to your backend startup or run it once:

```python
from google.cloud import storage

# Initialize client
storage_client = storage.Client()
bucket = storage_client.bucket('nooto-plugins-logos')

# Make all objects in the bucket publicly readable
policy = bucket.get_iam_policy(requested_policy_version=3)
policy.bindings.append(
    {
        "role": "roles/storage.objectViewer",
        "members": {"allUsers"},
    }
)
bucket.set_iam_policy(policy)

print("Bucket nooto-plugins-logos is now publicly readable")
```

## Verification

After making the bucket public, test with curl:

```bash
curl -I https://storage.googleapis.com/nooto-plugins-logos/01KB3VM1B8HAVVH5V652EHS6JN.png
```

You should see `HTTP/2 200` instead of `HTTP/2 403`.

## Security Note

Making the bucket public means anyone with the URL can access the app logos. This is generally fine for app logos as they're meant to be publicly visible. However, ensure:

1. No sensitive data is stored in this bucket
2. The bucket only contains app logos/images
3. You have appropriate bucket lifecycle policies to manage storage costs

## Alternative: Use Signed URLs (More Secure)

If you prefer not to make the bucket public, you can generate signed URLs in the backend:

### Update `storage.py`:

```python
from datetime import timedelta

def get_signed_app_logo_url(app_id: str) -> str:
    bucket = storage_client.bucket(omi_apps_bucket)
    blob = bucket.blob(f'{app_id}.png')

    # Generate a signed URL that expires in 1 hour
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(hours=1),
        method="GET",
    )
    return url
```

Then update the app retrieval logic to replace storage URLs with signed URLs before sending to frontend.

## Recommended Approach

For app logos, **making the bucket public** (Option 1 or 2) is the simplest and most efficient solution since:
- App logos are meant to be publicly visible anyway
- No authentication overhead
- Better performance (CDN-friendly)
- Simpler frontend code

---

**Current Bucket**: `nooto-plugins-logos`
**Environment Variable**: `BUCKET_PLUGINS_LOGOS`
**Affected Feature**: Admin panel app review (and likely public app listings)
