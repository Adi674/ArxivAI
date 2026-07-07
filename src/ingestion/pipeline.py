import io
import uuid
import logging
import hashlib
from typing import Optional
import httpx
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# PDF EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_text_from_bytes(pdf_bytes: bytes) -> Optional[str]:
    """
    Extract raw text from PDF bytes using PyPDF2.
    Returns text string or None if extraction fails.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        full_text = "\n\n".join(pages)
        logger.info(f"Extracted {len(full_text)} characters from PDF ({len(reader.pages)} pages)")
        return full_text if full_text.strip() else None
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return None


async def download_pdf(pdf_url: str) -> Optional[bytes]:
    """
    Download PDF from URL. Returns bytes or None.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            logger.info(f"Downloaded PDF: {pdf_url} ({len(response.content)} bytes)")
            return response.content
    except Exception as e:
        logger.error(f"Failed to download PDF from {pdf_url}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# CHUNKING
# ─────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    paper_id: str,
    metadata: dict,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[Document]:
    """
    Split text into chunks using LangChain RecursiveCharacterTextSplitter.
    Attaches paper metadata to every chunk.
    Returns list of LangChain Document objects.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = splitter.split_text(text)
    documents = []

    for i, chunk in enumerate(chunks):
        doc = Document(
            page_content=chunk,
            metadata={
                "paper_id": paper_id,
                "chunk_index": i,
                **metadata,
            }
        )
        documents.append(doc)

    logger.info(f"Created {len(documents)} chunks for paper {paper_id}")
    return documents


# ─────────────────────────────────────────────────────────────
# FULL INGESTION PIPELINE
# ─────────────────────────────────────────────────────────────

async def ingest_paper(
    paper_id: str,
    pdf_url: Optional[str],
    pdf_bytes: Optional[bytes],
    metadata: dict,
) -> list[str]:
    """
    Full pipeline: download (if needed) → extract → chunk → embed → store in Chroma.

    Args:
        paper_id: Unique paper identifier
        pdf_url: URL to download PDF from (if no bytes provided)
        pdf_bytes: Raw PDF bytes (if already downloaded)
        metadata: Dict with title, authors, domain, source, visibility, user_id etc.

    Returns:
        List of Chroma chunk IDs (store in papers.chroma_ids for future deletion).
    """
    from src.vectordb.chroma_client import get_vectorstore

    # Step 1: Get PDF bytes
    if pdf_bytes is None and pdf_url:
        pdf_bytes = await download_pdf(pdf_url)

    if not pdf_bytes:
        logger.error(f"No PDF content for paper {paper_id}")
        return []

    # Step 2: Extract text
    text = extract_text_from_bytes(pdf_bytes)
    if not text:
        logger.error(f"Could not extract text from paper {paper_id}")
        return []

    # Step 3: Chunk
    documents = chunk_text(text=text, paper_id=paper_id, metadata=metadata)
    if not documents:
        return []

    # Step 4: Embed and store in Chroma
    try:
        vectorstore = get_vectorstore()

        # Generate deterministic chunk IDs
        chunk_ids = [
            f"{paper_id}_chunk_{i}"
            for i in range(len(documents))
        ]

        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]

        vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=chunk_ids)

        logger.info(f"Stored {len(chunk_ids)} chunks in Chroma for paper {paper_id}")
        return chunk_ids

    except Exception as e:
        logger.error(f"Chroma storage failed for paper {paper_id}: {e}")
        return []