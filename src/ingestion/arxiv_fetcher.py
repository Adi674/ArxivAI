# src/ingestion/arxiv_fetcher.py
import httpx
import logging
import xml.etree.ElementTree as ET
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

ARXIV_API_BASE = "https://export.arxiv.org/api/query"

# Map our internal domain names to arXiv category codes
DOMAIN_TO_ARXIV_CATS = {
    "ML":       ["cs.LG", "stat.ML"],
    "NLP":      ["cs.CL"],
    "CV":       ["cs.CV"],
    "AI":       ["cs.AI"],
    "Biology":  ["q-bio.BM", "q-bio.GN", "q-bio.NC"],
    "Physics":  ["physics.comp-ph", "cond-mat.stat-mech"],
    "Chemistry":["physics.chem-ph", "q-bio.BM"],
    "Math":     ["math.ST", "math.OC"],
    "Theory":   ["cs.CC", "cs.DS"],
    "Systems":  ["cs.DC", "cs.OS", "cs.NI"],
    "GenAI":    ["cs.CL", "cs.AI", "cs.LG"],
}


def _parse_arxiv_entry(entry: ET.Element, ns: str) -> Optional[dict]:
    """
    Parse a single arXiv XML entry element into a paper metadata dict.

    Args:
        entry: XML Element for one paper
        ns: XML namespace string

    Returns:
        dict with id, title, authors, summary, pdf_url, categories, published
        or None if required fields are missing
    """
    try:
        arxiv_id_raw = entry.find(f"{ns}id").text.strip()
        # Extract clean ID: "http://arxiv.org/abs/2401.12345v1" → "2401.12345"
        arxiv_id = arxiv_id_raw.split("/abs/")[-1].split("v")[0]

        title = entry.find(f"{ns}title").text.strip().replace("\n", " ")
        summary = entry.find(f"{ns}summary").text.strip().replace("\n", " ")
        published = entry.find(f"{ns}published").text.strip()[:10]  # YYYY-MM-DD

        authors = []
        for author in entry.findall(f"{ns}author"):
            name_el = author.find(f"{ns}name")
            if name_el is not None:
                authors.append(name_el.text.strip())
        authors_str = ", ".join(authors[:5])  # cap at 5 for storage

        # Find PDF link
        pdf_url = None
        for link in entry.findall(f"{ns}link"):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "").replace("http://", "https://")
                if not pdf_url.endswith(".pdf"):
                    pdf_url += ".pdf"
                break

        categories = [
            cat.attrib.get("term", "")
            for cat in entry.findall("{http://arxiv.org/schemas/atom}category")
        ]

        return {
            "id": arxiv_id,
            "title": title,
            "authors": authors_str,
            "summary": summary,
            "pdf_url": pdf_url,
            "categories": categories,
            "published": published,
        }
    except Exception as e:
        logger.warning(f"Failed to parse arXiv entry: {e}")
        return None


async def fetch_arxiv_metadata(
    domain: str,
    num_papers: int = 50,
    days_back: int = 30,
) -> list[dict]:
    """
    Fetch paper metadata from arXiv API for a given domain.

    Args:
        domain: Internal domain name (e.g. "ML", "NLP")
        num_papers: Max papers to fetch
        days_back: How far back to search (approximate — arXiv API sorts by relevance)

    Returns:
        List of paper metadata dicts ready for ingestion pipeline
    """
    cats = DOMAIN_TO_ARXIV_CATS.get(domain, ["cs.LG"])
    
    if domain == "GenAI":
        # Query specifically for emerging LLM, Agentic AI, and RAG keywords in titles
        cat_query = '(cat:cs.CL OR cat:cs.AI OR cat:cs.LG) AND (ti:"large language model" OR ti:LLM OR ti:agent OR ti:"generative AI" OR ti:"retrieval-augmented generation" OR ti:RAG)'
    else:
        cat_query = " OR ".join(f"cat:{c}" for c in cats)

    params = {
        "search_query": cat_query,
        "start": 0,
        "max_results": num_papers,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    logger.info(f"Fetching {num_papers} papers for domain={domain} (cats: {cats})")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(ARXIV_API_BASE, params=params)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"arXiv API request failed: {e}")
        return []

    # Parse XML
    ns = "{http://www.w3.org/2005/Atom}"
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as e:
        logger.error(f"Failed to parse arXiv XML: {e}")
        return []

    papers = []
    for entry in root.findall(f"{ns}entry"):
        paper = _parse_arxiv_entry(entry, ns)
        if paper and paper.get("pdf_url"):
            papers.append(paper)

    logger.info(f"Parsed {len(papers)} valid papers for domain={domain}")
    return papers


async def fetch_fresh_papers(
    query: str,
    domain: str,
    k: int = 5,
) -> list[dict]:
    """
    Fetch fresh papers from arXiv matching a specific query.
    Called by the Retriever agent when local Chroma results have low relevance.

    Args:
        query: User's search query (natural language)
        domain: Domain to scope the search
        k: Number of papers to fetch

    Returns:
        List of paper metadata dicts
    """
    cats = DOMAIN_TO_ARXIV_CATS.get(domain, ["cs.LG"])
    cat_filter = " OR ".join(f"cat:{c}" for c in cats)

    # Combine query terms with category filter
    search_query = f"({cat_filter}) AND ti:{query}"

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": k,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    logger.info(f"Fresh arXiv fetch: query='{query}', domain={domain}, k={k}")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(ARXIV_API_BASE, params=params)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Fresh arXiv fetch failed: {e}")
        return []

    ns = "{http://www.w3.org/2005/Atom}"
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []

    papers = []
    for entry in root.findall(f"{ns}entry"):
        paper = _parse_arxiv_entry(entry, ns)
        if paper and paper.get("pdf_url"):
            papers.append(paper)

    return papers