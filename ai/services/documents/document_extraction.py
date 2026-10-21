import os
import fitz
import pandas as pd

class DocumentExtractionService:
    @staticmethod
    def extract(file_path):
        ext=os.path.splitext(file_path)[1].lower()

        if ext==".pdf":
            return DocumentExtractionService._extract_pdf(file_path)

        if ext in [".xls",".xlsx"]:
            return DocumentExtractionService._extract_excel(file_path)

        raise ValueError(f"Unsupported document type: {ext}")

    @staticmethod
    def _extract_pdf(file_path):
        doc=fitz.open(file_path)
        pages=[]

        for page_number,page in enumerate(doc,start=1):
            text=page.get_text("text").strip()
            if text:
                pages.append({
                    "page_number":page_number,
                    "text":text
                })

        doc.close()
        return pages

    @staticmethod
    def _extract_excel(file_path):
        sheets=pd.read_excel(file_path,sheet_name=None)

        pages=[]

        for sheet_name,df in sheets.items():
            df=df.fillna("")
            text=df.to_string(index=False)

            if text.strip():
                pages.append({
                    "page_number":None,
                    "text":f"Sheet: {sheet_name}\n{text}"
                })

        return pages