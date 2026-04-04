import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            429: "rate_limited",
        }
        response.data["error_code"] = error_code_map.get(
            response.status_code,
            f"http_{response.status_code}",
        )
        return response

    logger.exception(
        "Unhandled exception in view: %s",
        context.get("view").__class__.__name__ if context.get("view") else "unknown",
    )
    return Response(
        {
            "detail": "An unexpected error occurred.",
            "error_code": "internal_error",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )