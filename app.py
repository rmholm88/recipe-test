from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import openai
import base64
import os
import uuid

app = Flask(__name__)
CORS(app, origins=["https://rmholm88.github.io"])

openai.api_key = os.getenv("OPENAI_API_KEY")

RECIPE_STORE = {}

@app.route("/")
def index():
    return "API is running", 200

def ocr_and_format_html(image_base64):
    response = openai.chat.completions.create(
        model="gpt-4o",
        temperature=0.3,  # 🔓 Allow some flexibility in response
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert recipe parser. Extract the full recipe from the image. "
                    "Return valid semantic HTML using schema.org Recipe markup. "
                    "Strictly wrap the ingredients in a <ul> tag with each item in a <li>. "
                    "Wrap the instructions in a <ol> tag with each step in a separate <li>. "
                    "Use <h1> for the recipe title and include <p> for yield/servings. "
                    "At the bottom, include a <script type='application/ld+json'> block with proper structured data. "
                    "Ensure all content is complete and readable. Do not omit any ingredients or steps. "

                    "Ignore decorative text, bylines, headers, footers, or irrelevant magazine elements. "
                    "Only extract ingredients and instructions. "
                    "Use context clues like numbers or bullet points to identify steps."
                )
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            }
        ],
        max_tokens=2000
    )
    return response.choices[0].message.content


@app.route("/api/process", methods=["POST", "OPTIONS"])
def process():
    if request.method == "OPTIONS":
        response = Response()
        response.headers.add("Access-Control-Allow-Origin", "https://rmholm88.github.io")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response, 204

    data = request.get_json()
    image_base64 = data.get("image")

    if not image_base64:
        response = jsonify({"error": "No image provided"})
        response.headers.add("Access-Control-Allow-Origin", "https://rmholm88.github.io")
        return response, 400

    try:
        rendered_html = ocr_and_format_html(image_base64)

        recipe_id = str(uuid.uuid4())
        RECIPE_STORE[recipe_id] = rendered_html

        response = jsonify({"htmlUrl": f"https://recipe-test.onrender.com/recipes/{recipe_id}"})
        response.headers.add("Access-Control-Allow-Origin", "https://rmholm88.github.io")
        return response
    except Exception as e:
        response = jsonify({"error": str(e)})
        response.headers.add("Access-Control-Allow-Origin", "https://rmholm88.github.io")
        return response, 500


@app.route("/recipes/<recipe_id>")
def serve_recipe(recipe_id):
    html = RECIPE_STORE.get(recipe_id)
    if not html:
        return "Recipe not found", 404
    return Response(html, mimetype='text/html')


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    response = jsonify({"error": str(e)})
    response.headers.add("Access-Control-Allow-Origin", "https://rmholm88.github.io")
    return response, 500


if __name__ == "__main__":
    app.run(debug=True)

