import re
bbl=open('main_survey.bbl').read()
items=re.split(r'(?=\\bibitem)', bbl)
d={}
for it in items:
    m=re.search(r'\{(rrag\d+)\}', it[:200])
    if m: d[m.group(1)]=re.sub(r'\s+',' ',it).strip()
keys=['rrag006','rrag015','rrag023','rrag032','rrag034','rrag035','rrag039','rrag046','rrag051','rrag057','rrag058','rrag091','rrag110','rrag111','rrag132','rrag141','rrag206','rrag017']
for k in keys:
    it=d.get(k,'')
    vm=re.search(r'In \\emph\{([^}]*)\}', it)
    ym=re.search(r'\b(20\d\d[a-z]?)\.', it)
    venue = vm.group(1) if vm else "(NONE)"
    year = ym.group(1) if ym else "?"
    print("%-8s year~=%-6s venue=%s" % (k, year, venue))
