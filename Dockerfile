# Use the official AWS Lambda base image for Python 3.12
FROM public.ecr.aws/lambda/python:3.12 AS base

# Copy the dependency list into the Lambda task root directory
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install Python dependencies without caching to keep the image small
RUN pip install --no-cache-dir -r requirements.txt

# Copy main application files (your Lambda code)
COPY app.py lambda_dashboard.py ${LAMBDA_TASK_ROOT}/

# Copy the 'templates' directory (for Flask/Jinja2 HTML templates, if applicable)
COPY templates/ ${LAMBDA_TASK_ROOT}/templates/

# --- OPTIONAL STAGE: Handle config.json if present ---
# This uses a multi-stage build pattern. The second stage 'final' inherits everything from 'base'.
FROM base AS final

# Copy config.json into the Lambda root directory, but only if it exists in your context
RUN if [ -f config.json ]; then cp config.json ${LAMBDA_TASK_ROOT}/; fi

# Define the Lambda function handler (the entry point)
CMD ["lambda_dashboard.lambda_handler"]
# Note: Change "lambda_dashboard.lambda_handler" to your actual handler if different
# End of Dockerfile
