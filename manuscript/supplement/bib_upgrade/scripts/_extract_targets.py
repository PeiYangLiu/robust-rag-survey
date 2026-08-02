import re, json

KEYS = "rrag001 rrag002 rrag003 rrag004 rrag005 rrag006 rrag007 rrag008 rrag013 rrag015 rrag017 rrag023 rrag032 rrag034 rrag035 rrag039 rrag044 rrag046 rrag049 rrag051 rrag057 rrag058 rrag091 rrag093 rrag110 rrag111 rrag112 rrag115 rrag127 rrag128 rrag132 rrag141 rrag175 rrag206".split()

def parse_value(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return "", start
    if text[start] == "{":
        depth = 1; index = start + 1
        while index < len(text) and depth:
            if text[index] == "{": depth += 1
            elif text[index] == "}": depth -= 1
            index += 1
        return text[start+1:index-1], index
    if text[start] == '"':
        index = start + 1
        while index < len(text):
            if text[index] == '"' and text[index-1] != "\\":
                return text[start+1:index], index+1
            index += 1
    index = start
    while index < len(text) and text[index] not in ",\n":
        index += 1
    return text[start:index].strip(), index

def parse_bib(path):
    text = open(path, encoding="utf-8").read()
    entries = {}
    cursor = 0
    while True:
        m = re.search(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", text[cursor:])
        if not m: break
        body_start = cursor + m.end()
        depth = 1; index = body_start
        while index < len(text) and depth:
            if text[index] == "{": depth += 1
            elif text[index] == "}": depth -= 1
            index += 1
        body = text[body_start:index-1]
        fields = {}; fc = 0
        while True:
            fm = re.search(r"(?m)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[fc:])
            if not fm: break
            name = fm.group(1).lower()
            vs = fc + fm.end()
            value, ve = parse_value(body, vs)
            fields[name] = re.sub(r"\s+", " ", value).strip()
            fc = ve
        entries[m.group(2)] = {"type": m.group(1).lower(), "fields": fields}
        cursor = index
    return entries

entries = parse_bib("auto_references.bib")
out = {}
for k in KEYS:
    if k not in entries:
        print("MISSING", k); continue
    e = entries[k]
    out[k] = e
    print(f"=== {k} [{e['type']}] ===")
    print("  title :", e['fields'].get('title',''))
    print("  author:", e['fields'].get('author',''))
    print("  year  :", e['fields'].get('year',''))
    print("  url   :", e['fields'].get('url',''))
    print()

json.dump(out, open("supplement/bib_upgrade/targets.json","w"), indent=2)
print("Extracted", len(out), "entries")
