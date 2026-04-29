from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import openai
import base64
import os
import uuid
import re

app = Flask(__name__)
CORS(app, origins=["https://rmholm88.github.io"])

openai.api_key = os.getenv("OPENAI_API_KEY")
RECIPE_STORE = {}


@app.after_request
def apply_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "https://rmholm88.github.io"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    print(f"❌ Server Error: {e}")
    return jsonify({"error": "Internal Server Error"}), 500

@app.route("/")
def index():
    return "API is running", 200


def ocr_and_format_html(image_base64):
    response = openai.chat.completions.create(
        model="gpt-4o",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert recipe parser. Extract the full recipe from the image. "
                    "Ignore decorative text, bylines, headers, footers, or irrelevant magazine elements. "
                    "Only extract ingredients and instructions. Use context clues like numbers or bullet points to identify steps. "
                    "Return only the inner HTML body fragment — do NOT include <html>, <head>, <body>, or <style> tags. "
                    "Use schema.org Recipe markup with itemprop attributes. "
                    "Strictly wrap the ingredients in a <ul> tag with each item in a <li itemprop='recipeIngredient'>. "
                    "Wrap the instructions in a <ol> tag with each step in a <li itemprop='recipeInstructions'>. "
                    "Use <h1 itemprop='name'> for the recipe title and <p> tags for yield/servings/time. "
                    "Do not use dashes, numbers, or line breaks for formatting — only proper HTML elements. "
                    "At the end, include a <script type='application/ld+json'> block with proper structured data. "
                    "Ensure all content is complete. Do not omit any ingredients or steps."
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
    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    return content.strip()


def extract_body(html):
    """Pull content from between <body> tags; strip html/head wrappers if present."""
    match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    html = re.sub(r'<!DOCTYPE[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'</?html[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<head>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
    return html.strip()


RECIPE_PAGE_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:         #0a0a0a;
    --surface:    #141414;
    --surface-2:  #1c1c1c;
    --border:     #272727;
    --accent:     #00bfa6;
    --accent-dim: rgba(0, 191, 166, 0.1);
    --text:       #f0f0f0;
    --text-muted: #777;
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.65;
    min-height: 100dvh;
  }

  .recipe-hero {
    width: 100%;
    max-height: 340px;
    overflow: hidden;
    background: var(--surface);
  }

  .recipe-hero img {
    width: 100%;
    height: 340px;
    object-fit: cover;
    display: block;
    opacity: 0.92;
  }

  .recipe-body {
    max-width: 680px;
    margin: 0 auto;
    padding: 2rem 1.25rem 3rem;
  }

  h1 {
    font-size: clamp(1.65rem, 5vw, 2.4rem);
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1.12;
    color: var(--text);
    margin-bottom: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
  }

  /* metadata <p> tags */
  h1 ~ p,
  .meta, .meta p {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
  }

  h1 ~ p strong, .meta strong {
    color: var(--text);
    font-weight: 600;
  }

  h2 {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 2rem 0 0.875rem;
  }

  /* ingredients */
  ul {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  ul li {
    display: flex;
    align-items: baseline;
    gap: 0.65rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.93rem;
    border-radius: 8px;
    transition: background 0.15s;
  }

  ul li:hover { background: var(--accent-dim); }

  ul li::before {
    content: '';
    flex-shrink: 0;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--accent);
    opacity: 0.6;
    margin-top: 0.5em;
  }

  /* instructions */
  ol {
    list-style: none;
    counter-reset: steps;
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }

  ol li {
    counter-increment: steps;
    display: grid;
    grid-template-columns: 2rem 1fr;
    gap: 0.875rem;
    align-items: start;
    padding: 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 0.93rem;
    line-height: 1.65;
    transition: border-color 0.15s;
  }

  ol li:hover { border-color: #3a3a3a; }

  ol li::before {
    content: counter(steps);
    font-size: 0.75rem;
    font-weight: 800;
    color: var(--accent);
    background: var(--accent-dim);
    border-radius: 6px;
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .recipe-footer {
    max-width: 680px;
    margin: 0 auto;
    padding: 1rem 1.25rem 2.5rem;
    border-top: 1px solid var(--border);
  }

  .scan-link {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent);
    text-decoration: none;
    opacity: 0.8;
    transition: opacity 0.15s;
  }

  .scan-link:hover { opacity: 1; }

  script[type="application/ld+json"] { display: none; }

  @media (max-width: 480px) {
    .recipe-hero img { height: 220px; }
    ol li { grid-template-columns: 1.75rem 1fr; gap: 0.625rem; padding: 0.875rem; }
    ol li::before { width: 1.75rem; height: 1.75rem; font-size: 0.7rem; }
  }
"""


def build_recipe_page(body_html, recipe_id, has_image):
    hero = ""
    if has_image:
        hero = f"""
  <div class="recipe-hero">
    <img src="/recipes/{recipe_id}/image" alt="Recipe photo" loading="lazy"
         onerror="this.parentElement.style.display='none'">
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Recipe</title>
  <style>{RECIPE_PAGE_CSS}</style>
</head>
<body>
  {hero}
  <div class="recipe-body">
    {body_html}
  </div>
  <div class="recipe-footer">
    <a href="https://rmholm88.github.io/recipe-test/recipe_uploader_app.html" class="scan-link">← Scan another recipe</a>
  </div>
</body>
</html>"""


@app.route("/api/process", methods=["POST", "OPTIONS"])
def process():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json()
    image_base64 = data.get("image")

    if not image_base64:
        return jsonify({"error": "No image provided"}), 400

    print(f"📷 Received image, size: {len(image_base64)} bytes")

    try:
        rendered_html = ocr_and_format_html(image_base64)
        recipe_id = str(uuid.uuid4())

        RECIPE_STORE[recipe_id] = {"html": rendered_html, "image": image_base64}

        print(f"✅ Recipe parsed and stored with ID: {recipe_id}")
        return jsonify({"htmlUrl": f"https://recipe-test.onrender.com/recipes/{recipe_id}"})

    except openai.OpenAIError as oe:
        print(f"❌ OpenAI API error: {oe}")
        return jsonify({"error": "Failed to process image with OpenAI"}), 502

    except Exception as e:
        print(f"❌ Unexpected server error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500


@app.route("/recipes/<recipe_id>/image")
def serve_recipe_image(recipe_id):
    entry = RECIPE_STORE.get(recipe_id)
    if not entry or not entry.get("image"):
        return "Not found", 404
    return Response(base64.b64decode(entry["image"]), mimetype="image/jpeg")


@app.route("/recipes/<recipe_id>")
def serve_recipe(recipe_id):
    entry = RECIPE_STORE.get(recipe_id)
    if not entry:
        return "Recipe not found", 404

    body = extract_body(entry["html"])
    return Response(build_recipe_page(body, recipe_id, has_image=True), mimetype='text/html')


if __name__ == "__main__":
    app.run(debug=True)
