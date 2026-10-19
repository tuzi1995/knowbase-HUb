from unittest.mock import patch

import server


def test_product_catalog_impact_returns_payload_for_added_model():
    current_catalog = {"洗地机": ["A30"]}
    new_catalog = {"洗地机": ["A30", "A30 Pro Ultra 3.0"]}

    with server.app.app_context(), \
            patch.object(server, "parse_product_catalog", return_value=current_catalog), \
            patch.object(server.db.session, "query") as query:
        query.return_value.distinct.return_value.all.return_value = []
        impact = server._build_product_catalog_impact(new_catalog)

    assert impact == {
        "removed_models": [],
        "removed_model_count": 0,
        "matrix_column_count": 0,
        "matrix_row_count": 0,
        "orphan_models": [],
        "orphan_model_count": 0,
        "orphan_row_count": 0,
        "requires_confirmation": False,
    }


def test_catalog_release_rows_reads_persisted_model_states_once():
    class Repository:
        def __init__(self):
            self.read_count = 0

        def model_state_map(self):
            self.read_count += 1
            return {"A30": {"release_status": "pending_release", "current_application_id": "APP-1"}}

        def model(self, _model_id):
            raise AssertionError("release rows must use the batched state read")

    repository = Repository()
    with patch.object(server, "parse_product_catalog", return_value={"洗地机": ["A30", "A30 Pro"]}), \
            patch.object(server, "parse_product_release_intents", return_value={}), \
            patch.object(server._NEW_PRODUCT_RELEASE_SERVICE, "repository", repository):
        rows = server._catalog_release_rows()

    assert repository.read_count == 1
    assert [(row["model_id"], row["release_status"]) for row in rows] == [
        ("A30", "pending_release"),
        ("A30 Pro", "released"),
    ]
