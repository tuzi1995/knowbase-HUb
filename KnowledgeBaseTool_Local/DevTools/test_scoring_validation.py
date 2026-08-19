from datetime import datetime

import pytest

from scoring_logic import calculate_months_diff, calculate_product_overlap, normalize_scoring_result


def _valid_result():
    return {
        "分析过程": "test",
        "维度得分": {
            "问题质量": 10,
            "答案合规与准确性": 30,
            "时效性": 20,
            "实际解决力": 30,
            "非冗余与相关性": 10,
            "多媒体加分": 5,
        },
        "总分": 105,
        "处理建议": "直接保留",
    }


def test_scoring_result_rejects_out_of_range_dimension():
    result = _valid_result()
    result["维度得分"]["问题质量"] = 11
    with pytest.raises(ValueError, match="out of range"):
        normalize_scoring_result(result)


def test_scoring_result_rejects_total_that_disagrees_with_dimensions():
    result = _valid_result()
    result["总分"] = 100
    with pytest.raises(ValueError, match="dimension sum"):
        normalize_scoring_result(result)


def test_default_timeliness_baseline_uses_current_month():
    assert calculate_months_diff(datetime.now().strftime("%Y-%m-%d")) == 0


def test_empty_product_scope_is_not_counted_as_overlap():
    items = [
        {"kb_id": "KB-EMPTY", "question": "same", "product_name": ""},
        {"kb_id": "KB-G10", "question": "same", "product_name": "G10"},
    ]
    assert calculate_product_overlap(items) == {"KB-EMPTY": 0, "KB-G10": 0}
