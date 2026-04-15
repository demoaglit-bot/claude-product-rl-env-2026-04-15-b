import json
import os
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
SEED_PATH = ROOT / "data" / "seed.json"
STATIC_PATH = ROOT / "static" / "index.html"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_seed() -> dict:
    return json.loads(SEED_PATH.read_text())


STATE = load_seed()


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def html_response(handler, html: str, status=HTTPStatus.OK):
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def find_conversation(conversation_id: str):
    return next((item for item in STATE["conversations"] if item["id"] == conversation_id), None)


def visible_conversations(search: str = ""):
    items = STATE["conversations"]
    if not search:
        return items
    needle = search.lower()
    return [
        item
        for item in items
        if needle in item["title"].lower() or needle in item["summary"].lower()
    ]


def ensure_current_conversation() -> dict:
    conversation = find_conversation(STATE["ui"]["selectedConversationId"])
    if conversation:
        return conversation
    fallback = STATE["conversations"][0]
    STATE["ui"]["selectedConversationId"] = fallback["id"]
    return fallback


def deterministic_assistant_reply(prompt: str) -> str:
    excerpt = " ".join(prompt.strip().split())[:160] or "Empty prompt"
    return (
        "Deterministic Claude environment reply. "
        f"Observed request excerpt: {excerpt}. "
        "Recommended next step: review the action items, verify the artifact, and continue the workflow."
    )


def observable_state() -> dict:
    conversation = ensure_current_conversation()
    search_value = STATE["ui"].get("searchQuery", "")
    artifact_id = STATE["ui"].get("openArtifactId")
    artifact = next((item for item in conversation.get("artifacts", []) if item["id"] == artifact_id), None)
    return {
        "workspace": STATE["workspace"],
        "current_conversation_id": conversation["id"],
        "visible_conversations": visible_conversations(search_value),
        "conversation": conversation,
        "composer": STATE["composer"],
        "ui": STATE["ui"],
        "open_artifact": artifact,
        "feedback_log": STATE["feedback_log"],
    }


def select_conversation(conversation_id: str):
    conversation = find_conversation(conversation_id)
    if not conversation:
        return None
    STATE["ui"]["selectedConversationId"] = conversation_id
    STATE["ui"]["openArtifactId"] = None
    return conversation


def create_turn(role: str, content: str, message_id: str) -> dict:
    return {
        "id": message_id,
        "role": role,
        "content": content,
        "created_at": now_iso(),
    }


def submit_prompt(prompt: str):
    conversation = ensure_current_conversation()
    user_message = create_turn("user", prompt, f"msg_{len(conversation['messages']) + 1}")
    assistant_message = create_turn(
        "assistant",
        deterministic_assistant_reply(prompt),
        f"msg_{len(conversation['messages']) + 2}",
    )
    conversation["messages"].extend([user_message, assistant_message])
    conversation["summary"] = assistant_message["content"][:96]
    conversation["updated_at"] = assistant_message["created_at"]
    draft = STATE["composer"].get("draft", "")
    STATE["composer"] = {
        "draft": "",
        "lastSubmittedPrompt": prompt,
        "draftHistory": [draft] + STATE["composer"].get("draftHistory", []),
    }
    return assistant_message


def open_artifact(artifact_id: str):
    conversation = ensure_current_conversation()
    artifact = next((item for item in conversation.get("artifacts", []) if item["id"] == artifact_id), None)
    if not artifact:
        return None
    STATE["ui"]["openArtifactId"] = artifact_id
    return artifact


def log_feedback(message_id: str, rating: str):
    entry = {
        "message_id": message_id,
        "rating": rating,
        "created_at": now_iso(),
        "conversation_id": STATE["ui"]["selectedConversationId"],
    }
    STATE["feedback_log"].insert(0, entry)
    return entry


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html_response(self, STATIC_PATH.read_text())
            return
        if parsed.path == "/api/state":
            query = parse_qs(parsed.query)
            search = query.get("search", [""])[0]
            if search != STATE["ui"].get("searchQuery", ""):
                STATE["ui"]["searchQuery"] = search
            json_response(self, observable_state())
            return
        json_response(self, {"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        global STATE
        parsed = urlparse(self.path)
        payload = read_json(self)
        if parsed.path == "/api/reset":
            STATE = load_seed()
            json_response(self, observable_state())
            return
        if parsed.path == "/api/conversations/select":
            conversation = select_conversation(payload["conversation_id"])
            if not conversation:
                json_response(self, {"error": "Conversation not found"}, status=HTTPStatus.NOT_FOUND)
                return
            json_response(self, observable_state())
            return
        if parsed.path == "/api/composer":
            STATE["composer"]["draft"] = payload.get("draft", "")
            json_response(self, observable_state())
            return
        if parsed.path == "/api/messages":
            prompt = payload.get("prompt", "").strip()
            if not prompt:
                json_response(self, {"error": "Prompt is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            message = submit_prompt(prompt)
            json_response(self, {"message": message, "state": observable_state()})
            return
        if parsed.path == "/api/artifacts/open":
            artifact = open_artifact(payload["artifact_id"])
            if not artifact:
                json_response(self, {"error": "Artifact not found"}, status=HTTPStatus.NOT_FOUND)
                return
            json_response(self, observable_state())
            return
        if parsed.path == "/api/feedback":
            entry = log_feedback(payload["message_id"], payload.get("rating", "thumbs_up"))
            json_response(self, {"feedback": entry, "state": observable_state()})
            return
        json_response(self, {"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):
        return


def main():
    port = int(os.environ.get("PORT", "8000"))
    address = ("127.0.0.1", port)
    server = ThreadingHTTPServer(address, Handler)
    print(f"Claude RL environment listening on http://{address[0]}:{address[1]}")
    server.serve_forever()


if __name__ == "__main__":
    main()
