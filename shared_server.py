from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
note_requests = {}
comment_list_requests = {}

@app.route("/set_note", methods=["POST"])
def set_note():
    data = request.json
    note_id = data["note_id"]
    print(note_id, data["url"])
    note_requests[note_id] = {
        "url": data["url"],
        "data": data["data"]
    }
    return jsonify({"status": "ok"})

@app.route("/set_comment_list", methods=["POST"])
def set_comment_list():
    data = request.json
    note_id = data["note_id"]
    comment_list_requests[note_id] = {
        "url": data["url"],
        "data": data["data"]
    }
    return jsonify({"status": "ok"})

@app.route("/get_note/<note_id>")
def get_note(note_id):
    json_data = jsonify(note_requests.get(note_id, {}))
    del note_requests[note_id]  # Remove after fetching
    return json_data

@app.route("/get_comment_list/<note_id>")
def get_comment_list(note_id):
    json_data = jsonify(comment_list_requests.get(note_id, {}))
    del comment_list_requests[note_id]  # Remove after fetching
    return json_data

if __name__ == "__main__":
    app.run(port=int(os.getenv("SHARED_SERVER_PORT")))