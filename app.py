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
                    "Use <h1 itemprop='name'> for the recipe title and <p> tags for yield/servings/time. "
                    "Use <h2>Ingredients</h2> before the ingredients list and <h2>Instructions</h2> before the steps — these are required. "
                    "Strictly wrap the ingredients in a <ul> tag with each item in a <li itemprop='recipeIngredient'>. "
                    "Wrap the instructions in a <ol> tag with each step in a <li itemprop='recipeInstructions'>. "
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


def extract_title(body_html):
    match = re.search(r'<h1[^>]*>(.*?)</h1>', body_html, re.DOTALL | re.IGNORECASE)
    if match:
        return re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return "Recipe"


def wrap_columns(body_html):
    """Split at the Ingredients and Instructions h2 headings and wrap in a two-column grid."""
    ing_h2  = re.search(r'<h2[^>]*>\s*Ingredients\s*</h2>',  body_html, re.IGNORECASE)
    inst_h2 = re.search(r'<h2[^>]*>\s*Instructions\s*</h2>', body_html, re.IGNORECASE)
    if not ing_h2 or not inst_h2:
        return body_html
    before       = body_html[:ing_h2.start()]
    ingredients  = body_html[ing_h2.start():inst_h2.start()]
    instructions = body_html[inst_h2.start():]
    return (
        before +
        '<div class="recipe-cols">'
        f'<div class="col-ingredients">{ingredients}</div>'
        f'<div class="col-instructions">{instructions}</div>'
        '</div>'
    )


