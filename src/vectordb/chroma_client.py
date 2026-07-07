import logging
from functools import lru_cache
import chromadb
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    Load HuggingFace all-MiniLM-L6-v2 embedding model.
    Cached singleton — loads once per process.
    """
    logger.info("Loading embedding model: all-MiniLM-L6-v2")
    model = HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    logger.info("Embedding model loaded")
    return model


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.Client:
    """
    Create persistent Chroma client.
    Cached singleton.
    """
    client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
    logger.info(f"Chroma client ready at: {settings.CHROMA_PATH}")
    return client


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    """
    Return LangChain Chroma vectorstore with embedding model attached.
    Cached singleton.
    """
    client = get_chroma_client()
    embeddings = get_embedding_model()

    vectorstore = Chroma(
        client=client,
        collection_name="arxivai_papers",
        embedding_function=embeddings,
    )
    logger.info("Chroma vectorstore ready")
    return vectorstore