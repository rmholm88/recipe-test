from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import openai
import base64
import os
import uuid

app = Flask(__name__)
CORS(app)  # 👈 Needed for frontend to talk to backend

openai.api_key = os.getenv("OPENAI_API_KEY")

RECIPE_STORE = {}

@app.route("/")
def index():
    return "API is running", 200

def ocr_and_format_html(image_base64):
    response = openai.chat.completions.create(
        model="gpt-4o",
        temperature=0,  # 🔒 Make output deterministic
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert recipe parser. Extract the full recipe from the image. "
                    "Return it as valid semantic HTML using schema.org Recipe markup. "
                    "Clearly format the recipe title, ingredients (as a <ul> list), instructions (as an ordered <ol> list), "
                    "and yield/serving size. At the bottom, include a <script type='application/ld+json'> block with proper structured data. "
                    "Ensure all content is complete and readable. Do not omit any ingredients or steps."
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


@app.route("/api/process", methods=["POST"])
def process():
    data = request.get_json()
    image_base64 = data.get("image")

    if not image_base64:
        return jsonify({"error": "No image provided"}), 400

    try:
        rendered_html = ocr_and_format_html(image_base64)

        recipe_id = str(uuid.uuid4())
        RECIPE_STORE[recipe_id] = rendered_html

        return jsonify({"htmlUrl": f"https://recipe-test.onrender.com/recipes/{recipe_id}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/recipes/<recipe_id>")
def serve_recipe(recipe_id):
    html = RECIPE_STORE.get(recipe_id)
    if not html:
        return "Recipe not found", 404
    return Response(html, mimetype='text/html')

if __name__ == "__main__":
    app.run(debug=True)

