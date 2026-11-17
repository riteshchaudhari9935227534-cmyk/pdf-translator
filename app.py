import os, io, re, requests
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import fitz
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from xml.sax.saxutils import escape

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
MAX_PAGES = 150

# Configure a LibreTranslate-compatible server in your hosting environment.
# Public servers can be rate-limited or unavailable; this starter does not promise unlimited free translation.
TRANSLATE_URL = os.environ.get("LIBRETRANSLATE_URL", "https://libretranslate.com")
API_KEY = os.environ.get("LIBRETRANSLATE_API_KEY", "")

def chunks(text, limit=2500):
    result, current = [], ""
    for paragraph in text.splitlines(True):
        while len(paragraph) > limit:
            if current:
                result.append(current)
                current = ""
            result.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        if len(current) + len(paragraph) > limit:
            if current:
                result.append(current)
            current = paragraph
        else:
            current += paragraph
    if current:
        result.append(current)
    return result or [""]

def translate(text, source, target):
    if not text.strip():
        return text
    output = []
    for part in chunks(text):
        data = {"q": part, "source": source, "target": target, "format": "text"}
        if API_KEY:
            data["api_key"] = API_KEY
        response = requests.post(
            TRANSLATE_URL.rstrip("/") + "/translate",
            data=data,
            timeout=90
        )
        response.raise_for_status()
        translated = response.json().get("translatedText")
        if translated is None:
            raise RuntimeError("Translation service returned an invalid response.")
        output.append(translated)
    return "".join(output)

def get_font():
    candidates = [
        os.environ.get("PDF_FONT_PATH", ""),
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("Devanagari", path))
                return "Devanagari"
            except Exception:
                pass
    return "Helvetica"

def create_pdf(page_texts, direction):
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18*mm,
                            leftMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    font = get_font()
    body = ParagraphStyle("TranslatedBody", parent=styles["BodyText"],
                          fontName=font, fontSize=9, leading=13, spaceAfter=6)
    title = ParagraphStyle("TranslatedTitle", parent=styles["Title"], fontName=font)
    story = [Paragraph(escape("Translated PDF: " + direction), title), Spacer(1, 10)]
    for number, text in enumerate(page_texts, start=1):
        story.append(Paragraph(f"Page {number}", styles["Heading3"]))
        for line in text.splitlines():
            if line.strip():
                story.append(Paragraph(escape(line), body))
            else:
                story.append(Spacer(1, 4))
        if number < len(page_texts):
            story.append(PageBreak())
    doc.build(story)
    output.seek(0)
    return output

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")
    upload = request.files.get("pdf")
    source = request.form.get("source", "en")
    target = request.form.get("target", "hi")
    if not upload or not upload.filename.lower().endswith(".pdf"):
        flash("Please choose a PDF file.")
        return redirect(url_for("index"))
    if source not in ("en", "hi") or target not in ("en", "hi") or source == target:
        flash("Please choose two different languages.")
        return redirect(url_for("index"))
    try:
        raw = upload.read()
        pdf = fitz.open(stream=raw, filetype="pdf")
        if pdf.page_count > MAX_PAGES:
            raise ValueError(f"PDF is {pdf.page_count} pages. Maximum supported is {MAX_PAGES} pages.")
        translated_pages = []
        for page in pdf:
            text = page.get_text("text")
            if not text.strip():
                translated_pages.append("[No selectable text detected. Scanned pages need OCR.]")
            else:
                translated_pages.append(translate(text, source, target))
        pdf.close()
        result = create_pdf(translated_pages, f"{source.upper()} to {target.upper()}")
        return send_file(result, mimetype="application/pdf", as_attachment=True,
                         download_name="translated.pdf")
    except Exception as exc:
        flash("Translation failed: " + str(exc))
        return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
