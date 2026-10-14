import logging

logger = logging.getLogger(__name__)


def _redact(body):
    # Stand-in for a real PII scrubber: drop values, keep keys.
    return {k: "***" for k in body}


def log_request(request):
    logger.debug("incoming %s %s body_keys=%s", request.method, request.path, sorted(request.body))
    logger.debug("request body (redacted): %s", _redact(request.body))
