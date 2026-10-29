from server.admin_store import AdminStore
from sentinel.remediation import recommend_remediation


def test_client_incident_assignment_and_recommendation_persist(tmp_path):
    store = AdminStore(tmp_path / "admin.sqlite3")
    client = store.add_client("Example client", "ops@example.com")
    incident = store.add_incident("r-test", "diamonds", 3, {
        "verdict": "quality", "title": "Quality issue", "headline": "Unexpected units",
        "suspect": "length", "confidence": "high", "issues": ["unit scale changed"],
        "masked": ["length"], "candidates": [],
    })
    assert incident is not None
    assert store.update_incident_client(incident["id"], client["id"])
    row = store.get_incident(incident["id"])
    payload = recommend_remediation({**row["evidence"], "verdict": row["verdict"], "headline": row["headline"]}, row["dataset"])
    store.save_recommendation(incident["id"], payload)
    assert store.update_incident_status(incident["id"], "resolved")
    listed = store.incidents("resolved")
    assert len(listed) == 1
    assert listed[0]["client_id"] == client["id"]
    assert listed[0]["recommendation"]["payload"]["recommended_method"] == "validate_and_correct_data_pipeline"
