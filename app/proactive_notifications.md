# Proactive Notifications

Proactive notifications are a part of Omi's backend infrastructure that allow applications inside the Omi ecosystem to send contextual, data-driven messages directly to users. These notifications leverage a scope-based system to determine what data is available for drafting personalized and relevant messages.
Assuming you are going to build an app on OMI 

## First Submit Your App
Submit your app using the Omi mobile app.
# Setting up your own first App
1. Go to explore inside of OMIs APP select Create your own
2. Click create an App and fill out all necessary components for the App you have in mind 


The webhook URL should be a POST request in which the memory object is sent as a JSON payload.

The setup completed URL is optional and should be a GET endpoint that returns {'is_setup_completed': boolean}.

The auth URL is optional as well and is utilized by users to setup your app. The uid query paramater will be appended to this URL upon usage.

---
## 🔧 Use Cases

- Notify a user about a live conversation or memory they should review.  
- Offer personalized coaching or follow-ups based on conversation tone.  
- Recommend actions, suggestions, content, or tools based on real-time emotional context.  
- Alert users at key moments to keep them present during long conversations.

---

## ⚙️ System Architecture

1. **Trigger Events:** The app backend detects an event that should notify a user.  
2. **Scope Resolution:** Data scopes (e.g., memory, event context, emotional state) are evaluated to determine what information is available.  
3. **Token Resolution:** The user's device push token is fetched.  
4. **Delivery:** The notification is sent through a push provider (APNs or FCM).

---

## 🛠️ Implementation Guide

### Step 0: Set Up an Ngrok Tunnel (For Local Development)

To receive incoming webhook calls during development, you can use [Ngrok](https://ngrok.com/) to expose your local server:

1. Open a separate terminal window.  
2. Run:  
    ```bash
    ngrok http 8000
    ```  
3. Ngrok will provide a public HTTPS URL that looks something like (e.g.,  
   `https://d2c1-207-53-253-3.ngrok-free.app`) which you can use as your webhook base URL. 
  
4. But inside omi your webhook will look like so 
    `https://d2c1-207-53-253-3.ngrok-free.app/api/v1/transcripts/livetranscript` 

5. Configure this webhook URL inside your Omi app settings.

---

### Step 1: Handle Real-time Transcript Segments

Your app needs to handle transcript segments as they arrive in real-time:

1. **Segment Processing:**
   - Segments arrive in multiple calls as the conversation unfolds
   - Use the session_id to maintain context across calls
   - Implement smart logic to avoid redundant processing
   - Build a complete conversation context by accumulating segments
   - Clear processed segments to prevent re-triggering on future calls

2. **Error Handling & Performance:**
   - Handle errors gracefully, especially for network issues
   - Consider performance implications for lengthy conversations
   - Implement retry logic for failed segment processing
   - Monitor memory usage when accumulating segments

3. **Testing Your Integration:**
   - Open the OMI app on your device
   - Go to Settings and enable Developer Mode or Inside Manage App
   - Navigate to Developer and or Manage App Settings
   - Set your endpoint URL in the "Memory Creation Webhook" field
   - Test with existing memories:
     - Go to any memory detail view
     - Click on the top right corner (3 dots menu)
     - In the Developer Tools section, trigger the endpoint call with existing memory data

For reference, check the Realtime News checker Python Example and its respective JSON format for implementation details.

---

### Step 2: Compose and Send a Notification

Your backend or plugin should send a notification payload to the Omi notification API like this:

**POST /api/notifications/send**
```json
{
"user_id": "user123",
"type": "trigger_event",
"message": "Reminder: Your PR review is coming up.",
"data": {
 "deep_link": "/memories/abc123"
}
}
