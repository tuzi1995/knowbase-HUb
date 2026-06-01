#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修改记录API
直接调用API检查是否返回数据
"""

import requests
import json

BASE_URL = "http://localhost:8085"

def test_modifications_api():
    """测试修改记录API"""
    print("=" * 70)
    print("测试修改记录API")
    print("=" * 70)
    
    url = f"{BASE_URL}/api/kb/modifications"
    params = {
        'page': 1,
        'pageSize': 10
    }
    
    print(f"\n请求URL: {url}")
    print(f"参数: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"\n状态码: {response.status_code}")
        
        if response.status_code == 401:
            print("\n❌ 需要登录")
            print("请先在浏览器中登录 http://localhost:8085")
            return False
        
        if response.status_code != 200:
            print(f"\n❌ API返回错误")
            print(f"响应内容: {response.text[:500]}")
            return False
        
        # 解析响应
        try:
            data = response.json()
            print(f"\n✅ API响应成功")
            print(f"数据类型: {type(data)}")
            
            if isinstance(data, dict):
                total = data.get('total', 0)
                items = data.get('data', [])
                success = data.get('success', False)
                
                print(f"success: {success}")
                print(f"total: {total}")
                print(f"data数组长度: {len(items)}")
                
                if len(items) > 0:
                    print(f"\n前3条记录：")
                    for i, item in enumerate(items[:3], 1):
                        print(f"\n记录 {i}:")
                        print(f"  kb_id: {item.get('kb_id')}")
                        print(f"  modifier: {item.get('modifier')}")
                        print(f"  modification_time: {item.get('modification_time')}")
                        print(f"  change_type: {item.get('change_type')}")
                        print(f"  source: {item.get('source')}")
                        print(f"  question: {item.get('question', '')[:50]}...")
                    
                    return True
                else:
                    print("\n⚠️  返回的data数组为空")
                    print("这意味着：")
                    print("1. API端点正常工作")
                    print("2. 但是数据库中没有修改记录")
                    print("3. 或者查询条件过滤掉了所有记录")
                    return False
                    
            elif isinstance(data, list):
                print(f"返回数组长度: {len(data)}")
                if len(data) > 0:
                    print(f"\n第一条记录: {json.dumps(data[0], ensure_ascii=False, indent=2)}")
                    return True
                else:
                    print("\n⚠️  返回空数组")
                    return False
            else:
                print(f"\n⚠️  意外的响应格式")
                print(f"响应内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
                return False
                
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON解析失败: {e}")
            print(f"响应内容: {response.text[:500]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 无法连接到服务器: {BASE_URL}")
        print("请确保8085服务已启动")
        return False
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_server_log_hints():
    """提供服务器日志检查提示"""
    print("\n" + "=" * 70)
    print("服务器日志检查提示")
    print("=" * 70)
    
    print("""
请在8085服务的终端窗口中查找以下信息：

1. 查看保存时的日志：
   编辑并保存一条知识库记录后，查找：
   
   ✅ 成功的标志：
   - "[INFO] Modification record inserted successfully: <kb_id>"
   
   ❌ 失败的标志：
   - "[ERROR] Failed to insert modification record: <错误信息>"
   - "knowledge_base_modifications" 相关错误
   
2. 查看API调用日志：
   切换到"修改记录"标签页后，查找：
   - "GET /api/kb/modifications" - 应该返回200状态码
   
3. 常见错误模式：
   - "table knowledge_base_modifications does not exist" - 表不存在
   - "column ... does not exist" - 字段不存在
   - "null value in column" - 必填字段为空
   - "duplicate key value" - 主键冲突

4. 如何查看完整日志：
   - 在终端中向上滚动查看历史输出
   - 或者将日志重定向到文件：
     python3 server.py > server.log 2>&1
    """)

def test_save_and_check():
    """指导用户测试保存并检查"""
    print("\n" + "=" * 70)
    print("手动测试步骤")
    print("=" * 70)
    
    print("""
请按以下步骤测试：

步骤1：打开浏览器开发者工具
   - 按 F12 或 Cmd+Option+I
   - 切换到 Network 标签页
   - 勾选 "Preserve log"（保留日志）

步骤2：编辑并保存一条知识库记录
   - 进入"知识库管理"
   - 点击任意记录的"编辑"按钮
   - 修改问题或答案
   - 点击"保存"

步骤3：检查Network请求
   在Network标签页中查找以下请求：
   
   a) POST /api/kb/update
      - 状态码应该是 200
      - 响应应该包含 {"success": true, ...}
      - 检查响应中的 mod_log_ok 字段：
        * true - 修改记录插入成功
        * false - 修改记录插入失败，查看 mod_log_error
   
   b) PUT /api/kb/item/tags
      - 状态码应该是 200
      - 响应应该包含 {"success": true}

步骤4：切换到"修改记录"标签页
   - 点击"修改记录"标签
   - 在Network中查找 GET /api/kb/modifications
   - 检查响应：
     * 状态码应该是 200
     * 响应应该包含 {"success": true, "total": X, "data": [...]}
     * 如果 total > 0 但前端不显示，可能是前端渲染问题

步骤5：检查Console错误
   - 切换到 Console 标签页
   - 查看是否有JavaScript错误
   - 特别注意红色的错误信息

步骤6：查看服务器日志
   - 在运行8085的终端窗口中
   - 查找上述提到的日志信息
    """)

def main():
    print("\n🔍 开始测试修改记录功能\n")
    
    # 测试API
    result = test_modifications_api()
    
    # 提供日志检查提示
    check_server_log_hints()
    
    # 提供手动测试步骤
    test_save_and_check()
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    if result:
        print("✅ API端点正常工作，并且返回了数据")
        print("\n如果前端还是不显示，可能的原因：")
        print("1. 前端过滤条件过滤掉了记录")
        print("2. 前端渲染逻辑有问题")
        print("3. 浏览器缓存问题（尝试强制刷新）")
    else:
        print("⚠️  API测试未通过")
        print("\n可能的原因：")
        print("1. 需要登录（在浏览器中登录后再测试）")
        print("2. 数据库中确实没有修改记录")
        print("3. 保存时修改记录插入失败")
        print("\n建议：")
        print("1. 先在浏览器中登录")
        print("2. 编辑并保存一条知识库记录")
        print("3. 按照上述手动测试步骤检查")
        print("4. 查看服务器日志中的错误信息")

if __name__ == "__main__":
    main()
