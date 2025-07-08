# Step 1: Flask App (app.py)
# Place this in a file named app.py

from flask import Flask, request, jsonify
import openai
import base64
import requests
import os

app = Flask(__name__)

# Set your OpenAI API key and GitHub token in environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")
github_token = os.getenv("GITHUB_TOKEN")

def ocr_and_format_html(image_base64):
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[
            {"role": "system", "content": "Extract the recipe from the image and format it as schema.org compatible HTML."},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            }
        ],
        max_tokens=2000
    )
    return response.choices[0].message.content

def upload_to_gist(filename, content):
    url = "https://api.github.com/gists"
    headers = {
        "Authorization": f"token {github_token}"
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
        return None

@app.route("/api/process", methods=["POST"])
def process():
    data = request.get_json()
    image_base64 = data.get("image")
    if not image_base64:
        print("❌ No image provided.")
        return jsonify({"error": "No image provided"}), 400

    try:
        print("✅ Received image. Sending to OpenAI...")
        html = ocr_and_format_html(image_base64)
        print("✅ Got response from OpenAI.")

        html_url = upload_to_gist("recipe.html", html)
        if html_url:
            print("✅ Uploaded to GitHub Gist.")
            return jsonify({"htmlUrl": html_url})
        else:
            print("❌ Failed to upload to Gist.")
            return jsonify({"error": "Failed to upload HTML"}), 500
    except Exception as e:
        print("🔥 Exception occurred:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
