# ruff: noqa: E501
"""Hand-labelled judge probes, dev documents only. Labels are the assistant's, not a human's.

Each probe is (id, category, question id for evidence, question text or None, answer text).
Evidence is always the top-5 retrieved for the evidence question.
"""

CLEAN = [
    ("tesla-a2", "Tesla's total liabilities at the end of 2024 were $48,390 million [E2]."),
    (
        "tesla-a5",
        "As of January 22, 2025, there were 9,512 holders of record of Tesla's common stock [E3].",
    ),
    ("ragas-a1", "50 Wikipedia pages were selected to construct the WikiEval dataset [E1]."),
    (
        "tesla_10k-gen-009",
        "For the year ended December 31, 2024, 1 million weighted average shares were added to the basic count due to convertible senior notes [E1].",
    ),
    (
        "ragas-gen-004",
        "BERTScore and MoverScore use contextualised embeddings, produced by a pre-trained BERT model, to compare the similarity between the generated answer and the reference answers [E1].",
    ),
    (
        "ragas-gen-009",
        "For the few pages without any back-links, the researchers used ChatGPT to complete the given context [E2].",
    ),
    (
        "nist_ai_rmf-gen-016",
        "The process of converting complex human behaviors into mathematical models can hinder AI risk management efforts because it may come at the cost of removing necessary context. This loss of context, in turn, makes it difficult to understand individual and societal impacts that are key to AI risk management efforts [E5].",
    ),
    (
        "nist_ai_rmf-gen-012",
        "Internal experts who did not serve as front-line developers for the system and/or independent assessors should be involved in regular assessments and updates [E2].",
    ),
    (
        "tesla_10k-gen-006",
        "Warranty expense is recorded as a component of Cost of revenues in the consolidated statements of operations [E1][E2].",
    ),
    (
        "tesla-a4",
        "Automotive sales revenue decreased $6.03 billion, or 8%, in the year ended December 31, 2024 as compared to the year ended December 31, 2023 [E3].",
    ),
    (
        "ragas-gen-003",
        "For models that do not provide access to token probabilities, the SelfCheckGPT method addresses the problem by sampling multiple answers [E1]. Factual answers are more stable: different samples will tend to be semantically similar, whereas this is less likely for hallucinated answers [E1].",
    ),
]

# Planted errors. The evidence does not support at least one claim.
UNSUPPORTED = [
    (
        "number",
        "tesla-a2",
        "Tesla's total liabilities at the end of 2024 were $58,390 million [E2].",
    ),
    (
        "number",
        "tesla-a5",
        "As of January 22, 2025, there were 12,512 holders of record of Tesla's common stock [E3].",
    ),
    (
        "number",
        "ragas-a1",
        "150 Wikipedia pages were selected to construct the WikiEval dataset [E1].",
    ),
    (
        "number",
        "tesla_10k-gen-009",
        "For the year ended December 31, 2024, 3 million weighted average shares were added to the basic count due to convertible senior notes [E1].",
    ),
    (
        "number",
        "tesla-a4",
        "Automotive sales revenue decreased $7.03 billion, or 11%, in the year ended December 31, 2024 as compared to the year ended December 31, 2023 [E3].",
    ),
    (
        "contradiction",
        "tesla_10k-gen-006",
        "Warranty expense is recorded as a component of Operating expenses in the consolidated statements of operations [E1][E2].",
    ),
    (
        "contradiction",
        "ragas-gen-004",
        "BERTScore and MoverScore use contextualised embeddings, produced by a pre-trained GPT model, to compare the similarity between the generated answer and the question [E1].",
    ),
    (
        "contradiction",
        "ragas-gen-009",
        "For the few pages without any back-links, the researchers asked Wikipedia editors to complete the given context [E2].",
    ),
    (
        "contradiction",
        "nist_ai_rmf-gen-012",
        "The front-line developers of the system should lead regular assessments and updates, and independent assessors should not be involved [E2].",
    ),
    (
        "contradiction",
        "nist_ai_rmf-gen-016",
        "Representing human behaviors with mathematical models preserves necessary context, which makes individual and societal impacts easier to understand [E5].",
    ),
    (
        "fabrication",
        "tesla-a5",
        "As of January 22, 2025, there were 9,512 holders of record of Tesla's common stock [E3]. This was up 12% from the prior year [E3].",
    ),
    (
        "fabrication",
        "ragas-gen-003",
        "The SelfCheckGPT method samples multiple answers [E1]. It was developed at Stanford University and reaches 94% accuracy [E1].",
    ),
    (
        "fabrication",
        "nist_ai_rmf-gen-012",
        "Independent assessors should be involved in regular assessments [E2]. NIST requires these assessments to take place every six months [E2].",
    ),
    (
        "fabrication",
        "tesla_10k-gen-006",
        "Warranty expense is recorded as a component of Cost of revenues [E1]. SEC rules cap it at 3% of revenues [E2].",
    ),
    (
        "real_misattribution",
        "nist_ai_rmf-gen-015",
        "Formal or quasi-formal norms to help manage AI risks may be provided by organizations, industries, communities, and policy makers [E3]. Additionally, sectors or industries may have established definitions of harm or requirements for documentation, reporting, and disclosure [E3].",
    ),
    (
        "real_lost_table_title",
        "tesla-a1",
        "Tesla spent $832 million on research and development in 2024 [E3].",
    ),
    (
        "real_lost_table_title",
        "tesla-a3",
        "Tesla held $49 million in cash and cash equivalents at year end 2024 [E1].",
    ),
]

# True to the evidence, but not what was asked. (question id for text, id for evidence, answer)
OFF_TOPIC = [
    (
        "subtle",
        "tesla-a2",
        "tesla-a2",
        "Tesla's total assets at the end of 2024 were $122,070 million [E2].",
    ),
    (
        "subtle",
        "tesla-a4",
        "tesla-a4",
        "Cost of automotive sales revenue decreased $3.25 billion, or 5%, in 2024 compared with 2023 [E1].",
    ),
    (
        "obvious",
        "tesla-a5",
        "tesla_10k-gen-006",
        "Warranty expense is recorded as a component of Cost of revenues in the consolidated statements of operations [E1][E2].",
    ),
    (
        "obvious",
        "ragas-a1",
        "ragas-gen-003",
        "The SelfCheckGPT method addresses the problem by sampling multiple answers [E1].",
    ),
    (
        "obvious",
        "nist_ai_rmf-gen-012",
        "nist_ai_rmf-gen-016",
        "Representing complex human phenomena with mathematical models can come at the cost of removing necessary context [E5].",
    ),
    (
        "obvious",
        "ragas-gen-009",
        "ragas-gen-004",
        "BERTScore and MoverScore use contextualised embeddings to compare the generated answer and the reference answers [E1].",
    ),
]

# The assistant's reading of the 28 real `answered` results.
REAL_WRONG = {"tesla-a1", "tesla-a3", "nist_ai_rmf-gen-015"}
