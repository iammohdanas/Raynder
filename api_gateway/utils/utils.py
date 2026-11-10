import os
from django.utils.text import get_valid_filename


def tender_document_upload_path(instance, filename):
    filename = get_valid_filename(filename)

    return os.path.join(
        "tenders",
        str(instance.tender.id),
        filename,
    )