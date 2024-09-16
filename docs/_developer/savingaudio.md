---
layout: default
title: Storing Audio
nav_order: 6
---
# 🎧 Creating a Google Cloud Storage Bucket for Audio Files 🎧

This guide will walk you through setting up a Google Cloud Storage (GCS) bucket perfect for keeping your 🎶 audio files 🎶 safe and sound. We'll set it up with the right permissions and give you the keys 🔑 (credentials) so you can easily upload and manage your tunes.

## 🚀 Prerequisites 🚀

* An active Google Cloud Platform (GCP) account.
* A little bit of experience navigating the GCP console.

## 🪣 Step 1: Create Your Audio Bucket 🪣

1. **Head to the GCS Console:**
   - Log in to your GCP account and go to the [Google Cloud Storage console](https://console.cloud.google.com/storage/browser).
2. **Click "CREATE BUCKET":** 
   -  Hit that button to get started! 
3. **Let's Set Up Your Bucket:**
   - **Name your bucket:**  Pick a unique name that follows the [naming guidelines](https://cloud.google.com/storage/docs/naming-buckets#requirements). Get creative, but keep it relevant! Example: `friend-audio-files`.
   - **Where should we store your audio?:** Choose a location that makes sense for you. Think about how quickly you need to access your files and your budget. A **Multi-region** is great for extra reliability across a wider area, while a **Region** gives you faster access in a specific spot.
   - **Pick a storage class:**  **Standard** is usually the best choice for files you access often. If you have audio you don't need very often, check out the other options (Nearline, Coldline, Archive) to save some 💰.
   - **Control who can access your files:**
     - **Public access prevention:** Keep this **"On"** to make sure your audio stays private. 🤫
     - **Access control:**  Stick with **"Uniform"** for consistent permissions across all your audio files.
   - **Extra protection for your tunes:**
     - **Soft delete policy:** This is already on by default – it's like a safety net if you accidentally delete something! 
     - **Object versioning:** Want to keep track of changes and easily recover older versions? Turn this on!
     - **Object retention policy:**  If you need to keep audio for a specific amount of time, use this to set rules. 
     - **Encryption type:** Google will keep your audio encrypted by default – you don't need to do anything here unless you have special requirements.
4. **Time to Create:**
   - Double-check everything and click **"CREATE"**.
5. **Success!**
   - You'll get a message letting you know your bucket is ready to rock. 🤘

## 🔐 Step 2: Create a Service Account 🔐 

Think of this like a special ID card for your app to access the bucket.

1. **Go to "IAM & Admin":**
   - Find it in the GCP console menu.
2. **Click "Service Accounts":**
   - This is where we'll make that ID card.
3. **"CREATE SERVICE ACCOUNT":**
   - Click the button to get started.
4. **Fill in the Details:**
   - **Service account name:**  Give it a clear name. Example: `test-service-account-friend-app`.
   - **Service account description:**  What will this account do? (e.g., "Uploads audio to the friend-audio-files bucket").
5. **Give Permissions (Optional):**
   - **Select a role:** Search for and select **"Storage Object User"**. This gives your app permission to work with the audio files in your bucket.
6. **Grant Users Access (Optional):**
   - We can skip this for now – we'll use a key instead.
7. **Create that Account!**
   - Review and click **"DONE"**.

## 🔑 Step 3: Get Your Key 🔑

1. **Find Your Service Account:**
   - Go back to the service accounts list and click on the one you just created.
2. **Click "KEYS":**
   - Time to get that access key!
3. **Add a New Key:**
   - Click **"ADD KEY"** and then **"Create new key"**.
4. **Choose "JSON":**
   - This is the format we need.
5. **Create!**
   - Click **"CREATE"**, and the key file will download to your computer.
   - **Keep it Safe!**  This key gives your app access to your bucket – don't share it publicly!

## 🧬 Step 4: Convert to Base64 🧬

This step turns your key file into a special code we can use in the app.

**Option 1: Command Line**

1. **Open Your Terminal:**
   - Open a terminal or command prompt.
2. **Go to Your Key:**
   - Use `cd` to navigate to where you saved the key file.
3. **Run This Command:**
   - Replace `your-key-file.json` with the actual name of your key file:
     ```bash
     base64 your-key-file.json
     ```
4. **Copy the Code:**
   - You'll get a long string of text – this is your Base64 encoded key! Copy it.

**Option 2: Website Converter**

1. **Go to the Converter:**
   - Visit [https://codebeautify.org/json-to-base64-converter](https://codebeautify.org/json-to-base64-converter).
2. **Paste Your Key:**
   - Open your `json` key file and copy the entire contents.
3. **Convert!**
   - Paste the key contents into the website's input box and click **"JSON to Base64"**.
4. **Copy the Base64:**
   - Copy the encoded text from the output box.

## 📝 Step 5: Grab Your Bucket Name 📝

1. **Back to the GCS Console:**
   - Go back to the [Google Cloud Storage console](https://console.cloud.google.com/storage/browser).
2. **Find Your Bucket:**
   - You'll see it in the list.
3. **Copy the Name:**
   - Click on your bucket's name and copy it from the **"Bucket details"** page.

## 🎉 You're All Set! 🎉

You now have two important pieces:

* **GCP Credentials Base64:** Your special encoded key.
* **GCP Bucket Name:** The name of your audio bucket.

### 📱Last Step📱
1. Open the app
2. Goto Settings
3. Enable Developer Mode
4. Select Developer Mode (scroll down)
5. Enter your GCP Credentails and GCP Bucket Name
6. SAVE 🚀

Watch the magic and check out those sweet sounds! 🎶

## Contributing 🤝

We welcome contributions from the open source community! Whether it's improving documentation, adding new features, or reporting bugs, your input is valuable. Check out our [Contribution Guide](https://docs.omi.me/developer/Contribution/) for more information.

## Support 🆘

If you're stuck, have questions, or just want to chat about Omi:

- **GitHub Issues: 🐛** For bug reports and feature requests
- **Community Forum: 💬** Join our [community forum](https://discord.gg/ZutWMTJnwA) for discussions and questions
- **Documentation: 📚** Check out our [full documentation](https://docs.omi.me/) for in-depth guides

Happy coding! 💻 If you have any questions or need further assistance, don't hesitate to reach out to our community.
