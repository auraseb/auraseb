#!/usr/bin/env python3
"""Write merges.json (list of ISO mergedAt timestamps) from posted.json.
Python 3 stdlib only. Token from env GH_TOKEN. Batches PR lookups through GraphQL.
usage: merges_from_posted.py posted.json merges.json
"""
import json, os, re, sys, urllib.request

def gql(query, token):
    req = urllib.request.Request("https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": "bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def main(src, dst):
    token = os.environ["GH_TOKEN"]
    posted = json.load(open(src))
    prs = []
    for v in posted.values():
        m = re.match(r"https://github.com/([^/]+)/([^/]+)/pull/(\d+)", v.get("pr") or "")
        if m:
            prs.append(m.groups())
    out = []
    for i in range(0, len(prs), 50):
        chunk = prs[i:i + 50]
        q = "query{" + "".join(
            'p%d:repository(owner:"%s",name:"%s"){pullRequest(number:%s){mergedAt}}' % (j, o, n, num)
            for j, (o, n, num) in enumerate(chunk)) + "}"
        data = (gql(q, token).get("data") or {})
        for v in data.values():
            if v and v.get("pullRequest") and v["pullRequest"].get("mergedAt"):
                out.append(v["pullRequest"]["mergedAt"])
    out.sort()
    json.dump(out, open(dst, "w"), indent=1)
    print(len(prs), "prs,", len(out), "merged")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
