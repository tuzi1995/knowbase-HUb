import json
import time
import pandas as pd
from datetime import datetime
import requests
import os
import re

# ================= 配置区 =================
# 产品型号定义
PRODUCT_CATALOG_TEXT = """
### 附录：官方产品型号列表
(供评分参考，用于辅助判断产品名称准确性及分类)

1. **扫地机**：P5, T6, T7, T7 Pro, T7S, T7S Plus, T8, T8 Plus, G10, G10 Plus, G10S, G10S Auto, G10S Pro, G10S Pure, G20, G20S, P10, P10 Pro, P10S, P10S Pure, P10S Pro 系列, P10S Pro 系列超薄嵌入式, P20 Pro, G20S Ultra, V20, 石头星耀Pro, G30, P20 Plus, P20 Ultra, G30 Space探索版, G30 U, P20, P20极光, P20 Ultra Plus, P20活水版, P20极光 增强版, G30曜石, G30S Pro, P20 Ultra活水版
2. **洗地机**：U10, A10, A10 Plus, A10 Ultra, A10 UltraE, A20, A20 Air, A20 Pro, A30 Pro, A30, A30 CE, A30 ProCE, A30 Pro Steam, A30 Lite, A30 SE, A30 Muse, A30 U, A30 Combo, A30 Pro Turbo, A30 Pure, A30 Pro Combo, A30 Pro Ultra, 拓界 Mist, 拓界 Aura, A30 Pro Steam 5合1版, 拓界 Pro, A30 CE 畅享版, A30 CE 悦享版, A30 Pro Steam 智享版, A30 Pro CE 悦享版, A30 2.0
3. **吸尘器**：H5, H6, H7, H50 Ultra, H50, H50 Pro
4. **洗衣机**：H1, H1 Air, H1 Neo, M1, M1 Pure, 洗烘一体机 Z1, 洗烘一体机 Z1 Pro, Q1, Q1M, 洗烘一体机 Z1 Plus, 洗衣机 Z1, M1S, M1S Pure, 洗衣机 Z1 Max, 洗衣机 Z1 Max 银盾版, 洗衣机 Z1 Max 智控版, 热泵干衣机 Z1 Max, 分子筛干衣机 Z1 Max, 套装 Z1 Max, Z1 Max Pro, Z1 Max Ultra, Q1 Hello Kitty
"""

