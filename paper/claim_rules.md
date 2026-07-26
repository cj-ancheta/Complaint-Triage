# Claim and wording rules

## Required framing

- Label the manuscript and every result display **validation-only**.
- Call every reported model value **validation evidence**, **validation result**,
  or **tuning evidence**.
- Describe the selected MiniLM as the **research candidate**, not a deployed or
  production model.
- Describe `manual_review_only` as the empirical and governance outcome and
  translate it as **manual review** for readers.
- State that the frozen November-December 2024 test partition was untouched and
  that **frozen-test** access remains unauthorized.
- Separate observed repository controls from broader claims about trustworthy AI.
- Separate observed predictive results from the proposed causal estimands and
  label the target trial `design_blueprint_not_registered_not_conducted`.

## Prohibited substitutions

| Do not write | Write instead |
|---|---|
| "The model achieves 88.6% accuracy." | "On the reused temporal validation partition, MiniLM accuracy was 0.8859." |
| "MiniLM significantly outperformed TF-IDF." | "MiniLM had higher observed validation macro F1; no inferential significance test was predeclared." |
| "The calibrated model is reliable." | "Temperature scaling improved the declared aggregate October calibration diagnostics." |
| "The system can automate complaint routing." | "No threshold met every gate, so all cases remain manual." |
| "The model is fair." | "Demographic fairness was not assessed." |
| "The dataset represents consumers." | "The data are published CFPB complaints and are not population-representative." |
| "CI proves the system is secure." | "Required CI checks reduce specified software and supply-chain risks." |
| "Human oversight solves the risk." | "Human review is a required safeguard whose effectiveness was not measured." |
| "The model improves reviewer accuracy or productivity." | "A prospective randomized workflow study is required to estimate those effects." |
| "The causal study shows..." | "The proposed causal protocol would estimate...; no trial was conducted." |

## Numerical rules

- Keep unrounded values in generation code and use consistent display precision
  in tables.
- Never introduce a number by manually transcribing it when it can be generated
  from committed JSON.
- Label September calibration-fit diagnostics as in-sample.
- Label October calibration/abstention results as validation tuning evidence.
- Do not calculate or imply a frozen-test estimate.
- Do not infer uncertainty beyond the Wilson intervals already predeclared for
  selective precision; those intervals do not address shift or dependence.
- Do not invent a causal effect, non-inferiority margin, power calculation, or
  reviewer baseline from validation metrics.

## Privacy rules

- No narrative fragments, paraphrased examples, vocabulary, complaint IDs, or
  row-level predictions.
- No screenshots of local data, model artifacts, database rows, or environment
  secrets.
- Aggregate confusion matrices and class counts are allowed.
- Literature examples must not be presented as examples from this dataset.

## Citation rules

- Use primary papers for methods and original empirical claims.
- Use official CFPB material for database provenance and publication caveats.
- Use official tool documentation only for implementation-specific behavior.
- Cite a source exactly where its claim appears; do not use one citation as
  blanket support for a paragraph of unrelated claims.
- Mark synthesis and project-specific interpretation as such.
