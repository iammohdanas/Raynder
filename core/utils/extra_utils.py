import hashlib

def substage_document_upload_path(instance, filename):
    return (
        f"workflow/substages/"
        f"{instance.substage.stage.project.project_id}/"
        f"{instance.substage.stage.stage_code}/"
        f"{instance.substage.substage_code}/"
        f"{filename}"
    )


def generate_file_hash(file):
    sha256_hash = hashlib.sha256()
    for chunk in file.chunks():
        sha256_hash.update(chunk)
    return sha256_hash.hexdigest()