RECIPE_PAGE_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:         #0a0a0a;
    --surface:    #141414;
    --border:     #272727;
    --accent:     #00bfa6;
    --accent-dim: rgba(0, 191, 166, 0.1);
    --text:       #f0f0f0;
    --text-muted: #777;
    --max-w:      820px;
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.65;
    min-height: 100dvh;
  }

  /* hero image */
  .recipe-hero {
    width: 100%;
    max-height: 380px;
    overflow: hidden;
    background: var(--surface);
  }

  .recipe-hero img {
    width: 100%;
    height: 380px;
    object-fit: cover;
    display: block;
    opacity: 0.9;
  }

  /* main content container */
  .recipe-body {
    max-width: var(--max-w);
    margin: 0 auto;
    padding: 2.25rem 1.5rem 3rem;
  }

  /* title */
  h1 {
    font-size: clamp(1.75rem, 4vw, 2.5rem);
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1.1;
    color: var(--text);
    margin-bottom: 0.875rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
  }

  /* metadata */
  h1 ~ p, .meta, .meta p {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
  }

  h1 ~ p strong, .meta strong {
    color: var(--text);
    font-weight: 600;
  }

  /* section labels */
  h2 {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--accent);
    padding-bottom: 0.6rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--border);
  }

  /* two-column layout */
  .recipe-cols {
    display: grid;
    grid-template-columns: 5fr 7fr;
    gap: 3rem;
    align-items: start;
    margin-top: 1.75rem;
  }

  .col-ingredients,
  .col-instructions {
    min-width: 0;
  }

  .col-instructions h2 { margin-top: 0; }

  /* ingredients — tappable checklist */
  ul {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  ul li {
    display: flex;
    align-items: baseline;
    gap: 0.7rem;
    padding: 0.55rem 0.6rem;
    font-size: 0.92rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s, opacity 0.2s;
    user-select: none;
  }

  ul li:hover { background: var(--accent-dim); }

  ul li::before {
    content: '';
    flex-shrink: 0;
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1.5px solid #3a3a3a;
    background: transparent;
    margin-top: 0.2em;
    transition: background 0.15s, border-color 0.15s;
  }

  ul li.checked { opacity: 0.35; text-decoration: line-through; }
  ul li.checked::before { background: var(--accent); border-color: var(--accent); }

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
    padding: 1rem 1.125rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 0.92rem;
    line-height: 1.65;
    transition: border-color 0.15s;
  }

  ol li:hover { border-color: #3a3a3a; }

  ol li::before {
    content: counter(steps);
    font-size: 0.72rem;
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

  /* footer */
  .recipe-footer {
    max-width: var(--max-w);
    margin: 0 auto;
    padding: 1.25rem 1.5rem 1rem;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .scan-link {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent);
    text-decoration: none;
    opacity: 0.8;
    transition: opacity 0.15s;
  }

  .scan-link:hover { opacity: 1; }

  .copy-btn {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-muted);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.4rem 0.875rem;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s;
    white-space: nowrap;
  }

  .copy-btn:hover { color: var(--text); border-color: #444; }
  .copy-btn.copied { color: var(--accent); border-color: var(--accent); }

  /* anylist import section */
  .anylist-section {
    max-width: var(--max-w);
    margin: 0 auto;
    padding: 0 1.5rem 2.5rem;
  }

  .anylist-section summary {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-muted);
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 0;
    transition: color 0.15s;
  }

  .anylist-section summary:hover { color: var(--text); }
  .anylist-section summary::before { content: '▸'; font-size: 0.7rem; transition: transform 0.2s; }
  .anylist-section[open] summary::before { transform: rotate(90deg); }

  .anylist-steps {
    margin-top: 0.75rem;
    padding: 1rem 1.25rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .anylist-steps li {
    font-size: 0.85rem;
    color: var(--text-muted);
    line-height: 1.5;
    list-style: decimal;
    margin-left: 1.1rem;
  }

  .anylist-steps li strong { color: var(--text); }

  .anylist-download {
    display: flex;
    gap: 0.625rem;
    margin-top: 0.875rem;
    flex-wrap: wrap;
  }

  .anylist-download a {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--accent);
    text-decoration: none;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.35rem 0.75rem;
    transition: border-color 0.15s, color 0.15s;
    white-space: nowrap;
  }

  .anylist-download a:hover { border-color: var(--accent); }

  script[type="application/ld+json"] { display: none; }

  @media (max-width: 680px) {
    .recipe-hero img { height: 240px; }
    .recipe-cols {
      grid-template-columns: 1fr;
      gap: 0;
    }
    .col-instructions { margin-top: 2rem; }
    ol li { grid-template-columns: 1.75rem 1fr; gap: 0.625rem; padding: 0.875rem; }
    ol li::before { width: 1.75rem; height: 1.75rem; font-size: 0.7rem; }
    .recipe-footer { flex-wrap: wrap; }
  }
"""


def build_recipe_page(body_html, recipe_id, has_image):
    body_html = wrap_columns(body_html)
    title = extract_title(body_html)

    hero = ""
    if has_image:
        hero = f"""
  <div class="recipe-hero">
    <img src="/recipes/{recipe_id}/image" alt="{title}" loading="lazy"
         onerror="this.parentElement.style.display='none'">
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>{RECIPE_PAGE_CSS}</style>
</head>
<body>
  {hero}
  <div class="recipe-body">
    {body_html}
  </div>
  <div class="recipe-footer">
    <a href="https://rmholm88.github.io/recipe-test/recipe_uploader_app.html" class="scan-link">← Scan another</a>
    <button class="copy-btn" id="copyBtn" onclick="copyLink()">Copy link</button>
  </div>
  <details class="anylist-section">
    <summary>How to import into Anylist</summary>
    <ol class="anylist-steps">
      <li>Open this page on your phone or tablet</li>
      <li>Tap the <strong>Share</strong> button (the box with an arrow) to open the share sheet</li>
      <li>Scroll the share sheet and tap <strong>Anylist</strong></li>
      <li>Review the recipe and tap <strong>Save Recipe</strong></li>
    </ol>
    <div class="anylist-download">
      <a href="https://apps.apple.com/us/app/anylist-grocery-shopping-list/id522167641" target="_blank" rel="noopener">↓ Download for iPhone / iPad</a>
      <a href="https://play.google.com/store/apps/details?id=com.purplecover.anylist" target="_blank" rel="noopener">↓ Download for Android</a>
    </div>
  </details>
  <script>
    // Ingredient checklist
    document.querySelectorAll('ul li').forEach(li => {{
      li.addEventListener('click', () => li.classList.toggle('checked'));
    }});

    // Copy link
    function copyLink() {{
      const btn = document.getElementById('copyBtn');
      navigator.clipboard.writeText(window.location.href).then(() => {{
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {{
          btn.textContent = 'Copy link';
          btn.classList.remove('copied');
        }}, 2000);
      }});
    }}
  </script>
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
