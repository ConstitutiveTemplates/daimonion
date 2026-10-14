import logging

logger = logging.getLogger(__name__)


def log_request(request):
    logger.debug("incoming %s %s body=%s email=%s", request.method, request.path, request.body, request.email)
    print(f"request from {request.email}: {request.body}")
