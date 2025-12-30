# =============================================================================
# VD-SPEED-TEST Lambda Container Image (Multi-Handler, Optimized for Size)
# =============================================================================
# Supports all 3 Lambda handlers in a single image.
# Set the handler at runtime via AWS_LAMBDA_FUNCTION_HANDLER env var or CMD override.
#
# Build:   docker build -t vd-speedtest-lambda .
# Size:    ~150-180MB (optimized)
#
# Deploy examples:
#   Dashboard:  docker run -e AWS_LAMBDA_FUNCTION_HANDLER=lambda_dashboard.lambda_handler ...
#   Aggregator: docker run -e AWS_LAMBDA_FUNCTION_HANDLER=lambda_function.lambda_handler ...
#   Checker:    docker run -e AWS_LAMBDA_FUNCTION_HANDLER=lambda_hourly_check.lambda_handler ...
# =============================================================================

FROM public.ecr.aws/lambda/python:3.12-minimal AS builder

# Install build dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --target /opt/python -r /tmp/requirements.txt \
    && find /opt/python -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /opt/python -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /opt/python -type f -name "*.pyo" -delete 2>/dev/null || true \
    && find /opt/python -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true \
    && find /opt/python -type d -name "test" -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /opt/python/pip* /opt/python/setuptools* /opt/python/wheel* 2>/dev/null || true

# =============================================================================
# Final Stage - Minimal Runtime
# =============================================================================
FROM public.ecr.aws/lambda/python:3.12-minimal

# Copy optimized dependencies from builder
COPY --from=builder /opt/python ${LAMBDA_TASK_ROOT}

# Copy only essential application files (no .pyc, no tests)
COPY app.py ${LAMBDA_TASK_ROOT}/
COPY lambda_dashboard.py ${LAMBDA_TASK_ROOT}/
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
COPY lambda_hourly_check.py ${LAMBDA_TASK_ROOT}/
COPY s3_speed_utils.py ${LAMBDA_TASK_ROOT}/
COPY config.json ${LAMBDA_TASK_ROOT}/
COPY shared/ ${LAMBDA_TASK_ROOT}/shared/
COPY templates/ ${LAMBDA_TASK_ROOT}/templates/

# Clean up any bytecode
RUN find ${LAMBDA_TASK_ROOT} -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Default handler (Dashboard) - override at runtime for other handlers
# AWS Lambda will use CMD as the handler, or you can override with:
#   ImageConfig.Command in SAM/CloudFormation
#   --entrypoint in docker run
CMD ["lambda_dashboard.lambda_handler"]
