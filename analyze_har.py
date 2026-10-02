import json

har = json.load(open(r'C:\Users\PC\Downloads\ecrew.airalgerie.dz.har', encoding='utf-8'))
for i, e in enumerate(har['log']['entries']):
    req = e['request']
    resp = e['response']
    url = req['url']
    if any(k in url.lower() for k in ['login', 'dashboard', 'homeindex', 'ecrew']):
        print(f"Entry {i}: {req['method']} {url} -> {resp['status']}")
        for h in req['headers']:
            if h['name'].lower() in ['cookie', 'ecrewheader', 'requestverificationtoken', 'referer', 'content-type', 'user-agent']:
                print(f"   REQ {h['name']}: {h['value'][:80]}")
        for h in resp['headers']:
            if h['name'].lower() in ['set-cookie', 'location']:
                print(f"   RESP {h['name']}: {h['value'][:80]}")
        if 'postData' in req:
            print(f"   POST: {req['postData']['text'][:120]}")
