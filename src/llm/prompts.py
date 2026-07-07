DOMAIN_CLASSIFY_PROMPT = """You are a research domain classifier. Classify the following query into one or more research domains.

Available domains: ML, NLP, CV, AI, Biology, Physics, Chemistry, Math, Theory, Systems

Query: {query}

Respond ONLY with JSON in this exact format:
{{"primary_domain": "ML", "secondary_domains": ["NLP"], "confidence": 0.92}}

JSON:"""


QUERY_ANALYZE_PROMPT = """Analyze this research query and identify its properties.

Query: {query}
Domain: {domain}

Determine:
1. query_type: "single_hop" (one clear question) or "multi_hop" (multiple sub-questions needed)
2. needs_personal_papers: true if user mentions "my papers", "my work", "I wrote"
3. needs_recent: true if user mentions "recent", "latest", "2024", "new"
4. sub_queries: if multi_hop, list the individual sub-questions

Respond ONLY with JSON:
{{"query_type": "single_hop", "needs_personal_papers": false, "needs_recent": false, "sub_queries": []}}

JSON:"""


SEARCH_STRATEGY_PROMPT = """You are deciding the retrieval strategy for a research query.

Query: {query}
Domain: {domain}
Query Type: {query_type}
Needs Recent Papers: {needs_recent}

Decide:
1. search_spaces: which namespaces to search (e.g. ["public", "user_private"])
2. fetch_arxiv_fresh: true only if query needs very recent papers not in database

Respond ONLY with JSON:
{{"search_spaces": ["public", "user_private"], "fetch_arxiv_fresh": false}}

JSON:"""


QUERY_REFORMULATE_PROMPT = """The original query returned poor search results. Rewrite it for better retrieval from a vector database of academic papers.

Original query: {query}
Domain: {domain}
Reason for reformulation: Low average relevance score ({score})

Write a single improved query that is more specific, uses academic terminology, and will match relevant papers better.

Improved query:"""


EXTRACT_FINDINGS_PROMPT = """You are a research analyst. Extract the key findings from the following paper excerpt.

Paper: {title} by {authors}
Domain: {domain}

Excerpt:
{content}

List the 3-5 most important findings as concise bullet points. Be specific and factual.

Findings:"""


CONTRADICTION_DETECT_PROMPT = """Compare these two research excerpts and identify any contradictions or conflicting claims.

Paper A: {title_a}
Excerpt A: {content_a}

Paper B: {title_b}
Excerpt B: {content_b}

If there is a clear contradiction, describe it. If no contradiction exists, say "No contradiction found."

Analysis:"""


CITATION_GRAPH_PROMPT = """For each claim in this answer draft, identify which paper supports it.

Answer draft:
{draft}

Available papers:
{papers}

Respond ONLY with JSON mapping claim fragments to paper IDs:
{{"claim fragment": "paper_id", ...}}

JSON:"""


SYNTHESIS_PROMPT = """You are a research assistant answering a question based on retrieved academic papers.

Question: {query}
Domain: {domain}

Retrieved paper findings:
{findings}

Contradictions found:
{contradictions}

Knowledge gaps:
{knowledge_gaps}

Write a comprehensive, well-structured answer that:
1. Directly answers the question
2. Cites papers inline as [Author, Year] or [Paper Title]
3. Acknowledges contradictions if any
4. Notes what is still unknown or uncertain
5. Stays grounded in the retrieved papers

Answer:"""


SYNTHESIS_REFINE_PROMPT = """Your previous answer had quality issues. Improve it based on the feedback.

Original question: {query}
Previous answer: {draft}

Evaluator feedback:
{feedback}

Write an improved answer that addresses the specific issues mentioned:

Improved answer:"""


HALLUCINATION_CHECK_PROMPT = """Check if this answer contains claims not supported by the provided papers.

Answer:
{answer}

Source papers:
{papers}

For each factual claim in the answer, verify it appears in the source papers.
If you find claims NOT in the source papers, list them.

Respond ONLY with JSON:
{{"hallucination_detected": false, "unsupported_claims": []}}

JSON:"""


COMPLETENESS_CHECK_PROMPT = """Evaluate if this answer fully addresses the original question.

Question: {query}
Answer: {answer}

Score the answer on these dimensions (0.0 to 1.0):
- faithfulness: Is it grounded in the papers?
- completeness: Does it answer all parts of the question?
- relevance: Is it relevant to what was asked?
- citation_accuracy: Are citations correct?

Respond ONLY with JSON:
{{"faithfulness": 0.9, "completeness": 0.8, "relevance": 0.9, "citation_accuracy": 0.85, "overall": 0.86, "feedback": "Missing discussion of X"}}

JSON:"""