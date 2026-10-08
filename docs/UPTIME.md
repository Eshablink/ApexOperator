# Keeping the hosted demo warm

ApexOperator's Render free-tier service can sleep between requests. The public portfolio demo explains the cold start in the UI instead of looking broken.

For a simple external keep-warm monitor:

1. Create a free monitor in UptimeRobot.
2. Use \`https://apexoperator.onrender.com/health\` as the URL.
3. Set the monitor interval to the longest interval your plan supports (10 minutes is a common choice).
4. Treat HTTP 200 as healthy.
5. Do not monitor authenticated endpoints.

The application also surfaces a non-blocking "Waking up the server · ~30s" state and a Retry action when the hosted API is slow or unavailable.

This monitor is optional; it is not part of the application's trust boundary.
