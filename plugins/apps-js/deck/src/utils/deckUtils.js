const https = require('https');

/**
 * Sends a direct notification to a Deck user.
 * Retrieves DECK_APP_ID and DECK_APP_SECRET from environment variables.
 *
 * @param {string} sessionId The session ID (or user identifier) of the Deck user to send the notification to.
 * @param {string} message The text content of the notification.
 * @returns {Promise<object>} A promise that resolves with the API response data on success, or rejects on error.
 */
function sendDeckNotification(sessionId, message) {
    const appId = process.env.DECK_APP_ID;
    const appSecret = process.env.DECK_APP_SECRET;

    if (!appId) {
        throw new Error("DECK_APP_ID environment variable is not set.");
    }
    if (!appSecret) {
        throw new Error("DECK_APP_SECRET environment variable is not set.");
    }

    const deckApiBaseUrl = "api.omi.me"; // Using the same API base URL
    const endpointPath = `/v2/integrations/${appId}/notification`;

    // Encode the message and user ID for URL query parameters
    const encodedMessage = encodeURIComponent(message);
    const encodedSessionId = encodeURIComponent(sessionId); // Using sessionId for the 'uid' parameter

    const queryString = `uid=${encodedSessionId}&message=${encodedMessage}`;
    const fullPath = `${endpointPath}?${queryString}`;

    const options = {
        hostname: deckApiBaseUrl,
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
                    console.log(`Deck notification sent successfully! Status Code: ${res.statusCode}`);
                    try {
                        resolve(data ? JSON.parse(data) : {});
                    } catch (e) {
                        resolve({ message: 'Success, but response not JSON', raw: data });
                    }
                } else {
                    const errorMsg = `Deck API Error (Status ${res.statusCode}): ${data}`;
                    console.error(errorMsg);
                    reject(new Error(errorMsg));
                }
            });
        });

        req.on('error', (e) => {
            console.error(`Problem with deck notification request: ${e.message}`);
            reject(e);
        });

        req.end();
    });
}

/**
 * Sends a presentation ready notification with viewer link
 * @param {string} sessionId The session ID
 * @param {string} viewerUrl The viewer URL for the presentation
 * @returns {Promise<object>} Promise that resolves with API response
 */
function sendPresentationReadyNotification(sessionId, viewerUrl) {
    const message = `🎯 Your presentation is ready! View it here: ${viewerUrl}`;
    return sendDeckNotification(sessionId, message);
}

/**
 * Sends a presentation generation started notification
 * @param {string} sessionId The session ID
 * @param {string} viewerUrl The viewer URL for tracking progress
 * @returns {Promise<object>} Promise that resolves with API response
 */
function sendPresentationStartedNotification(sessionId, viewerUrl) {
    const message = `🚀 Your presentation is being generated! Track progress here: ${viewerUrl}`;
    return sendDeckNotification(sessionId, message);
}

/**
 * Sends a presentation generation failed notification
 * @param {string} sessionId The session ID
 * @param {string} error The error message
 * @returns {Promise<object>} Promise that resolves with API response
 */
function sendPresentationFailedNotification(sessionId, error) {
    const message = `❌ Failed to generate your presentation: ${error}. Please try again with "hey deck".`;
    return sendDeckNotification(sessionId, message);
}

// --- How to use the function ---
// This block runs when the script is executed directly for testing
if (require.main === module) {
    // Example usage:
    const TARGET_SESSION_ID = "Nosqs0W7E0YL3o0lORE9HewcYtt2"; // Replace with an actual session/user ID
    const NOTIFICATION_MESSAGE = "This is a test deck notification from your Node.js app!";

    console.log("Attempting to send deck notification...");
    sendDeckNotification(TARGET_SESSION_ID, NOTIFICATION_MESSAGE)
        .then(response => {
            console.log("Full Deck API Response:", response);
        })
        .catch(error => {
            console.error("Failed to send deck notification:", error.message);
            process.exit(1); // Exit with an error code if notification fails
        });
}

// Export the functions for use in other modules
module.exports = {
    sendDeckNotification,
    sendPresentationReadyNotification,
    sendPresentationStartedNotification,
    sendPresentationFailedNotification
}; 