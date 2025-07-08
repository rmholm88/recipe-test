from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import base64
import requests
import os

app = Flask(__name__)
CORS(app)

# Set your OpenAI API key and GitHub token from environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")
github_token = os.getenv("GITHUB_TOKEN")

def ocr_and_format_html(image_base64):
    client = openai.OpenAI(api_key=openai.api_key)

    response = client.chat.completions.create(
        model="gpt-4-vision",
        messages=[
            {"role": "system", "content": "Extract the recipe from the image and format it as schema.org compatible HTML."},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        max_tokens=2000
    )

    return response.choices[0].message.content

def upload_to_gist(filename, content):
    import sys

    url = "https://api.github.com/gists"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "description": "Recipe HTML File",
        "public": True,
        "files": {
            filename: {
                "content": content
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        return response.json()["files"][filename]["raw_url"]
    else:
        print("❌ GitHub API error:", file=sys.stderr)
        print(f"Status Code: {response.status_code}", file=sys.stderr)
        print(f"Response Text: {response.text}", file=sys.stderr)
        return None


@app.route("/api/process", methods=["POST"])
def process():
    print("📥 Received request to /api/process")
    data = request.get_json()

    if not data or "image" not in data:
        print("⚠️ No image found in request")
        return jsonify({"error": "No image provided"}), 400

    image_base64 = data["image"]

    try:
        print("🔍 Starting OCR and HTML generation")
        html = ocr_and_format_html(image_base64)
        print("✅ HTML successfully generated")

        print("⬆️ Attempting to upload to GitHub Gist")
        html_url = upload_to_gist("recipe.html", html)

        if html_url:
            print(f"✅ Upload succeeded: {html_url}")
            return jsonify({"htmlUrl": html_url})
        else:
            print("❌ Upload to GitHub Gist failed")
            return jsonify({"error": "Failed to upload HTML"}), 500

    except Exception as e:
        print("🔥 Exception occurred:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
