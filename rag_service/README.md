# RAG Service

Standalone local FastAPI service. Handle document intelligence. Power `@file` terminal attachment feature. 

## Architecture

Terminal send file path + question.
Service validate, extract, chunk, embed, retrieve, rerank, summarize.
Service return prompt-ready evidence pack. 

Fail closed if unsupported/unsafe. No final answer generation here. Evidence only.

## Supported Files

* **Code/Text**: `.py`, `.js`, `.ts`, `.tsx`, `.md`, `.txt`, `.json`, `.yaml`, `.csv`, `.log`
* **Documents**: `.pdf` (text extractable only), `.docx`
* **Spreadsheets**: `.xlsx`, `.csv` (table-aware, no query engine)

Scanned PDF fail. Wait for OCR future version.

## Storage & Models

* **Database**: SQLite. Store file hash, chunk, text, source location, metadata.
* **Vector Store**: FAISS. Store dense chunk vectors.
* **Embeddings**: Local BGE-M3 or BGE-Large. Primary dense + sparse fallback.
* **Reranker**: Local BGE-reranker-base.

## Cache

Cache by file hash. Match hash + extractor version + model version → bypass extraction/embedding.

## Commands

Test setup + dependencies. Run doctor:

```bash
python -m rag_service doctor
```

Start service manual:

```bash
python -m rag_service
```

## Debug
Enable `rag_debug` in config. Save JSON trace files. JSON track extraction, chunks, retrieval candidates, scores, timings.