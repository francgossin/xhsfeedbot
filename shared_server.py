import sys
import os
import logging
from dotenv import load_dotenv
from typing import Any
from flask import Flask, request, jsonify

load_dotenv()
app = Flask(__name__)
note_requests: dict[str, Any] = {}
comment_list_requests: dict[str, Any] = {}

logger = logging.getLogger()
formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d %(levelname)s %(module)s: %(message)s",datefmt=r"%H:%M:%S")
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)

@app.route("/set_note", methods=["POST"])
def set_note():
    data = request.json
    if data is None:
        return jsonify({"status": "error", "message": "No data provided"}), 400
    note_id = data["note_id"]
    note_requests[note_id] = {
        "url": data["url"],
        "data": data["data"]
    }
    logger.info(f"Note set: {note_id}, {data['url']}")
    return jsonify({"status": "ok"})

@app.route("/set_comment_list", methods=["POST"])
def set_comment_list():
    data = request.json
    if data is None:
        return jsonify({"status": "error", "message": "No data provided"}), 400
    note_id = data["note_id"]
    comment_list_requests[note_id] = {
        "url": data["url"],
        "data": data["data"]
    }
    logger.info(f"Comment list set: {note_id}, {data['url']}")
    return jsonify({"status": "ok"})

@app.route("/get_note/<note_id>")
def get_note(note_id: str):
    json_data = jsonify(note_requests.get(note_id, {}))
    del note_requests[note_id]  # Remove after fetching
    logger.info(f"Note fetched: {note_id}")
    return json_data

@app.route("/get_comment_list/<note_id>")
def get_comment_list(note_id: str):
    json_data = jsonify(comment_list_requests.get(note_id, {}))
    del comment_list_requests[note_id]  # Remove after fetching
    logger.info(f"Comment list fetched: {note_id}")
    return json_data

if __name__ == "__main__":
    port = os.getenv("SHARED_SERVER_PORT")
    app.run(port=int(port) if port else 5001)