# System Prompt (V7)
DEFAULT_SYSTEM_PROMPT = """你是一个专家级的企业知识库审计员。你的目标是确保QA对（问题与答案）能够直接用于智能客服检索和用户自助服务。

请按照以下步骤进行思维链（Chain-of-Thought）分析，并输出 JSON 结果：

### 评分标准（总分 100 分）

1. **问题质量 (10分)**
   - 评估：问题是否清晰、自包含、关键词明确。
   - **特殊豁免**：对于**指向性明确**的故障/功能描述（如“烘干时间跳动”、“无法建图”），即使省略主语，视为关键词明确，**不扣分**。
   - **不予豁免**：
     1. **指向性模糊**的通用症状（如“声音大”、“有异响”、“不动了”），若未指明具体部件或场景，判为**指代不明**，**扣10分**。
     2. **纯名词/参数堆砌**：对于非故障类的参数/属性询问（如“滚筒拖布贴边距离”、“水箱容量”），若无疑问词（如“是多少”、“多大”）或动词，视为**语意不完整**，**扣5分**。
   - 扣分：
     - **指代不明**（扣10分）：使用“它、这个”等悬空指代且无具体场景。
     - **语意不完整/关键词堆砌**（扣5分）：仅有名词短语且非故障描述。
     - 过于宽泛（扣5分）：如“使用说明”、“介绍一下”。

2. **答案合规与准确性 (30分)**
   - 评估：事实是否准确，是否包含敏感承诺，语气是否亲切专业。
   - 扣分：
     - **事实错误**（扣30分）：答案事实有误。若存在机型重叠，且关键参数与其他QA冲突（如尺寸数值不一致），视为事实错误/误导用户。
     - **敏感承诺/违规**（扣20分）：包含绝对化保证（如“100%修好”、“永远不坏”）、违规售后（如“无条件退款”超规则、私下补偿）、隐私引导、违法或低俗内容。
     - 语气生硬/推诿（扣10分）。

3. **时效性 (20分)**
   - **规则**（直接使用元数据中的 `距基准月数` 进行判定）：
     - **≤ 6 个月**：得 20 分
     - **6 < 月数 ≤ 12**：得 15 分
     - **12 < 月数 ≤ 24**：得 10 分
     - **24 < 月数**：得 5 分
     - **内容过期**：如果答案中包含的具体活动/时间已过（如“活动截止2025.12”），得 0 分。

4. **实际解决力 (30分)**
   - **故障/操作设置类**：必须包含**明确操作动作**（如点击、设置、查询、复位、清洁路径等），否则视为无步骤，扣15-20分。
   - **确认/参数类**（如“是否支持”、“尺寸/功率”、“有无功能”）：只需给出准确结论/数值即可，**不强制要求操作步骤**，不因此扣分。
   - 扣分：步骤逻辑混乱（扣10分）。

5. **非冗余与相关性 (10分)**
   - **核心规则**：
     1. **机型覆盖重叠**：如果`机型重叠计数` > 0（判定标准：覆盖机型完全一致或完全包含），说明存在冗余，**扣10分**。
     2. **内容无效冗余**：如果答案答非所问、与问题意图不符、或仅包含无关废话，视为无效信息，**扣10分**。
     3. **唯一且相关**：机型无重叠且内容紧扣问题，得10分。

6. **多媒体加分 (附加分, Max 10分)**
   - **评估**：答案中是否包含有助于理解的图片或视频链接（需检查 urls 字段）。
   - **规则**：
     - 包含有效图片：+5分
     - 包含有效视频：+10分
     - 无多媒体或多媒体失效：+0分
   - 此项为附加分，总分可超过100分。

""" + PRODUCT_CATALOG_TEXT + """
### 输出格式（JSON）
必须严格遵守此顺序，先分析后打分：
{
    "分析过程": "请在此处简要分析各维度的优缺点...",
    "维度得分": {
        "问题质量": int,
        "答案合规与准确性": int,
        "时效性": int,
        "实际解决力": int,
        "非冗余与相关性": int,
        "多媒体加分": int
    },
    "总分": int,
    "处理建议": "直接保留" | "优化后保留" | "建议删除"
}
"""

USER_PROMPT_TEMPLATE = """
请对以下QA对进行评分：

【元数据】
- 问题ID：{qid}
- 产品：{product}
- 更新时间：{update_time} (当前基准日期: {current_date})
- 距基准月数：{months_diff} 个月 (请直接使用此数值判断时效性)
- 机型重叠计数：{overlap_count} (如果>0，说明库中存在针对相同机型的相同问题，属冗余)

【内容】
- 问题：{question}
- 答案：{answer}
- 链接/多媒体资源：{urls} (用于判断“多媒体加分”)

请返回 JSON 结果。
"""

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORING_CONFIG_FILE = os.path.join(_BASE_DIR, 'scoring_config.json')
AI_CONFIG_FILE = os.path.join(_BASE_DIR, 'ai_config.json')

def load_scoring_config():
    default_config = {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "system_prompt": DEFAULT_SYSTEM_PROMPT
    }
    if not os.path.exists(SCORING_CONFIG_FILE):
        return default_config
    try:
        with open(SCORING_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if not isinstance(config, dict):
                return default_config
            merged = default_config.copy()
            merged.update(config)
            if not merged.get('system_prompt'):
                merged['system_prompt'] = DEFAULT_SYSTEM_PROMPT
            return merged
    except:
        return default_config

def save_scoring_config(config):
    tmp_file = f"{SCORING_CONFIG_FILE}.tmp"
    try:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, SCORING_CONFIG_FILE)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except Exception:
            pass
        return False

