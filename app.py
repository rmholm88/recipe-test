from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import openai
import base64
import os
import uuid
import psycopg2
from psycopg2.extras import execute_values

app = Flask(__name__)
CORS(app, origins=["https://rmholm88.github.io"])

openai.api_key = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")


def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recipes (
                    id TEXT PRIMARY KEY,
                    html TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()


init_db()


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
                    "Return valid semantic HTML using schema.org Recipe markup. "
                    "Strictly wrap the ingredients in a <ul> tag with each item in a <li>. "
                    "Wrap the instructions in a <ol> tag with each step in a separate <li>. "
                    "Use <h1> for the recipe title and include <p> for yield/servings. "
                    "Do not use dashes, numbers, or line breaks for formatting — only proper HTML elements. "
                    "At the bottom, include a <script type='application/ld+json'> block with proper structured data. "
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

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO recipes (id, html) VALUES (%s, %s)",
                    (recipe_id, rendered_html)
                )
            conn.commit()

        print(f"✅ Recipe parsed and stored with ID: {recipe_id}")
        return jsonify({"htmlUrl": f"https://recipe-test.onrender.com/recipes/{recipe_id}"})

    except openai.OpenAIError as oe:
        print(f"❌ OpenAI API error: {oe}")
        return jsonify({"error": "Failed to process image with OpenAI"}), 502

    except Exception as e:
        print(f"❌ Unexpected server error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500


RECIPE_STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #fafaf7;
    --surface:  #ffffff;
    --border:   #e8e5df;
    --text:     #1a1a1a;
    --muted:    #6b6b6b;
    --accent:   #2a7a5c;
    --accent-dim: rgba(42, 122, 92, 0.08);
    --step-bg:  #f0f7f4;
    --num:      #2a7a5c;
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.65;
    padding: 2rem 1.25rem 4rem;
  }

  /* hide any existing inline styles the AI might add */
  body > style { display: none; }

  .recipe-wrap,
  body > div,
  body > article,
  body > main {
    max-width: 660px;
    margin: 0 auto;
  }

  h1 {
    font-size: clamp(1.6rem, 5vw, 2.2rem);
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1.15;
    color: var(--text);
    margin-bottom: 1.25rem;
    padding-bottom: 1.25rem;
    border-bottom: 2px solid var(--border);
  }

  /* metadata lines — <p> tags before the first h2 */
  h1 ~ p,
  .meta,
  .meta p {
    font-size: 0.88rem;
    color: var(--muted);
    margin-bottom: 0.3rem;
  }

  h1 ~ p strong,
  .meta strong {
    color: var(--text);
    font-weight: 600;
  }

  h2 {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 2.25rem 0 1rem;
  }

  /* ingredients */
  ul {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  ul li {
    padding: 0.55rem 0.75rem;
    font-size: 0.95rem;
    border-radius: 8px;
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    transition: background 0.15s;
  }

  ul li:hover { background: var(--accent-dim); }

  ul li::before {
    content: '';
    flex-shrink: 0;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    opacity: 0.5;
    margin-top: 0.45em;
  }

  /* instructions */
  ol {
    list-style: none;
    counter-reset: steps;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  ol li {
    counter-increment: steps;
    display: grid;
    grid-template-columns: 2rem 1fr;
    gap: 0.75rem;
    align-items: start;
    padding: 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 0.95rem;
    line-height: 1.6;
  }

  ol li::before {
    content: counter(steps);
    font-size: 0.8rem;
    font-weight: 800;
    color: var(--num);
    background: var(--step-bg);
    border-radius: 6px;
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 0.05rem;
  }

  /* strip inline styles from AI output */
  [style] { color: inherit !important; font-family: inherit !important; }

  script[type="application/ld+json"] { display: none; }

  @media (max-width: 480px) {
    body { padding: 1.25rem 1rem 3rem; }
    ol li { grid-template-columns: 1.75rem 1fr; gap: 0.6rem; padding: 0.875rem; }
    ol li::before { width: 1.75rem; height: 1.75rem; font-size: 0.75rem; }
  }

  @media print {
    body { background: white; padding: 0; }
    ol li { border: 1px solid #ccc; break-inside: avoid; }
  }
</style>
"""

def inject_styles(html):
    if '</head>' in html:
        return html.replace('</head>', RECIPE_STYLE + '</head>', 1)
    if '<body' in html:
        idx = html.index('<body')
        return html[:idx] + f'<head>{RECIPE_STYLE}</head>' + html[idx:]
    return f'<head>{RECIPE_STYLE}</head>' + html


@app.route("/recipes/<recipe_id>")
def serve_recipe(recipe_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT html FROM recipes WHERE id = %s", (recipe_id,))
            row = cur.fetchone()
    if not row:
        return "Recipe not found", 404
    return Response(inject_styles(row[0]), mimetype='text/html')

if __name__ == "__main__":
    app.run(debug=True)
