import os

def tender_document_upload_path(instance, filename):
    return os.path.join(
        "tenders",
        str(instance.tender.source_tender_id),
        filename,
    )