def load_ai_config():
    """
    加载 AI 润色等优化工具使用的 API 配置与 Prompt。
    若独立的 ai_config.json 不存在，则回退使用评分配置中的公共字段，保证兼容旧版本。
    """
    default_config = {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "ai_prompts": {}
    }
    if os.path.exists(AI_CONFIG_FILE):
        try:
            with open(AI_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if not isinstance(config, dict):
                    return default_config
                merged = default_config.copy()
                merged.update(config)
                if 'ai_prompts' not in merged or not isinstance(merged['ai_prompts'], dict):
                    merged['ai_prompts'] = {}
                return merged
        except Exception:
            return default_config

    # 兼容旧版本：如果还没有独立 AI 配置，则从评分配置中继承公共字段
    scoring_cfg = load_scoring_config()
    ai_cfg = {
        "api_key": scoring_cfg.get("api_key", ""),
        "base_url": scoring_cfg.get("base_url", "https://api.deepseek.com"),
        "model": scoring_cfg.get("model", "deepseek-chat"),
        "ai_prompts": scoring_cfg.get("ai_prompts") if isinstance(scoring_cfg.get("ai_prompts"), dict) else {}
    }
    merged = default_config.copy()
    merged.update(ai_cfg)
    if 'ai_prompts' not in merged or not isinstance(merged['ai_prompts'], dict):
        merged['ai_prompts'] = {}
    return merged

def save_ai_config(config):
    tmp_file = f"{AI_CONFIG_FILE}.tmp"
    try:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, AI_CONFIG_FILE)
        return True
    except Exception as e:
        print(f"Error saving AI config: {e}")
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except Exception:
            pass
        return False

# ================= 辅助函数 =================

def calculate_months_diff(update_time_str, baseline_str="2026-02-01"):
    """
    计算更新时间距离基准日期的月数差（向下取整）。
    """
    try:
        if not update_time_str or update_time_str == "未知" or update_time_str == "nan":
            return 999 
            
        update_date = pd.to_datetime(update_time_str)
        baseline_date = pd.to_datetime(baseline_str)
        
        diff = (baseline_date.year - update_date.year) * 12 + (baseline_date.month - update_date.month)
        return max(0, diff)
    except:
        return 999

def extract_json_object(text):
    """
    Some gateways accept response_format but still wrap JSON in markdown or
    short explanatory text. Keep parsing strict enough for malformed JSON while
    tolerating harmless wrappers.
    """
    if text is None:
        raise ValueError("empty model response")
    raw = str(text).strip()
    if not raw:
        raise ValueError("empty model response")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end > start:
        return json.loads(raw[start:end + 1])

    raise ValueError(f"model response is not JSON: {raw[:300]}")

def normalize_scoring_result(result):
    if not isinstance(result, dict):
        raise ValueError("model response JSON is not an object")

    dims = result.get("维度得分")
    if not isinstance(dims, dict):
        raise ValueError("model response missing object field: 维度得分")

    required_dim_keys = ["问题质量", "答案合规与准确性", "时效性", "实际解决力", "非冗余与相关性", "多媒体加分"]
    for key in required_dim_keys:
        if key not in dims:
            raise ValueError(f"model response missing score field: 维度得分.{key}")
        try:
            dims[key] = int(dims[key])
        except (TypeError, ValueError):
            raise ValueError(f"model response score field is not int: 维度得分.{key}")

    if "总分" not in result:
        result["总分"] = sum(dims.get(k, 0) for k in required_dim_keys)
    try:
        result["总分"] = int(result["总分"])
    except (TypeError, ValueError):
        raise ValueError("model response score field is not int: 总分")

    result["分析过程"] = str(result.get("分析过程") or "")
    suggestion = str(result.get("处理建议") or "").strip()
    if suggestion not in ("直接保留", "优化后保留", "建议删除"):
        suggestion = "优化后保留"
    result["处理建议"] = suggestion
    return result

def _response_preview(text, max_len=500):
    raw = "" if text is None else str(text)
    raw = raw.replace("\r", "\\r").replace("\n", "\\n")
    if len(raw) > max_len:
        return raw[:max_len] + "..."
    return raw

