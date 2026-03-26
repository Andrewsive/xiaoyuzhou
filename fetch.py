import requests
import re
import json

url = 'https://www.xiaoyuzhoufm.com/podcast/5e280faf418a84a0461fa1eb'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'}

res = requests.get(url, headers=headers)
html = res.text

# Try to find episode URLs using raw regex (looking for eids)
eids = re.findall(r'"eid":"([a-f0-9]{24})"', html)
# Try also looking for '/episode/' strings
ep_links = re.findall(r'/episode/([a-f0-9]{24})', html)

eids = list(set(eids + ep_links))
print(f"Found {len(eids)} unique episodes in HTML!")

if eids:
    print("First 5:", eids[:5])
else:
    print("No episodes found. The HTML might not contain them.")
    print("HTML excerpt:", html[:1000])
