# -*- coding: utf-8 -*-
"""把 分析/merged_W.json 里的权重写回 hive/ai.py（只改 W 里已存在的键）。"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = json.load(open(os.path.join(ROOT, "分析", "merged_W.json"), encoding="utf-8"))
p = os.path.join(ROOT, "hive", "ai.py")
s = open(p, encoding="utf-8").read()
done = []
for k, v in W.items():
    if k.startswith("_"):
        continue
    pat = re.compile(r'("%s":\s*)(-?[0-9.]+)' % re.escape(k))
    if not pat.search(s):
        continue
    old = pat.search(s).group(2)
    if abs(float(old) - float(v)) < 1e-9:
        continue
    s = pat.sub(lambda m: m.group(1) + ("%g" % v), s, count=1)
    done.append((k, old, v))
open(p, "w", encoding="utf-8").write(s)
for k, o, v in done:
    print("%-16s %8s -> %8g" % (k, o, v))
print("共改 %d 项" % len(done))