def _extract_chat_completion_content(data):
    """
    Support common OpenAI-compatible response variants. Some gateways return
    message.content as a list of parts, while others expose output_text.
    """
    if not isinstance(data, dict):
        raise RuntimeError("LLM response JSON is not an object")

    choices = data.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice, dict) else {}
    if not isinstance(message, dict):
        message = {}

    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                part_text = part.get("text") or part.get("content")
                if isinstance(part_text, dict):
                    part_text = part_text.get("value") or part_text.get("text")
                if part_text:
                    parts.append(str(part_text))
        content = "\n".join(parts)

    if content is None:
        content = message.get("reasoning_content")
    if content is None:
        content = data.get("output_text")
    if content is None and isinstance(data.get("output"), list):
        parts = []
        for output_item in data.get("output") or []:
            if not isinstance(output_item, dict):
                continue
            for content_item in output_item.get("content") or []:
                if isinstance(content_item, dict):
                    text = content_item.get("text") or content_item.get("content")
                    if text:
                        parts.append(str(text))
        content = "\n".join(parts)

    content = "" if content is None else str(content).strip()
    if not content:
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        response_keys = ",".join(sorted(str(k) for k in data.keys()))
        raise RuntimeError(
            "empty LLM message content "
            f"(finish_reason={finish_reason}, response_keys={response_keys})"
        )
    return content

def _extract_sse_chat_completion_content(text):
    parts = []
    errors = []
    saw_event = False
    event_summaries = []

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        saw_event = True
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue

        try:
            event = json.loads(payload)
        except json.JSONDecodeError as exc:
            errors.append(f"bad SSE JSON: {payload[:120]} ({exc})")
            continue

        if isinstance(event, dict) and event.get("error"):
            errors.append(str(event.get("error")))
            continue

        if isinstance(event, dict):
            choices = event.get("choices")
            event_summaries.append({
                "keys": sorted(str(k) for k in event.keys())[:8],
                "choices": len(choices) if isinstance(choices, list) else None,
                "usage": bool(event.get("usage"))
            })

        try:
            content = _extract_chat_completion_content(event)
            if content:
                parts.append(content)
            continue
        except RuntimeError:
            pass

        for choice in (event.get("choices") or []) if isinstance(event, dict) else []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("text"):
                            parts.append(str(part.get("text")))
                        elif isinstance(part, str):
                            parts.append(part)
                elif content:
                    parts.append(str(content))

            message = choice.get("message") or {}
            if isinstance(message, dict) and message.get("content"):
                content = message.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("text"):
                            parts.append(str(part.get("text")))
                        elif isinstance(part, str):
                            parts.append(part)
                else:
                    parts.append(str(content))

    content = "".join(parts).strip()
    if content:
        return content
    if errors:
        raise RuntimeError("; ".join(errors[:3]))
    if saw_event:
        summary = _response_preview(json.dumps(event_summaries[:3], ensure_ascii=False), 300)
        preview = _response_preview(text, 300)
        raise RuntimeError(f"empty LLM SSE response content: events={summary}; preview={preview}")
    raise RuntimeError("LLM response is not SSE data")

def calculate_product_overlap(all_items):
    """
    计算机型重叠冗余。
    all_items: list of dicts, must contain 'question', 'product_name' (or 'product'), 'id'
    Returns: dict {id: overlap_count}
    """
    if not all_items:
        return {}
        
    df = pd.DataFrame(all_items)
    
    # 统一字段名
    if 'product_name' not in df.columns and 'product' in df.columns:
        df['product_name'] = df['product']
        
    # 预处理：将 product_name 拆分为集合
    df['product_set'] = df['product_name'].fillna('').apply(lambda x: set([p.strip() for p in str(x).split(',') if p.strip()]))
    
    overlap_counts = {}
    
    # 按问题分组
    if 'question' not in df.columns:
        return {item['id']: 0 for item in all_items} # Fallback
        
    grouped = df.groupby('question')
    
    for question, group in grouped:
        indices = group.index.tolist()
        n = len(indices)
        
        if n < 2:
            for idx in indices:
                item_id = group.loc[idx, 'id'] if 'id' in group.columns else group.loc[idx, 'kb_id']
                overlap_counts[item_id] = 0
            continue
            
        for i in range(n):
            current_idx = indices[i]
            current_products = group.loc[current_idx, 'product_set']
            overlap_found = 0
            
            for j in range(n):
                if i == j: continue
                other_idx = indices[j]
                other_products = group.loc[other_idx, 'product_set']
                
                # 覆盖机型完全一致 / 完全包含 才算重叠
                if current_products.issubset(other_products) or other_products.issubset(current_products):
                    overlap_found += 1
            
            # Use 'id' or 'kb_id' as key
            item_id = group.loc[current_idx, 'id'] if 'id' in group.columns else group.loc[current_idx, 'kb_id']
            overlap_counts[item_id] = overlap_found
            
    return overlap_counts

