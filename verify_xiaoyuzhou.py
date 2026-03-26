import requests
import json
import re

url = "https://www.xiaoyuzhoufm.com/podcast/5e280faf418a84a0461fa1eb"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    print(f"Fetching {url}...")
    res = requests.get(url, headers=headers, timeout=10)
    html = res.text
    print(f"HTML length: {len(html)}")
    
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        # print top level keys
        print(f"__NEXT_DATA__ keys: {data.keys()}")
        
        # let's write it to a file to inspect structure
        with open('next_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Data dumped to next_data.json")
    else:
        print("next_data not found in HTML.")
        
except Exception as e:
    print(f"Error: {e}")
