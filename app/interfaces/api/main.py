"""FastAPI entrypoint (placeholder)."""

from fastapi import FastAPI


app = FastAPI(title="CleverDocs")


@app.get("/health")
def health():
    return {"status": "ok"}
