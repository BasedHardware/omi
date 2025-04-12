// Calendar management functionality

// Utility function to safely get DOM elements
function getElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        console.error(`Element with id '${id}' not found`);
    }
    return element;
}

// Utility function to add status messages
function addStatus(message, type) {
    // Use error-handler.js functions if available
    if (type === 'error' && typeof window.showError === 'function') {
        window.showError(message);
        return null;
    } else if (type === 'success' && typeof window.showSuccess === 'function') {
        window.showSuccess(message);
        return null;
    }
    
    // Fallback to original implementation
    const statusContainer = getElement('status-container');
    if (!statusContainer) {
        console.error(`Status container not found, message was: ${message}`);
        // Create a floating message as last resort
        const floatingDiv = document.createElement('div');
        floatingDiv.className = `status ${type}`;
        floatingDiv.style.position = 'fixed';
        floatingDiv.style.top = '20px';
        floatingDiv.style.left = '50%';
        floatingDiv.style.transform = 'translateX(-50%)';
        floatingDiv.style.zIndex = '9999';
        floatingDiv.textContent = message;
        document.body.appendChild(floatingDiv);
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            if (floatingDiv.parentNode) {
                floatingDiv.parentNode.removeChild(floatingDiv);
            }
        }, 5000);
        
        return floatingDiv;
    }

    const statusDiv = document.createElement('div');
    statusDiv.className = `status ${type}`;
    statusDiv.textContent = message;
    statusContainer.insertBefore(statusDiv, statusContainer.firstChild);
    return statusDiv;
}

// Function to get user ID from URL
function getUserId() {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('uid');
}

// Check authentication status
async function checkAuth() {
    try {
        const response = await fetch('/check_auth');
        if (!response.ok) {
            throw new Error('Authentication check failed');
        }
        const data = await response.json();
        return data.authenticated;
    } catch (error) {
        console.error('Auth check error:', error);
        return false;
    }
}

