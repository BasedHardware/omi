const https = require('https');

/**
 * Sends a direct notification to an Omi user.
 * Retrieves OMI_APP_ID and OMI_APP_SECRET from environment variables.
 *
 * @param {string} sessionId The session ID (or user identifier) of the Omi user to send the notification to.
 * @param {string} message The text content of the notification.
 * @returns {Promise<object>} A promise that resolves with the API response data on success, or rejects on error.
 */
function sendOmiNotification(sessionId, message) {
    const appId = process.env.OMI_APP_ID;
    const appSecret = process.env.OMI_APP_SECRET;

    if (!appId) {
        throw new Error("OMI_APP_ID environment variable is not set.");
    }
    if (!appSecret) {
        throw new Error("OMI_APP_SECRET environment variable is not set.");
    }

    const omiApiBaseUrl = "api.omi.me"; // Just the host, no http/https
    const endpointPath = `/v2/integrations/${appId}/notification`;

    // Encode the message and user ID for URL query parameters
    const encodedMessage = encodeURIComponent(message);
    const encodedSessionId = encodeURIComponent(sessionId); // Using sessionId for the 'uid' parameter

    const queryString = `uid=${encodedSessionId}&message=${encodedMessage}`;
    const fullPath = `${endpointPath}?${queryString}`;

    const options = {
        hostname: omiApiBaseUrl,
        path: fullPath,
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${appSecret}`,
            'Content-Type': 'application/json',
            'Content-Length': 0 // No body being sent for direct messages
        }
    };

    return new Promise((resolve, reject) => {
        const req = https.request(options, (res) => {
            let data = '';

            res.on('data', (chunk) => {
                data += chunk;
            });

            res.on('end', () => {
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    console.log(`Notification sent successfully! Status Code: ${res.statusCode}`);
                    try {
                        resolve(data ? JSON.parse(data) : {});
                    } catch (e) {
                        resolve({ message: 'Success, but response not JSON', raw: data });
                    }
                } else {
                    const errorMsg = `Omi API Error (Status ${res.statusCode}): ${data}`;
                    console.error(errorMsg);
                    reject(new Error(errorMsg));
                }
            });
        });

        req.on('error', (e) => {
            console.error(`Problem with request: ${e.message}`);
            reject(e);
        });

        req.end();
    });
}

// --- How to use the function ---
// This block runs when the script is executed directly for testing
if (require.main === module) {
    // Example usage:
    const TARGET_SESSION_ID = "Nosqs0W7E0YL3o0lORE9HewcYtt2"; // Replace with an actual session/user ID
    const NOTIFICATION_MESSAGE = "This is a test notification from your Node.js app!";

    console.log("Attempting to send notification...");
    sendOmiNotification(TARGET_SESSION_ID, NOTIFICATION_MESSAGE)
        .then(response => {
            console.log("Full API Response:", response);
        })
        .catch(error => {
            console.error("Failed to send notification:", error.message);
            process.exit(1); // Exit with an error code if notification fails
        });
}

// Export the function for use in other modules
module.exports = sendOmiNotification;