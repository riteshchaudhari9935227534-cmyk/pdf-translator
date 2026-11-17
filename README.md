
import os
import io
import requests
import fitz
from flask import Flask, render_template, request, send_file, flash, redirect
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "pdf-translator-secret"

MAX_PAGES = 150
TRANSLATE_URL = os.environ.get(
    "LIBRETRANSLATE_URL",
    "https://libretranslate.com"
)

def translate_text(text, source, target):
    response = requests.post(
        TRANSLATE_URL.rstrip("/") + "/translate",
        data={
            "q": text,
            "source": source,
            "target": target,
            "format": "text"
        },
        timeout=90
    )
    response.raise_for_status()
    return response.json()["translatedText"]

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        return render_template("index.html")

    uploaded = request.files.get("pdf")
    source = request.form.get("source")
    target = request.form.get("target")

    if not uploaded or not uploaded.filename.lower().endswith(".pdf"):
        return "Please upload a PDF file."

    if source not in ("en", "hi") or target not in ("en", "hi") or source == target:
        return "Choose two different languages."

    try:
        document = fitz.open(
            stream=uploaded.read(),
            filetype="pdf"
        )

        if document.page_count > MAX_PAGES:
            return "Maximum 150 pages allowed."

        translated_pages = []

        for page in document:
            text = page.get_text("text")
            if text.strip():
                translated_pages.append(
                    translate_text(text, source, target)
                )
            else:
                translated_pages.append(
                    "[No selectable text found on this page]"
                )

        document.close()

        output = io.BytesIO()
        pdf = canvas.Canvas(output)

        for page_text in translated_pages:
            y = 800
            for line in page_text.splitlines():
                pdf.drawString(40, y, line[:100])
                y -= 18
                if y < 40:
                    pdf.showPage()
                    y = 800
            pdf.showPage()

        pdf.save()
        output.seek(0)

        return send_file(
            output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="translated.pdf"
        )

    except Exception as error:
        return "Translation error: " + str(error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
