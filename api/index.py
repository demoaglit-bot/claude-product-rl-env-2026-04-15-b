import json
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

import app as rl_app

OPENAPI_PATH = Path(__file__).with_name("openapi.yaml")


def _status_line(status: HTTPStatus) -> str:
    return f"{status.value} {status.phrase}"


def _json_response(payload, status=HTTPStatus.OK):
    body = json.dumps(payload).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    return status, headers, [body]


def _text_response(body: str, status=HTTPStatus.OK, content_type="text/plain; charset=utf-8"):
    encoded = body.encode("utf-8")
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(encoded))),
    ]
    return status, headers, [encoded]


def _read_json(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    raw = environ["wsgi.input"].read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO") or "/"

    status = HTTPStatus.NOT_FOUND
    headers = []
    body = []

    if method == "GET":
        if path == "/":
            status, headers, body = _text_response(rl_app.STATIC_PATH.read_text(), content_type="text/html; charset=utf-8")
        elif path == "/api/state":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            search = query.get("search", [""])[0]
            if search != rl_app.STATE["ui"].get("searchQuery", ""):
                rl_app.STATE["ui"]["searchQuery"] = search
            status, headers, body = _json_response(rl_app.observable_state())
        elif path == "/api/openapi.yaml":
            status, headers, body = _text_response(OPENAPI_PATH.read_text(), content_type="application/yaml; charset=utf-8")
        else:
            status, headers, body = _json_response({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
    elif method == "POST":
        payload = _read_json(environ)
        if path == "/api/reset":
            rl_app.STATE = rl_app.load_seed()
            status, headers, body = _json_response(rl_app.observable_state())
        elif path == "/api/conversations/select":
            conversation = rl_app.select_conversation(payload["conversation_id"])
            if not conversation:
                status, headers, body = _json_response({"error": "Conversation not found"}, status=HTTPStatus.NOT_FOUND)
            else:
                status, headers, body = _json_response(rl_app.observable_state())
        elif path == "/api/composer":
            rl_app.STATE["composer"]["draft"] = payload.get("draft", "")
            status, headers, body = _json_response(rl_app.observable_state())
        elif path == "/api/messages":
            prompt = payload.get("prompt", "").strip()
            if not prompt:
                status, headers, body = _json_response({"error": "Prompt is required"}, status=HTTPStatus.BAD_REQUEST)
            else:
                message = rl_app.submit_prompt(prompt)
                status, headers, body = _json_response({"message": message, "state": rl_app.observable_state()})
        elif path == "/api/artifacts/open":
            artifact = rl_app.open_artifact(payload["artifact_id"])
            if not artifact:
                status, headers, body = _json_response({"error": "Artifact not found"}, status=HTTPStatus.NOT_FOUND)
            else:
                status, headers, body = _json_response(rl_app.observable_state())
        elif path == "/api/feedback":
            entry = rl_app.log_feedback(payload["message_id"], payload.get("rating", "thumbs_up"))
            status, headers, body = _json_response({"feedback": entry, "state": rl_app.observable_state()})
        else:
            status, headers, body = _json_response({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
    else:
        status, headers, body = _json_response({"error": "Method not allowed"}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    start_response(_status_line(status), headers)
    return body
