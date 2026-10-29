from sentinel.remediation import recommend_remediation


def test_quality_recommendation_prioritizes_pipeline_fix_over_retraining():
    result = recommend_remediation({"verdict": "quality", "issues": ["invalid units"], "masked": ["length"]}, "diamonds")
    assert result["recommended_method"] == "validate_and_correct_data_pipeline"
    assert "retraining" in result["reasoning"].lower()
    assert result["validation_criteria"]


def test_shift_recommendation_does_not_assume_model_failure():
    result = recommend_remediation({"verdict": "shift", "headline": "Feature distribution moved"}, "abalone")
    assert result["recommended_method"] == "investigate_shift_before_retraining"
    assert "does not prove" in result["reasoning"]


def test_ambiguous_diagnosis_requires_more_evidence():
    result = recommend_remediation({"verdict": "unclear", "candidates": [{"feature": "a"}]})
    assert result["recommended_method"] == "collect_more_evidence_before_changes"
    assert "production" in " ".join(result["limitations"])


def test_every_recommendation_has_steps_and_validation():
    for verdict in ("quality", "broken", "unclear", "insufficient", "shift", "normal"):
        result = recommend_remediation({"verdict": verdict})
        assert result["action_steps"]
        assert result["validation_criteria"]
        assert result["evidence"]
