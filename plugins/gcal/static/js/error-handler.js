// Error handling functionality for Google Calendar integration

/**
 * Safely shows an error message
 * @param {string} message - The error message to display
 */
window.showError = function(message) {
    // First try to use the dedicated error-message element
    const errorDiv = document.getElementById('error-message');
    
    // If error-message element doesn't exist, create a temporary one or use status container
    if (!errorDiv) {
        // Try to use the status container as fallback
        const statusContainer = document.getElementById('status-container');
        if (statusContainer) {
            const tempErrorDiv = document.createElement('div');
            tempErrorDiv.className = 'status error';
            tempErrorDiv.textContent = message;
            statusContainer.insertBefore(tempErrorDiv, statusContainer.firstChild);
            
            // Auto-hide after 5 seconds
            setTimeout(() => {
                if (tempErrorDiv.parentNode) {
                    tempErrorDiv.parentNode.removeChild(tempErrorDiv);
                }
            }, 5000);
        } else {
            // Last resort: create a floating error message
            const floatingError = document.createElement('div');
            floatingError.style.position = 'fixed';
            floatingError.style.top = '20px';
            floatingError.style.left = '50%';
            floatingError.style.transform = 'translateX(-50%)';
            floatingError.style.backgroundColor = '#f2dede';
            floatingError.style.color = '#a94442';
            floatingError.style.padding = '10px';
            floatingError.style.borderRadius = '5px';
            floatingError.style.zIndex = '9999';
            floatingError.textContent = message;
            document.body.appendChild(floatingError);
            
            // Auto-hide after 5 seconds
            setTimeout(() => {
                if (floatingError.parentNode) {
                    floatingError.parentNode.removeChild(floatingError);
                }
            }, 5000);
        }
    } else {
        // Use the existing error-message element
        errorDiv.textContent = message;
        errorDiv.hidden = false;
        setTimeout(() => errorDiv.hidden = true, 5000);
    }
    
    // Also log to console
    console.error(message);
}

/**
 * Safely shows a success message
 * @param {string} message - The success message to display
 */
window.showSuccess = function(message) {
    // Try to use the status container
    const statusContainer = document.getElementById('status-container');
    if (statusContainer) {
        const successDiv = document.createElement('div');
        successDiv.className = 'status success';
        successDiv.textContent = message;
        statusContainer.insertBefore(successDiv, statusContainer.firstChild);
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            if (successDiv.parentNode) {
                successDiv.parentNode.removeChild(successDiv);
            }
        }, 5000);
    } else {
        // Fallback: create a floating success message
        const floatingSuccess = document.createElement('div');
        floatingSuccess.style.position = 'fixed';
        floatingSuccess.style.top = '20px';
        floatingSuccess.style.left = '50%';
        floatingSuccess.style.transform = 'translateX(-50%)';
        floatingSuccess.style.backgroundColor = '#dff0d8';
        floatingSuccess.style.color = '#3c763d';
        floatingSuccess.style.padding = '10px';
        floatingSuccess.style.borderRadius = '5px';
        floatingSuccess.style.zIndex = '9999';
        floatingSuccess.textContent = message;
        document.body.appendChild(floatingSuccess);
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            if (floatingSuccess.parentNode) {
                floatingSuccess.parentNode.removeChild(floatingSuccess);
            }
        }, 5000);
    }
}