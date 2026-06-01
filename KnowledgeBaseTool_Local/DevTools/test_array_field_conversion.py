#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数组字段转换功能

验证 _convert_array_fields_to_json() 函数是否正确工作
"""

import sys
import os
import json

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_convert_array_fields():
    """测试数组字段转换函数"""
    
    # 导入函数
    try:
        from server import _convert_array_fields_to_json
        print("✅ 成功导入 _convert_array_fields_to_json 函数")
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    
    # 测试用例 1: 单个记录
    print("\n测试用例 1: 单个记录")
    test_record = {
        'kb_id': 'TEST001',
        'question': '测试问题',
        'keyword_list': ['关键词1', '关键词2', '关键词3'],
        'error_list': ['错误1', '错误2'],
        'similar_questions': ['相似问题1', '相似问题2'],
        'image_urls': ['http://example.com/img1.jpg'],
        'video_urls': [],
        'file_urls': None,
        'other_field': 'some value'
    }
    
    print(f"转换前: keyword_list 类型 = {type(test_record['keyword_list'])}")
    print(f"转换前: keyword_list 值 = {test_record['keyword_list']}")
    
    _convert_array_fields_to_json(test_record)
    
    print(f"转换后: keyword_list 类型 = {type(test_record['keyword_list'])}")
    print(f"转换后: keyword_list 值 = {test_record['keyword_list']}")
    
    # 验证转换结果
    assert isinstance(test_record['keyword_list'], str), "keyword_list 应该是字符串"
    assert isinstance(test_record['error_list'], str), "error_list 应该是字符串"
    assert isinstance(test_record['similar_questions'], str), "similar_questions 应该是字符串"
    assert isinstance(test_record['image_urls'], str), "image_urls 应该是字符串"
    assert isinstance(test_record['video_urls'], str), "video_urls 应该是字符串"
    assert test_record['file_urls'] is None, "file_urls 应该保持 None"
    assert test_record['other_field'] == 'some value', "其他字段不应该被修改"
    
    # 验证 JSON 可以被解析回来
    parsed_keywords = json.loads(test_record['keyword_list'])
    assert parsed_keywords == ['关键词1', '关键词2', '关键词3'], "JSON 解析后应该恢复原始数组"
    
    print("✅ 测试用例 1 通过")
    
    # 测试用例 2: 记录列表
    print("\n测试用例 2: 记录列表")
    test_records = [
        {
            'kb_id': 'TEST002',
            'keyword_list': ['A', 'B'],
            'error_list': []
        },
        {
            'kb_id': 'TEST003',
            'keyword_list': ['C', 'D', 'E'],
            'similar_questions': ['Q1']
        }
    ]
    
    _convert_array_fields_to_json(test_records)
    
    assert isinstance(test_records[0]['keyword_list'], str), "第一条记录的 keyword_list 应该是字符串"
    assert isinstance(test_records[0]['error_list'], str), "第一条记录的 error_list 应该是字符串"
    assert isinstance(test_records[1]['keyword_list'], str), "第二条记录的 keyword_list 应该是字符串"
    assert isinstance(test_records[1]['similar_questions'], str), "第二条记录的 similar_questions 应该是字符串"
    
    print("✅ 测试用例 2 通过")
    
    # 测试用例 3: 边界情况
    print("\n测试用例 3: 边界情况")
    edge_cases = [
        {},  # 空记录
        {'kb_id': 'TEST004'},  # 没有数组字段
        {'kb_id': 'TEST005', 'keyword_list': 'already a string'},  # 已经是字符串
        {'kb_id': 'TEST006', 'keyword_list': None},  # None 值
    ]
    
    _convert_array_fields_to_json(edge_cases)
    
    assert edge_cases[2]['keyword_list'] == 'already a string', "已经是字符串的字段不应该被修改"
    assert edge_cases[3]['keyword_list'] is None, "None 值不应该被修改"
    
    print("✅ 测试用例 3 通过")
    
    print("\n" + "="*50)
    print("✅ 所有测试通过！数组字段转换功能正常工作")
    print("="*50)
    
    return True

if __name__ == '__main__':
    try:
        success = test_convert_array_fields()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
