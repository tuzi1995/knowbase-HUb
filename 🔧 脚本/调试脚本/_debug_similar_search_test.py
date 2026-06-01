import json
import re


def _sm_strip_number_prefix(s):
    s = str(s or "")
    return re.sub(r"^\s*(?:\(?\d+\)?[\.|、\)|\]]\s*)+", "", s)


def _sm_sort_lines(s):
    s = str(s or "")
    parts = [p.strip() for p in re.split(r"[\r\n]+", s) if p and str(p).strip()]
    if len(parts) <= 1:
        return s
    return "\n".join(sorted(parts))


def _sm_strip_particles_end(s):
    return re.sub(r"(吗|么|呀|啊|吧|呢|嘛)+\s*$", "", str(s or ""))


def _sm_remove_punct_and_space(s):
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(s or ""))


def _sm_norm_for_sim(s):
    s0 = _sm_strip_number_prefix(s)
    s1 = _sm_sort_lines(s0)
    s2 = _sm_strip_particles_end(s1)
    s3 = _sm_remove_punct_and_space(s2)
    return s3


def _rc_parse_similar_questions(v):
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        seen = set()
        for x in v:
            s = str(x or "").strip()
            if not s or s in seen:
                continue
            out.append(s)
            seen.add(s)
        return out
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            try:
                obj = json.loads(s)
                return _rc_parse_similar_questions(obj)
            except Exception:
                pass
        parts = [x.strip() for x in re.split(r"[\n\r]+|[,，;；、/\t]+", s) if x and x.strip()]
        out = []
        seen = set()
        for x in parts:
            if x in seen:
                continue
            out.append(x)
            seen.add(x)
        return out
    return []


def _contains_similar_kw(similar_question_search, row_similar_questions):
    sim_kw_raw = str(similar_question_search or "").strip()
    sim_kw = _sm_norm_for_sim(sim_kw_raw)
    sims = _rc_parse_similar_questions(row_similar_questions)
    merged = _sm_norm_for_sim(" ".join(sims))
    return sim_kw in merged


def main():
    cases = [
        ("延保卡申请后时效要多久", ["延保卡申请后时效要多久", "延保卡多久生效"]),
        ("延保卡  时效", "[\"延保卡申请后时效要多久\",\"延保卡多久生效\"]"),
        ("生效", "延保卡申请后时效要多久, 延保卡多久生效"),
        ("多久生效", "延保卡申请后时效要多久\n延保卡多久生效"),
        ("延保卡多久生效", "【延保卡多久生效】；延保卡申请后时效要多久？"),
    ]
    for q, v in cases:
        ok = _contains_similar_kw(q, v)
        print(f"{q!r} => {ok}  (stored={type(v).__name__})")


if __name__ == "__main__":
    main()

