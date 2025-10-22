FROM public.ecr.aws/lambda/python:3.12

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py ${LAMBDA_TASK_ROOT}
COPY lambda_dashboard.py ${LAMBDA_TASK_ROOT}

# Copy templates folder
COPY templates/ ${LAMBDA_TASK_ROOT}/templates/

# Copy config if exists
COPY config.json ${LAMBDA_TASK_ROOT}/ 2>/dev/null || true

# Set the Lambda handler
CMD ["lambda_dashboard.lambda_handler"]
