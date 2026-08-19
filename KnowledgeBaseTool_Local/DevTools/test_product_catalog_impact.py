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
