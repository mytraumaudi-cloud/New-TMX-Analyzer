from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import List
import xml.etree.ElementTree as ET
import re
import io
import csv

app = FastAPI(title="TMX Analyzer API")

# Simple word count function
def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))

@app.get("/")
def root():
    return {"message": "TMX Analyzer is running"}

@app.post("/analyze")
async def analyze_tmx(
    files: List[UploadFile] = File(...),  # Accept multiple files
    download_csv: bool = Form(False)       # Use Form for Swagger UI toggle
):
    results = []

    for file in files:
        try:
            context = ET.iterparse(file.file, events=("start", "end"))

            source_lang = None
            languages = set()
            tu_count = 0
            word_counts_by_lang = {}

            for event, elem in context:
                if event == "start" and elem.tag == "header":
                    source_lang = elem.attrib.get("srclang")
                    if source_lang:
                        languages.add(source_lang)

                if event == "end" and elem.tag == "tu":
                    tu_count += 1
                    for tuv in elem.findall("tuv"):
                        lang = tuv.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
                        seg = tuv.find("seg")
                        if seg is None or not seg.text:
                            continue
                        word_count = count_words(seg.text)
                        if lang:
                            languages.add(lang)
                            word_counts_by_lang[lang] = word_counts_by_lang.get(lang, 0) + word_count
                    elem.clear()

            source_word_count = word_counts_by_lang.get(source_lang, 0)
            target_langs = [lang for lang in word_counts_by_lang if lang != source_lang]

            results.append({
                "file_name": file.filename,
                "source_language": source_lang,
                "target_languages": target_langs,
                "translation_unit_count": tu_count,
                "word_counts_by_language": word_counts_by_lang,
                "source_word_count": source_word_count,
                "total_word_count": sum(word_counts_by_lang.values())
            })

        except Exception as e:
            results.append({
                "file_name": file.filename,
                "error": str(e)
            })

    # CSV export
    if download_csv:
        output = io.StringIO()

        # Collect all languages across files
        all_langs = set()
        for r in results:
            if "word_counts_by_language" in r:
                all_langs.update(r["word_counts_by_language"].keys())

        fieldnames = [
            "file_name",
            "source_language",
            "translation_unit_count",
            "source_word_count",
            "total_word_count"
        ] + sorted(all_langs)

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            row = {
                "file_name": r.get("file_name"),
                "source_language": r.get("source_language"),
                "translation_unit_count": r.get("translation_unit_count"),
                "source_word_count": r.get("source_word_count"),
                "total_word_count": r.get("total_word_count")
            }
            for lang in all_langs:
                row[lang] = r.get("word_counts_by_language", {}).get(lang, 0)
            writer.writerow(row)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=tmx_analysis.csv"}
        )

    return {"files_analyzed": results}