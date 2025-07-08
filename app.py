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
        model="gpt-4-vision-preview",
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
        return jsonify({"error": "No image provided"}), 400

    try:
        html = ocr_and_format_html(image_base64)
        html_url = upload_to_gist("recipe.html", html)
        if html_url:
            return jsonify({"htmlUrl": html_url})
        else:
            return jsonify({"error": "Failed to upload HTML"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
