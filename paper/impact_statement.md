# Impact statement

Financial complaint classifiers can look successful while serving common
categories far better than rare but required routes. This study shows why that
matters at the release decision. A compact transformer reached 0.8859 accuracy
on a reused temporal validation partition and improved class-balanced metrics
over a TF-IDF reference. After calibration, a confidence threshold of 0.80
appeared attractive at the aggregate level: 0.9450 selective accuracy at 0.8254
coverage. Yet it produced no suggestions for one required category and failed
the predeclared class-aware policy. The project therefore retained manual review
instead of presenting the threshold as safe automation.

The immediate impact is methodological and decision-facing. The work provides a
reproducible example of a no-go decision in which class completeness overrides
an appealing global number. It demonstrates how duplicate isolation, temporal
validation, per-class metrics, calibration diagnostics, selective-prediction
gates, privacy controls, artifact lineage, and protected continuous integration
can operate as one empirical system. Publishing the failed gate is valuable:
it makes visible a failure mode that could otherwise disappear behind aggregate
accuracy.

The paper also separates predictive evidence from causal impact. The public
complaint cohort does not record randomized access to model suggestions,
reviewer decisions under alternative interfaces, active review time, or
downstream consumer outcomes. It therefore cannot show that AI assistance
improves accuracy, productivity, resolution, or harm. The paper responds with a
prospective target-trial blueprint rather than causal rhetoric. It defines a
manual-only control, a governed suggestion-interface intervention,
contamination-aware randomization, intention-to-treat effects on independently
adjudicated routing correctness and active review time, and route-specific
safety constraints that an average benefit cannot override.

For practitioners, the actionable message is that model selection, release,
and impact evaluation are separate gates. Better validation performance can
justify further research; it does not authorize model exposure. A future trial
could establish workflow benefit only after stakeholder-defined harm margins,
power analysis, prospective registration, independent adjudication, monitoring,
and ethics/privacy review. Until then, the defensible operational conclusion is
manual review only.
