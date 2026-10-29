"""Evidence-led remediation suggestions for Sentinel incidents.

Recommendations are deliberately deterministic: they propose investigation and validation,
not unreviewed production changes. The UI can explain the evidence without inventing it.
"""
from __future__ import annotations


def recommend_remediation(result: dict, dataset: str = "") -> dict:
    verdict = str(result.get("verdict", "unclear")).lower()
    issues = result.get("issues") or []
    masked = result.get("masked") or []
    candidates = result.get("candidates") or []
    suspect = result.get("suspect") or (candidates[0].get("label") or candidates[0].get("feature") if candidates else None)
    evidence = []
    for issue in issues[:5]:
        if isinstance(issue, dict):
            evidence.append(str(issue.get("message") or issue.get("text") or issue.get("issue") or issue))
        else:
            evidence.append(str(issue))
    if masked:
        evidence.append("Quality checks masked: " + ", ".join(map(str, masked)))
    if suspect:
        evidence.append(f"Most likely affected feature: {suspect}")
    if not evidence:
        evidence.append(str(result.get("headline") or f"Sentinel verdict: {verdict}"))

    if verdict == "quality" or issues or masked:
        method = "validate_and_correct_data_pipeline"
        title = "Validate the data source and pipeline first"
        why = "Sentinel reported data-quality evidence. Model retraining on malformed or incorrectly transformed data can encode the problem rather than solve it."
        steps = ["Inspect schema, nulls, ranges, units, and recent upstream transformations.", "Compare affected values with source-system records and the last healthy batch.", "Correct the source or transformation only after confirming the cause, then replay corrected data."]
        validation = ["Quality checks pass on a fresh batch.", "Affected feature ranges and units match the documented contract.", "The incident does not recur in subsequent batches."]
        confidence = "high" if verdict == "quality" else "moderate"
    elif verdict == "shift":
        method = "investigate_shift_before_retraining"
        title = "Investigate the shift and monitor model quality"
        why = "The feature distribution changed, but Sentinel did not find a clear broken learned relationship. Drift alone does not prove that model performance has degraded."
        steps = ["Compare the shift by customer, region, time, and other meaningful segments.", "Check prediction quality against newly available labels or business KPIs.", "If performance remains acceptable, document the shift and monitor; retrain only if validated performance or the operating process has changed."]
        validation = ["Segment-level checks identify whether the change is expected.", "Recent labeled performance remains within agreed limits, or a retraining experiment improves it on a holdout set."]
        confidence = "moderate"
    elif verdict == "broken":
        method = "trace_feature_relationship_and_source"
        title = "Trace the affected feature and its upstream dependencies"
        why = "A learned relationship appears to have broken, which is consistent with a feature-specific source, unit, transformation, or genuine process change. The diagnosis narrows investigation but does not establish root cause by itself."
        steps = [f"Inspect the source, transformations, units, and sensors for {suspect or 'the suspected feature'}.", "Compare raw upstream values with the feature delivered to the model.", "If the pipeline is correct and the real process has changed, collect representative labeled data and evaluate a retrained model offline."]
        validation = ["The source-to-feature lineage is verified.", "The relationship residuals return to their healthy range after an approved correction, or an offline retrained model passes holdout evaluation."]
        confidence = "moderate"
    elif verdict == "unclear":
        method = "collect_more_evidence_before_changes"
        title = "Collect more evidence before changing the model"
        why = "The available residual fingerprints do not uniquely identify a cause. Acting on a single guessed feature could introduce an unnecessary or harmful change."
        steps = ["Review the top candidate features and their evidence together.", "Check data contracts, upstream logs, and affected segments; compare with an independent measurement if possible.", "Gather another representative batch and label outcomes before choosing a correction or retraining."]
        validation = ["A root cause is supported by independent evidence.", "A proposed fix is tested on a holdout batch before rollout."]
        confidence = "low"
    elif verdict == "insufficient":
        method = "restore_usable_data_and_recheck"
        title = "Restore enough valid data to diagnose safely"
        why = "There is not enough usable evidence for a reliable diagnosis. A remediation choice now would be speculative."
        steps = ["Check row volume, missingness, schema, and whether monitored columns are present.", "Restore or collect a sufficiently large valid batch.", "Run Sentinel again before deciding whether to retrain or alter the pipeline."]
        validation = ["The batch meets minimum usable-row requirements.", "Sentinel can evaluate the batch without an insufficient-data verdict."]
        confidence = "low"
    else:
        method = "continue_monitoring"
        title = "Continue monitoring; no corrective action indicated"
        why = "Sentinel did not identify a drift incident in this batch. Avoid unnecessary changes and keep monitoring for recurrence or performance degradation."
        steps = ["Keep the current baseline and monitoring schedule.", "Review model performance when labels become available.", "Escalate if a repeatable shift or performance issue appears."]
        validation = ["Subsequent batches remain within calibrated limits.", "Model performance remains within agreed business thresholds."]
        confidence = "moderate"
    return {
        "dataset": dataset,
        "diagnosis": verdict,
        "title": title,
        "recommended_method": method,
        "evidence": evidence,
        "reasoning": why,
        "confidence": confidence,
        "limitations": ["This is a decision-support recommendation, not proof of root cause.", "Review and validate changes before applying them to production."],
        "action_steps": steps,
        "validation_criteria": validation,
        "status": "pending_review",
    }
