"""Thin Flask blueprint for `POST /api/match`.

Route handling here is intentionally thin: parse and validate the multipart
request, delegate to `pipeline.run_pipeline`, and translate exceptions into
the right HTTP status/JSON shape. No business logic lives in this module.
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from .config import get_config
from .content_matching import AnthropicContentMatchAdapter
from .extraction import AnthropicExtractionAdapter
from .pipeline import PipelineInput, ProcessingError, RawUpload, run_pipeline
from .validation import UploadValidationError

api_blueprint = Blueprint("api", __name__)

_FIELDS = ("po", "grn", "invoice")


def _validation_error_response(field: str, message: str) -> tuple[Response, int]:
    return jsonify({"type": "validation_error", "field": field, "message": message}), 400


@api_blueprint.post("/api/match")
def match() -> tuple[Response, int]:
    uploads: dict[str, RawUpload] = {}
    for field in _FIELDS:
        files = request.files.getlist(field)
        if len(files) != 1:
            return _validation_error_response(field, f"{field}: exactly one file is required.")
        file_storage = files[0]
        uploads[field] = RawUpload(filename=file_storage.filename or field, data=file_storage.read())

    try:
        config = get_config()
    except RuntimeError:
        return (
            jsonify(
                {
                    "type": "processing_error",
                    "message": "Server is not configured with an Anthropic API key.",
                    "retryable": False,
                }
            ),
            500,
        )

    extraction_adapter = AnthropicExtractionAdapter(config)
    content_match_adapter = AnthropicContentMatchAdapter(config)

    try:
        result = run_pipeline(
            PipelineInput(po=uploads["po"], grn=uploads["grn"], invoice=uploads["invoice"]),
            config,
            extraction_adapter,
            content_match_adapter,
        )
        return jsonify(result.model_dump(mode="json")), 200
    except UploadValidationError as err:
        return _validation_error_response(err.field, err.message)
    except ProcessingError as err:
        status = 503 if err.retryable else 502
        return jsonify({"type": "processing_error", "message": str(err), "retryable": err.retryable}), status
    except Exception:  # noqa: BLE001 - last-resort guard; no business decision on unexpected errors
        return (
            jsonify({"type": "processing_error", "message": "Unexpected server error.", "retryable": False}),
            500,
        )
