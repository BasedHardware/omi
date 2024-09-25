---
layout: default
title: Troubleshooting Guide
parent: Backend
nav_order: 8
---

# 🔧 Troubleshooting Guide for Omi Backend

This guide provides solutions to common issues, answers to frequently asked questions, and strategies for diagnosing and resolving problems in the Omi backend system.

## Table of Contents

1. [Installation and Setup Issues](#installation-and-setup-issues)
2. [Authentication and Authorization Problems](#authentication-and-authorization-problems)
3. [Database Connection Issues](#database-connection-issues)
4. [API and WebSocket Errors](#api-and-websocket-errors)
5. [Transcription Service Problems](#transcription-service-problems)
6. [Memory Processing and Storage Issues](#memory-processing-and-storage-issues)
7. [Performance and Scaling Challenges](#performance-and-scaling-challenges)
8. [Deployment and Environment-Specific Problems](#deployment-and-environment-specific-problems)
9. [Security Concerns](#security-concerns)
10. [Debugging Strategies](#debugging-strategies)
11. [Frequently Asked Questions (FAQs)](#frequently-asked-questions-faqs)

## Installation and Setup Issues

### Q: I'm getting "Module not found" errors when running the backend.

A: This is usually due to missing dependencies. Try the following:

1. Ensure you're in the correct virtual environment.
2. Update pip: `pip install --upgrade pip`
3. Reinstall requirements: `pip install -r requirements.txt --no-cache-dir`
4. If a specific module is causing issues, try installing it separately: `pip install <module_name>`

### Q: The backend fails to start with a "Port already in use" error.

A: Another process might be using the required port. Try:

1. Identify the process using the port: `lsof -i :<port_number>`
2. Kill the process: `kill -9 <PID>`
3. If it persists, try changing the port in your configuration.

### Q: I'm having issues setting up Google Cloud credentials.

A: Ensure you've followed these steps:

1. Verify you have the correct `google-credentials.json` file.
2. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable:
   ```
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/google-credentials.json"
   ```
3. If using a service account, ensure it has the necessary permissions in Google Cloud Console.

## Authentication and Authorization Problems

### Q: Users are getting "Unauthorized" errors when trying to access the API.

A: This could be due to several reasons:

1. Check if the Firebase project is correctly set up and linked.
2. Verify that the user's token is being correctly sent in the Authorization header.
3. Ensure the token hasn't expired.
4. Check Firebase security rules to ensure they're not overly restrictive.

### Q: How can I debug Firebase Authentication issues?

A: Try the following:

1. Enable Firebase Authentication debug mode in your code:
   ```python
   firebase_admin.initialize_app(credentials, {'debugMode': True})
   ```
2. Check Firebase Console for any error messages or invalid login attempts.
3. Verify that the Firebase configuration in your `.env` file is correct.

## Database Connection Issues

### Q: I'm getting "Connection refused" errors with Firestore.

A: This could be due to network issues or incorrect configuration:

1. Check your internet connection.
2. Verify that your Firestore database exists and is properly set up in Google Cloud Console.
3. Ensure your service account has the necessary permissions to access Firestore.
4. Check if there are any outages reported in the Google Cloud Status Dashboard.

### Q: Pinecone operations are failing with authentication errors.

A: Verify your Pinecone setup:

1. Check if the `PINECONE_API_KEY` in your `.env` file is correct.
2. Ensure you're using the correct Pinecone environment and index name.
3. Verify that your Pinecone plan supports the operations you're trying to perform.

## API and WebSocket Errors

### Q: WebSocket connections are frequently disconnecting.

A: This could be due to various reasons:

1. Check if the client is sending regular heartbeat messages to keep the connection alive.
2. Increase the WebSocket timeout settings on both client and server sides.
3. Verify that there are no network issues or firewalls blocking WebSocket traffic.
4. Check server logs for any errors that might be causing the disconnections.

### Q: API requests are timing out.

A: This could be due to performance issues or network problems:

1. Check the server logs for any long-running operations that might be causing delays.
2. Monitor server resource usage (CPU, memory) to ensure it's not overloaded.
3. Verify that all external service calls (e.g., to OpenAI, Deepgram) are properly timing out and not blocking the API.
4. Consider implementing caching for frequently accessed data to improve response times.

## Transcription Service Problems

### Q: Transcription accuracy is poor or inconsistent.

A: Try the following:

1. Check the audio quality being sent to the transcription services.
2. Verify that the correct language model is being used for the input audio.
3. Ensure that the VAD (Voice Activity Detection) is properly filtering out non-speech audio.
4. Consider adjusting the confidence threshold for accepting transcription results.

### Q: One of the transcription services (Deepgram, Soniox, Speechmatics) is consistently failing.

A: Troubleshoot the specific service:

1. Check if the API key for the service is correct and not expired.
2. Verify that the service is operational by checking its status page.
3. Try sending a test request directly to the service API to isolate the issue.
4. Review the service's documentation for any recent changes or known issues.

## Memory Processing and Storage Issues

### Q: Memory embeddings are not being generated correctly.

A: This could be due to issues with the OpenAI API or the embedding process:

1. Check if the OpenAI API key is correct and has sufficient quota.
2. Verify that the embedding model (e.g., "text-embedding-3-large") is available and properly specified.
3. Ensure that the input text for embedding generation is properly formatted and not too long.
4. Check for any errors in the embedding generation process in the logs.

### Q: Stored memories are missing data or have incorrect information.

A: This could be due to issues in the memory processing pipeline:

1. Review the memory processing logic in `utils/memories/process_memory.py` for any bugs.
2. Check if all required fields are being properly extracted and stored.
3. Verify that the structured data extraction from OpenAI is working correctly.
4. Ensure that the Firestore write operations are successful and not being interrupted.

## Performance and Scaling Challenges

### Q: The backend is slow to respond during high traffic periods.

A: Consider the following optimizations:

1. Implement caching for frequently accessed data using Redis.
2. Optimize database queries and indexes in Firestore.
3. Use asynchronous processing for time-consuming tasks.
4. Consider scaling up your Google Cloud Run instances or implementing auto-scaling.

### Q: Memory retrieval is becoming slow as the number of memories increases.

A: Optimize your vector search process:

1. Ensure you're using efficient filtering in Pinecone queries.
2. Implement pagination for large result sets.
3. Consider using approximate nearest neighbor search instead of exact search for larger datasets.
4. Optimize your embedding model or quantize embeddings to reduce dimensionality.

## Deployment and Environment-Specific Problems

### Q: The backend works locally but fails when deployed to Google Cloud Run.

A: This could be due to environment differences:

1. Ensure all environment variables are correctly set in Google Cloud Run.
2. Check if all required services (Firestore, Pinecone, etc.) are accessible from Google Cloud Run.
3. Review the Cloud Run logs for any specific error messages.
4. Verify that the Dockerfile is correctly configured and all dependencies are included.

### Q: How can I debug issues in the production environment?

A: Use the following strategies:

1. Enable detailed logging in your production environment.
2. Use Google Cloud's Error Reporting and Logging services to monitor issues.
3. Implement feature flags to easily enable/disable certain functionalities for debugging.
4. Consider setting up a staging environment that mirrors production for testing.

## Security Concerns

### Q: How can I ensure that user data is properly isolated and secured?

A: Implement the following security measures:

1. Use Firebase Security Rules to restrict data access based on user authentication.
2. Implement proper input validation and sanitization for all API endpoints.
3. Use encryption for sensitive data both in transit and at rest.
4. Regularly audit and rotate API keys and other secrets.

### Q: I'm concerned about potential vulnerabilities in dependencies.

A: Address dependency security:

1. Regularly update dependencies to their latest secure versions.
2. Use tools like `safety` to check for known vulnerabilities in Python packages.
3. Implement a process for reviewing and approving dependency updates.
4. Consider using a dependency scanning tool in your CI/CD pipeline.

## Debugging Strategies

### General Debugging Tips

1. **Enable Verbose Logging**: Temporarily increase log levels to get more detailed information.
2. **Use Debuggers**: Utilize pdb or IDE debuggers to step through code execution.
3. **Isolate the Problem**: Try to reproduce the issue in a minimal, isolated environment.
4. **Check Recent Changes**: Review recent code changes that might have introduced the issue.

### Debugging Specific Components

1. **WebSocket Issues**: Use browser developer tools to inspect WebSocket traffic.
2. **Database Problems**: Use database admin consoles to directly query and verify data.
3. **API Errors**: Use tools like Postman to test API endpoints independently.

## Frequently Asked Questions (FAQs)

### Q: How can I optimize the performance of the transcription process?

A: Consider the following:
1. Use efficient audio encoding (e.g., Opus) to reduce bandwidth usage.
2. Implement client-side VAD to reduce the amount of audio sent for transcription.
3. Fine-tune the balance between real-time responsiveness and transcription accuracy.

### Q: What should I do if I suspect a memory leak in the backend?

A: Follow these steps:
1. Use memory profiling tools like `memory_profiler` to identify the source of the leak.
2. Check for any resources (e.g., database connections, file handles) that aren't being properly closed.
3. Review your code for any large objects that are being unnecessarily retained in memory.

### Q: How can I troubleshoot issues with the Modal serverless deployment?

A: Try the following:
1. Use Modal's built-in logging and monitoring tools to identify issues.
2. Ensure all required environment variables and secrets are properly set in Modal.
3. Test your functions locally using Modal's local development features before deployment.

### Q: What steps should I take if I suspect a security breach?

A: Follow this protocol:
1. Immediately revoke and rotate all potentially compromised API keys and secrets.
2. Review access logs and audit trails to identify the extent of the breach.
3. Temporarily disable affected services or endpoints if necessary.
4. Conduct a thorough security audit and implement any necessary additional security measures.

### Q: How can I improve the accuracy of speaker identification?

A: Consider these approaches:
1. Collect more diverse speech samples for each known speaker.
2. Experiment with different speaker recognition models or fine-tune the existing model.
3. Implement a confidence threshold for speaker identification to reduce false positives.

### Q: What should I do if the emotional analysis results seem inaccurate?

A: Try the following:
1. Verify that the audio quality is sufficient for accurate emotional analysis.
2. Check if the Hume AI API is being used correctly and with appropriate parameters.
3. Consider collecting user feedback on emotional analysis results to improve the system over time.

Remember, troubleshooting is often an iterative process. Start with the most likely causes and work your way through more complex possibilities. Don't hesitate to reach out to the Omi community or support channels for assistance with particularly challenging issues.
