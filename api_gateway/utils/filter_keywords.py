import re

def get_search_keywords(keywords):
    search_keywords = []
    for keyword in keywords:
        match = re.fullmatch(r"(\d+(?:\s*/\s*\d+)*)\s*KV", keyword, re.I)
        if match:
            v = re.sub(r"\s*/\s*", "/", match.group(1))
            variants = {f"{v} KV", f"{v}KV", f"{v} kv"}
            if "/" in v: variants.add(f"{v.replace('/', ' / ')} KV")
            search_keywords.extend(variants)
        else:
            search_keywords.append(keyword)
    return list(dict.fromkeys(search_keywords))

