#!/usr/bin/env python3
"""
调试脚本：测试 /api/kb/update 接口的响应格式
"""
import requests
import json

# 测试配置
BASE_URL = "http://localhost:8085"
LOGIN_URL = f"{BASE_URL}/login"
UPDATE_URL = f"{BASE_URL}/api/kb/update"

# 登录信息（请根据实际情况修改）
USERNAME = "admin"
PASSWORD = "admin"

def test_kb_update():
    """测试知识库更新接口"""
    
    # 创建会话
    session = requests.Session()
    
    # 1. 登录
    print("1. 正在登录...")
    login_data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    login_resp = session.post(LOGIN_URL, json=login_data)
    print(f"   登录状态码: {login_resp.status_code}")
    print(f"   登录响应: {login_resp.text[:200]}")
    
    if login_resp.status_code != 200:
        print("❌ 登录失败")
        return
    
    login_result = login_resp.json()
    if not login_result.get('success'):
        print(f"❌ 登录失败: {login_result.get('message')}")
        return
    
    print("✅ 登录成功\n")
    
    # 2. 测试更新接口（使用一个已存在的 ID）
    print("2. 测试更新接口...")
    update_data = {
        "question_wiki_id": "ICWIKI202604080002",  # 请替换为实际存在的 ID
        "question": "测试问题 - 调试",
        "answer": "测试答案 - 调试",
        "product_name": "IC-F3003",
        "question_type": "功能操作",
        "answer_type": "文字"
    }
    
    print(f"   请求数据: {json.dumps(update_data, ensure_ascii=False, indent=2)}")
    
    update_resp = session.post(UPDATE_URL, json=update_data)
    
    print(f"\n   响应状态码: {update_resp.status_code}")
    print(f"   响应头: {dict(update_resp.headers)}")
    print(f"   响应内容类型: {update_resp.headers.get('Content-Type')}")
    print(f"   响应文本长度: {len(update_resp.text)}")
    print(f"\n   完整响应文本:")
    print("   " + "="*60)
    print(update_resp.text)
    print("   " + "="*60)
    
    # 尝试解析 JSON
    try:
        resp_json = update_resp.json()
        print(f"\n   解析后的 JSON:")
        print(f"   {json.dumps(resp_json, ensure_ascii=False, indent=2)}")
        
        # 检查关键字段
        print(f"\n   关键字段检查:")
        print(f"   - success: {resp_json.get('success')}")
        print(f"   - question_wiki_id: {resp_json.get('question_wiki_id')}")
        print(f"   - message: {resp_json.get('message')}")
        print(f"   - error: {resp_json.get('error')}")
        print(f"   - no_change: {resp_json.get('no_change')}")
        
        # 检查是否有额外的字段
        expected_fields = {'success', 'question_wiki_id', 'mod_log_ok', 'mod_log_error', 'message', 'error', 'no_change'}
        extra_fields = set(resp_json.keys()) - expected_fields
        if extra_fields:
            print(f"\n   ⚠️  发现额外字段: {extra_fields}")
            for field in extra_fields:
                print(f"      - {field}: {resp_json[field]}")
        
        # 判断前端会如何处理
        if resp_json.get('success'):
            print(f"\n✅ 前端应该显示：保存成功")
        else:
            msg = resp_json.get('message') or resp_json.get('error') or '未知错误'
            print(f"\n❌ 前端应该显示：保存失败: {msg}")
            
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 解析失败: {e}")
        print(f"   这可能是导致前端报错的原因！")

if __name__ == "__main__":
    test_kb_update()
