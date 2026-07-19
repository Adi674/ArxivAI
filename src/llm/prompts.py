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

Decide THREE things and respond ONLY with strict JSON:

1. search_spaces: which namespaces to search
2. fetch_arxiv_fresh: true only if query needs very recent papers not in database
3. search_tool: which search tool to use — pick ONE of: "semantic", "keyword", "hybrid"

SEARCH TOOL DECISION RULES:
- "keyword"  → query mentions a SPECIFIC author name, paper title, arXiv ID (e.g. 2301.12345),
               conference (NeurIPS, ICML, ICLR), or exact model name (GPT-4, LLaMA-2, BERT).
               Use when the user is looking for a SPECIFIC known item.

- "semantic" → query asks to EXPLAIN, DEFINE, or UNDERSTAND a concept with NO specific
               named entities. Examples: "What is attention?", "How does dropout work?",
               "Explain gradient descent". Use when intent is conceptual understanding.

- "hybrid"   → query asks to COMPARE, CONTRAST, or asks HOW something performs in a
               SPECIFIC real-world setting. Also use for multi-hop queries or when unsure.
               Examples: "How does RLHF compare to SFT?", "What are the trade-offs of X?",
               "How does SMetric balance LLM session serving?". DEFAULT when uncertain.

Respond ONLY with this exact JSON format, no extra text:
{{"search_spaces": ["public"], "fetch_arxiv_fresh": false, "search_tool": "hybrid"}}

JSON:"""


QUERY_REFORMULATE_PROMPT = """You are a search query optimizer. The original search query returned poor search results. Rewrite it for better retrieval from a vector database.

Original query: {query}
Domain: {domain}
Reason for reformulation: Low average relevance score ({score})

Task:
Write a single optimized query that uses specific academic terminology, terms, or IDs to match relevant papers.

CRITICAL INSTRUCTIONS:
1. Output ONLY the raw optimized query string itself.
2. Do NOT output any intro or conversational filler (e.g. do NOT say "Here is the query:" or "Based on the original query...").
3. Do NOT wrap the query in quotes or markdown code blocks.
4. If an arXiv ID or author name is present in the original query, make sure to keep it in the optimized query.

Optimized query:"""


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

RELEVANCE_LABEL_PROMPT = """You are an information retrieval judge.
Determine if the following academic paper chunk is highly relevant to the user query.

Relevance criteria:
- The chunk contains info that directly answers the query or part of the query.
- The chunk provides essential background theory or details required for the answer.
- Tangential or generic mentions of terms are NOT relevant.

Query: {query}

Paper: {title} by {authors}
Chunk Content:
{content}

Respond ONLY with JSON:
{{"relevant": true}} or {{"relevant": false}}

JSON:"""


RELEVANCE_JUDGE_PROMPT = """You are an information retrieval judge.
Given a user query and up to 5 retrieved paper chunks, determine which chunks are highly relevant to answering the query.

Relevance Criteria:
- A chunk is relevant if it contains information that directly answers the query, supports the answer, or provides necessary background theory.
- Generic mentions of terms or tangential info are NOT relevant.

Query: {query}

Retrieved Chunks:
{chunks}

Respond ONLY with JSON containing a list of relevant chunk indexes (0-indexed matching the list below):
{{"relevant_indexes": [0, 2]}}

JSON:"""