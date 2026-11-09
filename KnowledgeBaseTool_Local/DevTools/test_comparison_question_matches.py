"""Exact KB question matching, including separately mentioned prefix models."""
from comparison_matrix import question_match_fields


CATALOG = {'扫地机': ['G30S Pro', 'G30S Pro铂金版', 'P30 Pro']}


def test_separate_short_model_is_not_hidden_by_long_model():
    row = {'question': 'G30S Pro对比G30S Pro铂金版'}
    result = question_match_fields(row, '扫地机', ['G30S Pro', 'G30S Pro铂金版'], CATALOG)
    assert result['question_match_sources'] == ['主问题']


def test_similar_question_matches_prefix_pair_with_whitespace():
    row = {'question': '产品对比', 'similar_questions': ['G30S Pro 铂金版 对比 G30S Pro']}
    result = question_match_fields(row, '扫地机', ['G30S Pro', 'G30S Pro铂金版'], CATALOG)
    assert result['question_match_sources'] == ['相似问题']


def test_long_model_alone_does_not_create_a_short_model_mention():
    row = {'question': 'G30S Pro铂金版对比P30 Pro'}
    assert not question_match_fields(row, '扫地机', ['G30S Pro', 'G30S Pro铂金版'], CATALOG)['question_match_sources']
    assert question_match_fields(row, '扫地机', ['G30S Pro铂金版', 'P30 Pro'], CATALOG)['question_match_sources'] == ['主问题']


def test_a_third_model_prevents_exact_pair_confirmation():
    row = {'question': 'G30S Pro、G30S Pro铂金版和P30 Pro对比'}
    assert not question_match_fields(row, '扫地机', ['G30S Pro', 'G30S Pro铂金版'], CATALOG)['question_match_sources']
