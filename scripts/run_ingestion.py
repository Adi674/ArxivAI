# scripts/run_ingestion.py
"""
CLI script to bulk-ingest arXiv papers into Chroma.

Usage:
    python scripts/run_ingestion.py --domain ML --num 50
    python scripts/run_ingestion.py --domain NLP --domain CV --num 30
    python scripts/run_ingestion.py --all --num 20   # all domains
"""

import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime

# Add project root to path so src imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_settings
from src.ingestion.arxiv_fetcher import fetch_arxiv_metadata, DOMAIN_TO_ARXIV_CATS
from src.ingestion.pipeline import ingest_paper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingestion")

ALL_DOMAINS = list(DOMAIN_TO_ARXIV_CATS.keys())


async def ingest_domain(domain: str, num_papers: int, dry_run: bool = False) -> dict:
    """
    Fetch and ingest papers for a single domain.

    Args:
        domain: Domain name (e.g. "ML", "NLP")
        num_papers: Max papers to ingest
        dry_run: If True, fetch metadata only, skip Chroma storage

    Returns:
        Summary dict with counts
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting ingestion: domain={domain}, num={num_papers}")

    papers = await fetch_arxiv_metadata(domain=domain, num_papers=num_papers)

    if not papers:
        logger.warning(f"No papers fetched for domain={domain}")
        return {"domain": domain, "fetched": 0, "ingested": 0, "failed": 0}

    logger.info(f"Fetched {len(papers)} papers for {domain}")

    if dry_run:
        for p in papers[:3]:
            logger.info(f"  [{p['id']}] {p['title'][:80]}")
        return {"domain": domain, "fetched": len(papers), "ingested": 0, "failed": 0}

    ingested = 0
    failed = 0

    for i, paper in enumerate(papers):
        try:
            metadata = {
                "title": paper["title"],
                "authors": paper["authors"],
                "domain": domain,
                "source": "arxiv",
                "user_id": "public",
                "visibility": "public",
                "collaborators": [],
                "collaboration_id": "",
                "upload_date": paper["published"],
                "citation_count": 0,
            }

            chunk_ids = await ingest_paper(
                paper_id=paper["id"],
                pdf_url=paper["pdf_url"],
                pdf_bytes=None,
                metadata=metadata,
            )

            if chunk_ids:
                ingested += 1
                logger.info(f"  [{i+1}/{len(papers)}] ✅ {paper['id']} — {len(chunk_ids)} chunks")
            else:
                failed += 1
                logger.warning(f"  [{i+1}/{len(papers)}] ❌ {paper['id']} — no chunks (PDF extraction failed)")

        except Exception as e:
            failed += 1
            logger.error(f"  [{i+1}/{len(papers)}] ❌ {paper['id']} — error: {e}")

    summary = {
        "domain": domain,
        "fetched": len(papers),
        "ingested": ingested,
        "failed": failed,
    }
    logger.info(f"Domain {domain} complete: {ingested} ingested, {failed} failed")
    return summary


async def main():
    parser = argparse.ArgumentParser(description="Ingest arXiv papers into Chroma")
    parser.add_argument("--domain", action="append", dest="domains",
                        help="Domain to ingest (can repeat). E.g. --domain ML --domain NLP")
    parser.add_argument("--all", action="store_true",
                        help="Ingest all domains")
    parser.add_argument("--num", type=int, default=50,
                        help="Number of papers per domain (default: 50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch metadata only, skip Chroma storage")
    args = parser.parse_args()

    if args.all:
        domains = ALL_DOMAINS
    elif args.domains:
        domains = args.domains
    else:
        parser.error("Specify --domain <name> or --all")

    # Validate domains
    invalid = [d for d in domains if d not in ALL_DOMAINS]
    if invalid:
        logger.error(f"Unknown domains: {invalid}. Valid: {ALL_DOMAINS}")
        sys.exit(1)

    settings = get_settings()
    logger.info(f"Domains to ingest: {domains}")
    logger.info(f"Papers per domain: {args.num}")

    start = datetime.utcnow()
    results = []

    for domain in domains:
        result = await ingest_domain(domain, args.num, dry_run=args.dry_run)
        results.append(result)

    elapsed = (datetime.utcnow() - start).total_seconds()

    print("\n" + "="*60)
    print("INGESTION SUMMARY")
    print("="*60)
    total_fetched = total_ingested = total_failed = 0
    for r in results:
        print(f"  {r['domain']:12} fetched={r['fetched']:3}  ingested={r['ingested']:3}  failed={r['failed']:3}")
        total_fetched  += r["fetched"]
        total_ingested += r["ingested"]
        total_failed   += r["failed"]
    print("-"*60)
    print(f"  {'TOTAL':12} fetched={total_fetched:3}  ingested={total_ingested:3}  failed={total_failed:3}")
    print(f"\nTime elapsed: {elapsed:.1f}s")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())