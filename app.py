from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "success",
        "message": "BeautyMind AI API is running"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy"
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}

    # TODO:
    # Put your BeautyMind AI processing logic here.
    # Example:
    # result = your_beautymind_function(data)

    return jsonify({
        "status": "success",
        "message": "Analysis endpoint is working",
        "received": data
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
