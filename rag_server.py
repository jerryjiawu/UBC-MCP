"""Local RAG server for the Discord bot.

Indexes every .txt/.md file under src/context/ using a local sentence-transformer
embedding model (no embedding API calls -- everything here runs on this machine)
and serves semantic retrieval over a tiny HTTP API, so the bot only has to send
the most relevant chunks to Gemini for a given question instead of stuffing the
entire brief into every request. Falls back gracefully: if this server is ever
down, discord_bot.py just uses the whole brief like before.

The index is rebuilt automatically whenever a source file's mtime changes, and
embeddings are cached on disk (.rag_cache.npz) so restarts don't re-embed
unchanged files.
"""
import glob
import hashlib
import os
import re
import threading

import numpy as np
from flask import Flask, jsonify, request
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONTEXT_DIR = os.path.join(PROJECT_ROOT, "src", "context")
CACHE_PATH = os.path.join(PROJECT_ROOT, ".rag_cache.npz")

MODEL_NAME = os.getenv("RAG_MODEL", "all-MiniLM-L6-v2")
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100
TOP_K_DEFAULT = 4

_model = None
_lock = threading.Lock()
_index = {"chunks": [], "sources": [], "embeddings": None, "signature": None}


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _iter_context_files():
    patterns = ["*.txt", "*.md"]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(os.path.join(CONTEXT_DIR, "**", pattern), recursive=True))
    return sorted(set(paths))


def _chunk_text(text: str) -> list[str]:
    """Split on blank lines (paragraphs/sections) first, then hard-wrap anything
    still too long, so retrieval granularity roughly follows the document's own
    structure instead of chopping mid-sentence everywhere."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 1 <= CHUNK_SIZE:
            buf = f"{buf}\n{para}".strip()
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(para) > CHUNK_SIZE:
            for i in range(0, len(para), CHUNK_SIZE - CHUNK_OVERLAP):
                chunks.append(para[i:i + CHUNK_SIZE])
        else:
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def _file_signature() -> str:
    """Hash of every context file's path+mtime -- changes iff the corpus changed."""
    parts = []
    for path in _iter_context_files():
        try:
            parts.append(f"{path}:{os.path.getmtime(path)}")
        except OSError:
            pass
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _load_cache(signature: str) -> bool:
    if not os.path.exists(CACHE_PATH):
        return False
    try:
        data = np.load(CACHE_PATH, allow_pickle=True)
        if str(data["signature"]) != signature:
            return False
        _index["chunks"] = list(data["chunks"])
        _index["sources"] = list(data["sources"])
        _index["embeddings"] = data["embeddings"]
        _index["signature"] = signature
        return True
    except Exception:
        return False


def _save_cache():
    try:
        np.savez(
            CACHE_PATH,
            signature=_index["signature"],
            chunks=np.array(_index["chunks"], dtype=object),
            sources=np.array(_index["sources"], dtype=object),
            embeddings=_index["embeddings"],
        )
    except Exception:
        pass


def _rebuild_index():
    signature = _file_signature()
    if _load_cache(signature):
        return

    chunks, sources = [], []
    for path in _iter_context_files():
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        rel = os.path.relpath(path, PROJECT_ROOT)
        for chunk in _chunk_text(text):
            chunks.append(chunk)
            sources.append(rel)

    model = _get_model()
    embeddings = (
        model.encode(chunks, normalize_embeddings=True)
        if chunks
        else np.zeros((0, model.get_sentence_embedding_dimension()))
    )

    _index["chunks"] = chunks
    _index["sources"] = sources
    _index["embeddings"] = embeddings
    _index["signature"] = signature
    _save_cache()


def _ensure_fresh_index():
    with _lock:
        if _index["embeddings"] is None or _index["signature"] != _file_signature():
            _rebuild_index()


def query(question: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    _ensure_fresh_index()
    if not _index["chunks"]:
        return []
    model = _get_model()
    q_emb = model.encode([question], normalize_embeddings=True)[0]
    sims = np.asarray(_index["embeddings"]) @ q_emb
    top_idx = np.argsort(-sims)[:top_k]
    return [
        {"text": str(_index["chunks"][i]), "source": str(_index["sources"][i]), "score": float(sims[i])}
        for i in top_idx
    ]


app = Flask(__name__)


@app.route("/query", methods=["POST"])
def api_query():
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or "").strip()
    top_k = int(data.get("top_k", TOP_K_DEFAULT))
    if not question:
        return jsonify({"error": "missing 'question'"}), 400
    return jsonify({"results": query(question, top_k=top_k)})


@app.route("/health")
def health():
    _ensure_fresh_index()
    return jsonify({"ok": True, "chunks_indexed": len(_index["chunks"]), "model": MODEL_NAME})


if __name__ == "__main__":
    _ensure_fresh_index()  # warm the model/index at startup instead of on the first request
    port = int(os.getenv("RAG_SERVER_PORT", "5056"))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
