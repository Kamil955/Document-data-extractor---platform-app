# Content types the application accepts. They live in `core` so that both the API layer
# (validation on upload) and the parsing layer (choosing a parser) can import them
# without depending on each other.
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
