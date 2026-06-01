import pandas as pd
import re

src = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\2026智能助理-语料库-第六周.xlsx"
df = pd.read_excel(src)

val = df.iloc[0, 15]

def cleaned_len(s):
    if pd.isna(s):
        return 0
    x = str(s)
    x = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", x)
    x = re.sub(r"[`*_~]+", "", x)
    x = re.sub(r"<[^>]+>", "", x)
    x = re.sub(r"\s+", "", x)
    return len(x)

print(len(str(val)))
print(cleaned_len(val))
