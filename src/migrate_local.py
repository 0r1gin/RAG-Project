from pathlib import Path

import documents

for path in sorted(Path("data").iterdir()):
    if path.suffix.lower() in documents.ALLOWED_EXTENSIONS:
        print(documents.add_document(path.name, path.read_bytes()))