class LLMScorer:
    def __init__(self, api_key, base_url, model, system_prompt=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def _chat_completions(self, messages, temperature=0.1, response_format=None, timeout=60):
        base = (self.base_url or "").strip().rstrip("/")
        if base.endswith("/v1"):
            base_v1 = base
        else:
            base_v1 = base + "/v1"
        url = base_v1 + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 400 and "stream" in (resp.text or "").lower():
            retry_payload = payload.copy()
            retry_payload.pop("stream", None)
            resp = requests.post(url, headers=headers, json=retry_payload, timeout=timeout)
        content_type = resp.headers.get("content-type", "")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"LLM HTTP {resp.status_code} ({content_type}): "
                f"{_response_preview(resp.text)}"
            )
        if "text/event-stream" in content_type.lower() or str(resp.text).lstrip().startswith("data:"):
            return _extract_sse_chat_completion_content(resp.text)
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"LLM response is not JSON (HTTP {resp.status_code}, "
                f"content-type={content_type}): {_response_preview(resp.text)}"
            ) from exc
        return _extract_chat_completion_content(data)

    def evaluate_one(self, item, overlap_count=0):
        """
        Evaluate a single item with retry logic.
        item: dict with keys: kb_id (or id), question, answer, product_name (or product), update_time
        """
        max_retries = 3
        retry_delay = 2
        
        qid = item.get('kb_id') or item.get('id') or 'unknown'
        question = item.get('question') or item.get('question_content') or ''
        answer = item.get('answer') or item.get('answer_content') or ''
        product = item.get('product_name') or item.get('product') or ''
        update_time = item.get('update_time') or item.get('updated_at') or '2025-01-01'
        
        # Calculate months diff
        current_date = datetime.now().strftime("%Y-%m-%d") # Use today as baseline or fixed?
        # User prompt says 2026-02-01 as baseline. Let's stick to the prompt's recommendation for consistency
        # Or use current real date? The prompt template has a placeholder.
        # Let's use the one passed in prompt or default.
        baseline_date = "2026-02-01" 
        months_diff = calculate_months_diff(str(update_time), baseline_date)

        user_content = USER_PROMPT_TEMPLATE.format(
            qid=qid,
            product=product,
            update_time=update_time,
            current_date=baseline_date,
            months_diff=months_diff,
            overlap_count=overlap_count,
            question=question,
            answer=answer,
            urls=item.get('urls') or '无'
        )

        last_error_msg = ""
        for attempt in range(max_retries + 1):
            try:
                content = self._chat_completions(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                result = normalize_scoring_result(extract_json_object(content))
                return result
                
            except Exception as e:
                error_msg = str(e)
                last_error_msg = error_msg
                if attempt < max_retries:
                    if "model response" in error_msg:
                        print(f"Failed to evaluate {qid}: {error_msg}")
                        return {"error": error_msg}
                    if "HTTP 400" in error_msg or "HTTP 401" in error_msg or "HTTP 403" in error_msg:
                        print(f"Failed to evaluate {qid}: {error_msg}")
                        return {"error": error_msg}
                    if "429" in error_msg:
                        time.sleep(65)
                    else:
                        time.sleep(retry_delay * (2 ** attempt))
                else:
                    print(f"Failed to evaluate {qid}: {error_msg}")
                    return {"error": error_msg}
        if last_error_msg:
            print(f"Failed to evaluate {qid}: {last_error_msg}")
            return {"error": last_error_msg}
        return {"error": "LLM scoring failed without error details"}
