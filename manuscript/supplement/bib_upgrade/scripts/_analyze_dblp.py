import json
r = json.load(open("supplement/bib_upgrade/dblp_results.json"))
print("KEYS WITH A PEER-REVIEWED (non-CoRR) STRICT MATCH (ratio>=0.90 & surname_ok):\n")
peer=[]
for k,v in r.items():
    if "candidates" not in v: 
        print(f"{k}: ERROR/{v.get('error','?')}"); continue
    good = [c for c in v["candidates"] if c["type"] not in ("Informal and Other Publications","") and c["ratio"]>=0.90 and c["surname_ok"]]
    if good:
        peer.append(k)
        for c in good:
            print(f"{k}: venue={c['venue']} yr={c['year']} type='{c['type']}' r={c['ratio']} doi={c['doi']}")
            print(f"     ee={c['ee']}")
            print(f"     dblp_title={c['htitle']}")
            print(f"     authors={c['authors']}")
        print()
print("\nPEER-REVIEWED KEYS:", peer)
print("COUNT:", len(peer))

print("\n\nKEYS WITHOUT A PEER-REVIEWED MATCH (candidates shown):")
for k,v in r.items():
    if "candidates" not in v: continue
    good = [c for c in v["candidates"] if c["type"] not in ("Informal and Other Publications","") and c["ratio"]>=0.90 and c["surname_ok"]]
    if not good:
        cs = v["candidates"]
        print(f"{k}: {'NO HITS' if not cs else ''}")
        for c in cs:
            print(f"     r={c['ratio']} surname_ok={c['surname_ok']} type='{c['type']}' venue={c['venue']} yr={c['year']}")
