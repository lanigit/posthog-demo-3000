// Ensure the posthog-js library is correctly imported
import posthog from 'posthog-js';

posthog.init('phc_sR3UFhd7ztezvCTZLgERXguZNNtMQyhEqR7y9qedHZb6', { api_host: 'https://us.i.posthog.com' });

// Track page views
posthog.capture('$pageview');

// Example of tracking a custom event
function trackButtonClick(buttonName) {
    posthog.capture('button_clicked', { button_name: buttonName });
}

// Identify user after login or signup
function identifyUser(userEmail) {
    posthog.identify(userEmail);
}

// Export functions for use in other scripts
export { trackButtonClick, identifyUser };
