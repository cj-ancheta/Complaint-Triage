# Literature search protocol

Status: publication primary-source search complete, including prediction
reporting, target-trial design, and prospective human-AI evaluation

## Inclusion rules

- Prefer original peer-reviewed papers, official CFPB publications, standards,
  and official technical documentation.
- Include foundational older work when it defines a method used here.
- Include recent work only when it directly changes the interpretation or known
  limitation of the method.
- Record DOI/arXiv/official URL, venue, year, exact supported claim, and the
  section where the citation will appear.
- Do not cite a source merely because it uses the same dataset or model family.

## Search questions

1. What has prior work established about classification of consumer financial
   complaint narratives, and what evaluation designs did it use?
2. What evidence supports TF-IDF/logistic regression as a strong text baseline?
3. What are MiniLM's stated compression goals and limitations?
4. What does the original temperature-scaling literature actually establish?
5. Which proper scoring rules and calibration-error caveats are relevant to
   multiclass probability assessment?
6. How are selective risk and coverage defined, and what changes under class
   imbalance or group/class constraints?
7. What does evidence say about automation bias and effective human oversight
   in decision support?
8. Which reproducibility, model-card, data-documentation, and ML-risk standards
   support the engineering-evidence framing?
9. What official CFPB caveats constrain representativeness, label meaning,
   narrative publication, and longitudinal comparisons?
10. Which prediction-model reporting items improve transparency without being
    misrepresented as evidence of operational impact?
11. How should a target trial specify assignment, estimands, outcomes, and
    analysis before causal estimation?
12. What prospective AI-intervention and human-AI studies demonstrate about the
    need to measure workflow effects rather than transport them?

## Planned claim-to-source matrix columns

| Field | Meaning |
|---|---|
| `source_id` | stable paper-local identifier |
| `primary_source` | yes/no and source type |
| `bibliographic_record` | authors, title, venue, year, DOI/URL |
| `supported_claim` | one precise paraphrased claim |
| `paper_section` | exact target subsection |
| `evidence_strength` | foundational, direct empirical, standard, or contextual |
| `scope_caveat` | what the source does not establish for this project |
| `quote_checked` | confirmation that wording was verified without copying long text |

The publication search is complete: every non-project factual claim in the
manuscript and causal protocol is mapped in `claim_source_matrix.md` or
explicitly marked as the author's synthesis. Citation IDs, links, and scope
caveats are tested against the final prose.