// Make loadCalendars available globally immediately
window.loadCalendars = async function() {
    const loadingElement = getElement('loading');
    const calendarList = getElement('calendar-list');
    const importBtn = getElement('import-btn');
    const statusContainer = getElement('status-container');

    if (!loadingElement || !calendarList || !importBtn || !statusContainer) {
        console.error('Required page elements not found');
        // Try to show error in a more resilient way
        const errorDiv = document.createElement('div');
        errorDiv.className = 'status error';
        errorDiv.textContent = 'Required page elements not found. Please refresh the page.';
        document.body.insertBefore(errorDiv, document.body.firstChild);
        return;
    }

    // Check for user ID
    const userId = getUserId();
    if (!userId) {
        addStatus('User ID is required', 'error');
        return;
    }

    // Check authentication first
    const isAuthenticated = await checkAuth();
    if (!isAuthenticated) {
        addStatus('Authentication required. Please authenticate with Google Calendar.', 'error');
        return;
    }

    // Fetch calendars
    fetch('/get_calendars?uid=' + encodeURIComponent(userId))
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(calendars => {
            // Hide loading indicator
            loadingElement.style.display = 'none';
            
            if (calendars.length === 0) {
                addStatus('No calendars found', 'error');
                return;
            }
            
            // Add calendars to list
            calendars.forEach(calendar => {
                const li = document.createElement('li');
                li.className = 'calendar-item';
                li.innerHTML = `
                    <input type="radio" name="calendar" id="calendar-${calendar.id}" value="${calendar.id}">
                    <label for="calendar-${calendar.id}">${calendar.summary}</label>
                `;
                calendarList.appendChild(li);
                
                // Add click event to select calendar
                li.addEventListener('click', function() {
                    const radio = this.querySelector('input[type="radio"]');
                    radio.checked = true;
                    
                    // Enable import button when a calendar is selected
                    importBtn.disabled = false;
                    
                    // Remove selected class from all items
                    document.querySelectorAll('.calendar-item').forEach(item => {
                        item.classList.remove('selected');
                    });
                    
                    // Add selected class to clicked item
                    this.classList.add('selected');
                });
            });
        })
        .catch(error => {
            // Safely hide loading element if it exists
            if (loadingElement) {
                loadingElement.style.display = 'none';
            }
            
            // Handle different types of errors
            if (error.code === 403 || (error.message && error.message.includes('403'))) {
                addStatus('Permission error: Please authenticate with Google Calendar', 'error');
                // Redirect to auth page
                window.location.href = `/auth?uid=${encodeURIComponent(userId)}&redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
            } else if (error.name === 'TypeError' && error.message.includes('null')) {
                addStatus('Error: Unable to access page elements. Please refresh the page.', 'error');
            } else {
                addStatus(`Error loading calendars: ${error.message || 'Unknown error occurred'}`, 'error');
            }
            console.error('Calendar loading error:', error);
        });
};

// Initialize event handlers when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    const calendarForm = getElement('calendar-form');
    if (!calendarForm) {
        addStatus('Calendar form not found. Please refresh the page.', 'error');
        return;
    }
    
    // Handle form submission
    calendarForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const selectedCalendar = document.querySelector('input[name="calendar"]:checked');
        const daysBackInput = getElement('days-back');
        const importBtn = getElement('import-btn');
        const syncModeCheckbox = getElement('sync-mode');
        
        if (!selectedCalendar) {
            addStatus('Please select a calendar', 'error');
            return;
        }

        if (!daysBackInput) {
            addStatus('Days back input not found', 'error');
            return;
        }

        const daysBack = parseInt(daysBackInput.value, 10);
        if (isNaN(daysBack) || daysBack < 1) {
            addStatus('Please enter a valid number of days (minimum 1)', 'error');
            return;
        }
        
        const userId = getUserId();
        if (!userId) {
            addStatus('User ID is required', 'error');
            return;
        }
        
        // Disable import button and show loading state
        importBtn.disabled = true;
        importBtn.innerHTML = '<span class="loading-spinner"></span>Processing...';
        
        // Check if continuous sync is enabled
        const isContinuousSync = syncModeCheckbox && syncModeCheckbox.checked;
        
        if (isContinuousSync) {
            // Set up continuous synchronization with Composio
            fetch('/sync_calendar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    calendar_id: selectedCalendar.value,
                    user_id: userId
                })
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(data => {
                        throw new Error(data.error || 'Failed to set up synchronization');
                    });
                }
                return response.json();
            })
            .then(data => {
                // Reset button state
                importBtn.disabled = false;
                importBtn.innerHTML = 'Import Events';
                
                // Show success message
                addStatus(`Calendar synchronization set up successfully! Your calendar events will now be automatically imported to OMI.`, 'success');
            })
            .catch(error => {
                // Reset button state
                importBtn.disabled = false;
                importBtn.innerHTML = 'Import Events';
                
                // Show error message
                addStatus(`Error: ${error.message}`, 'error');
            });
        } else {
            // Perform one-time import
            fetch('/import_events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    calendar_id: selectedCalendar.value,
                    user_id: userId,
                    days_back: parseInt(daysBack)
                })
            })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            addStatus(data.message, 'success');
            // Re-enable import button and restore original text
            importBtn.disabled = false;
            importBtn.textContent = 'Import Events';
        })
        .catch(error => {
            // Handle different types of errors
            if (error.code === 403 || (error.message && error.message.includes('403'))) {
                addStatus('Permission error: Please ensure you are properly authenticated with Google Calendar', 'error');
            } else if (error.name === 'TypeError' && error.message.includes('null')) {
                addStatus('Error: Unable to access page elements. Please refresh the page.', 'error');
            } else {
                addStatus(`Error importing events: ${error.message || 'Unknown error occurred'}`, 'error');
            }
            console.error('Import error:', error);
            
            // Re-enable import button and restore original text
            if (importBtn) {
                importBtn.disabled = false;
                importBtn.textContent = 'Import Events';
            }
        });
        }
    });
    });

// Calendar initialization is handled by the HTML file's DOMContentLoaded event