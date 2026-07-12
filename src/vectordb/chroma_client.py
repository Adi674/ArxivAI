import logging
import numpy as np
from functools import lru_cache
import boto3
from langchain_community.embeddings import BedrockEmbeddings

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MatryoshkaBedrockEmbeddings(BedrockEmbeddings):
    """
    Custom wrapper to enable Matryoshka dimensionality reduction (512 dimensions)
    for AWS Bedrock Amazon Titan Text Embeddings V2.
    """
    def _slice_and_normalize(self, vector: list[float]) -> list[float]:
        vec = np.array(vector[:512])
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results = super().embed_documents(texts)
        return [self._slice_and_normalize(r) for r in results]

    def embed_query(self, text: str) -> list[float]:
        result = super().embed_query(text)
        return self._slice_and_normalize(result)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        results = await super().aembed_documents(texts)
        return [self._slice_and_normalize(r) for r in results]

    async def aembed_query(self, text: str) -> list[float]:
        result = await super().aembed_query(text)
        return self._slice_and_normalize(result)


@lru_cache(maxsize=1)
def get_embedding_model() -> MatryoshkaBedrockEmbeddings:
    """
    Load AWS Bedrock Titan Text Embeddings V2 model (Matryoshka 512 dims).
    Cached singleton — loads once per process.
    """
    logger.info("Initializing AWS Bedrock embeddings: amazon.titan-embed-text-v2:0 (512 dims)")
    
    import os
    aws_key = settings.AWS_ACCESS_KEY_ID
    aws_secret = settings.AWS_SECRET_ACCESS_KEY
    
    if settings.AWS_API_KEY:
        logger.info("Using AWS Bedrock bearer token authentication (ABSK)")
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = settings.AWS_API_KEY
        aws_key = "dummy"
        aws_secret = "dummy"
        
    bedrock_client = boto3.client(
        service_name="bedrock-runtime",
        aws_access_key_id=aws_key,
        aws_secret_access_key=aws_secret,
        region_name=settings.AWS_DEFAULT_REGION,
    )
    
    model = MatryoshkaBedrockEmbeddings(
        client=bedrock_client,
        model_id="amazon.titan-embed-text-v2:0",
        model_kwargs={
            "dimensions": 512,
            "normalize": True
        }
    )
    logger.info("AWS Bedrock embeddings ready")
    return model