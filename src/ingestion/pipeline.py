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
            response = await client.get(pdf_url, follow_redirects=True)
            response.raise_for_status()
            logger.info(f"Downloaded PDF: {pdf_url} ({len(response.content)} bytes)")
            return response.content
    except Exception as e:
        logger.error(f"Failed to download PDF from {pdf_url}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# CHUNKING
# ─────────────────────────────────────────────────────────────

def sanitize_metadata(metadata: dict) -> dict:
    """
    Ensure all metadata values are str, int, float, or bool for Chroma compatibility.
    Converts lists/dicts to strings.
    """
    sanitized = {}
    for k, v in metadata.items():
        if isinstance(v, (str, int, float, bool)):
            sanitized[k] = v
        elif isinstance(v, list):
            if all(isinstance(x, str) for x in v):
                sanitized[k] = ", ".join(v)
            else:
                import json
                sanitized[k] = json.dumps(v)
        elif v is None:
            sanitized[k] = ""
        else:
            import json
            sanitized[k] = json.dumps(v)
    return sanitized


def chunk_text(
    text: str,
    paper_id: str,
    metadata: dict,
    chunk_size: int = 1500,
    overlap: int = 150,
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
    sanitized_meta = sanitize_metadata(metadata)

    for i, chunk in enumerate(chunks):
        doc = Document(
            page_content=chunk,
            metadata={
                "paper_id": paper_id,
                "chunk_index": i,
                **sanitized_meta,
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
    pdf_url: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    metadata: Optional[dict] = None,
    db: Optional[any] = None,
) -> list[str]:
    """
    Ingest a single paper: download, extract, chunk, embed, and store in Supabase pgvector.

    Args:
        paper_id: Unique paper identifier
        pdf_url: URL to download PDF from (if no bytes provided)
        pdf_bytes: Raw PDF bytes (if already downloaded)
        metadata: Dict with title, authors, domain, source, visibility, user_id etc.
        db: Async database session

    Returns:
        List of generated chunk IDs.
    """
    import uuid
    from sqlalchemy import select
    from src.models import Paper, PaperChunk
    from src.vectordb.chroma_client import get_embedding_model

    if db is None:
        from src.database import get_async_session_maker
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            return await ingest_paper(
                paper_id=paper_id,
                pdf_url=pdf_url,
                pdf_bytes=pdf_bytes,
                metadata=metadata,
                db=session
            )

    # Skip if paper is already ingested to prevent duplicate processing
    try:
        stmt = select(PaperChunk.id).where(PaperChunk.paper_id == paper_id).limit(1)
        res = await db.execute(stmt)
        if res.scalar():
            logger.info(f"Paper {paper_id} is already in Supabase. Skipping ingestion.")
            stmt_all = select(PaperChunk.id).where(PaperChunk.paper_id == paper_id)
            res_all = await db.execute(stmt_all)
            return [str(cid) for cid in res_all.scalars()]
    except Exception as e:
        logger.warning(f"Could not check existing chunks: {e}")

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

    # Clean text to remove PostgreSQL invalid byte sequences (null characters and UTF-16 surrogates)
    text = text.replace("\x00", "").replace("\u0000", "")
    text = "".join(c for c in text if not (0xD800 <= ord(c) <= 0xDFFF))

    # Step 3: Chunk
    documents = chunk_text(text=text, paper_id=paper_id, metadata=metadata)
    if not documents:
        return []

    # Step 4: Embed and store in Supabase pgvector
    try:
        embeddings_model = get_embedding_model()

        texts = [doc.page_content for doc in documents]
        embeddings = await embeddings_model.aembed_documents(texts)

        # Check if parent Paper record exists
        stmt_paper = select(Paper).where(Paper.id == paper_id)
        res_paper = await db.execute(stmt_paper)
        paper_record = res_paper.scalar_one_or_none()

        if not paper_record:
            user_uuid = None
            if metadata.get("user_id") and metadata.get("user_id") != "public":
                user_uuid = uuid.UUID(str(metadata.get("user_id")))
                
            paper_record = Paper(
                id=paper_id,
                user_id=user_uuid,
                title=metadata.get("title", "Unknown Title"),
                authors=metadata.get("authors", "Unknown Authors"),
                domain=metadata.get("domain", "ML"),
                source=metadata.get("source", "arxiv"),
                visibility=metadata.get("visibility", "public"),
                pdf_url=pdf_url or metadata.get("pdf_url")
            )
            db.add(paper_record)
            await db.flush()

        chunk_records = []
        chunk_ids = []

        for i, (text_content, emb) in enumerate(zip(texts, embeddings)):
            chunk_uuid = uuid.uuid4()
            chunk_ids.append(str(chunk_uuid))

            user_id_str = None
            if metadata.get("user_id") and metadata.get("user_id") != "public":
                user_id_str = str(metadata.get("user_id"))

            chunk_records.append(
                PaperChunk(
                    id=chunk_uuid,
                    paper_id=paper_id,
                    content=text_content,
                    chunk_index=i,
                    embedding=emb,
                    user_id=user_id_str,
                    visibility=metadata.get("visibility", "public"),
                    domain=metadata.get("domain", "ML"),
                    collaboration_id=str(metadata.get("collaboration_id")) if metadata.get("collaboration_id") else None
                )
            )

        db.add_all(chunk_records)
        paper_record.chroma_ids = chunk_ids
        await db.commit()

        logger.info(f"Stored {len(chunk_ids)} chunks in Supabase pgvector for paper {paper_id}")
        return chunk_ids

    except Exception as e:
        logger.error(f"Supabase pgvector storage failed for paper {paper_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []