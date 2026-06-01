import json
import os
import sys
import time
import traceback


def _read_supabase_config(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if isinstance(cfg, dict):
        return cfg
    return {}


def main() -> int:
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(tool_dir)

    # Import from server.py (for SupabaseClient + retry logic).
    sys.path.insert(0, tool_dir)
    try:
        from server import get_supabase_client
    except Exception as e:
        print(f"Failed to import server.py dependencies: {e}")
        traceback.print_exc()
        return 2

    client = get_supabase_client()
    if not client:
        print("Supabase not configured.")
        return 3

    try:
        print("Starting manual sync: knowledge_base_v1 -> knowledge_base_v1_t1")
        print("Fetching all data from knowledge_base_v1 ...")

        v1_data = client.select_all(
            "knowledge_base_v1",
            order_by="question_wiki_id",
            page_size=1000,
        ) or []

        if not v1_data:
            print("v1 is empty, nothing to sync. Clearing t1 ...")
            del_resp = client.delete("knowledge_base_v1_t1", {"question_wiki_id": "not.is.null"})
            if getattr(del_resp, "status_code", 500) >= 400:
                print(f"Failed to clear t1: {getattr(del_resp, 'text', '')}")
                return 4
            print("t1 cleared.")
            return 0

        allowed_columns = [
            "question_wiki_id",
            "question_type",
            "question",
            "answer",
            "answer_type",
            "if_bm25",
            "similar_questions",
            "error_list",
            "keyword_list",
            "image_urls",
            "video_urls",
            "file_urls",
            "link_type",
            "link_url",
            "update_time",
            "product_category_name",
            "product_name",
        ]

        to_insert = []
        for item in v1_data:
            if not isinstance(item, dict):
                continue
            new_item = {}
            for col in allowed_columns:
                if col in item:
                    new_item[col] = item[col]
            # must keep primary key
            if new_item.get("question_wiki_id") is None:
                continue
            to_insert.append(new_item)

        print(f"Prepared {len(to_insert)} items for sync.")

        print("Clearing knowledge_base_v1_t1 ...")
        del_resp = client.delete("knowledge_base_v1_t1", {"question_wiki_id": "not.is.null"})
        if getattr(del_resp, "status_code", 500) >= 400:
            print(f"Failed to clear t1: {getattr(del_resp, 'text', '')}")
            return 5

        batch_size = 500
        total = len(to_insert)
        print(f"Inserting into t1 in batches of {batch_size} (total={total}) ...")
        start = time.time()
        for i in range(0, total, batch_size):
            batch = to_insert[i : i + batch_size]
            idx = i // batch_size + 1
            print(f"Inserting batch {idx}/{(total + batch_size - 1) // batch_size} ...")
            resp = client.insert("knowledge_base_v1_t1", batch)
            if getattr(resp, "status_code", 500) >= 400:
                print(f"Batch insert failed at index {i}: {getattr(resp, 'text', '')}")
                return 6
            time.sleep(0.1)  # small delay to prevent rate limits

        elapsed = time.time() - start
        print(f"Sync completed successfully. Synced {total} items. Elapsed: {elapsed:.1f}s")
        return 0
    except Exception as e:
        print(f"Manual sync failed: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

