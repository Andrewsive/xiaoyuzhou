import os
import json
import urllib.request
import urllib.parse
import feedparser
import requests
import sqlite3
from pathlib import Path

# 设置存储路径
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio"
DB_PATH = BASE_DIR / "podcast.db"
AUDIO_DIR.mkdir(exist_ok=True)

def init_db():
    """初始化 SQLite 数据库，用于记录已处理的节目，实现增量更新"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            podcast_name TEXT,
            title TEXT,
            published TEXT,
            audio_url TEXT UNIQUE,
            local_path TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    return conn

def get_official_rss_by_name(podcast_name):
    """通过 Apple Podcasts API 搜索播客名称，获取官方 RSS 源"""
    print(f"[{podcast_name}] 正在获取官方 RSS 源...")
    term = urllib.parse.quote(podcast_name)
    url = f"https://itunes.apple.com/search?term={term}&entity=podcast&limit=1"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        data = json.loads(res)
        if data['resultCount'] > 0:
            return data['results'][0].get('feedUrl')
    except Exception as e:
        print(f"获取 RSS 失败: {e}")
    return None

def fetch_and_download(podcast_name, limit=5):
    """拉取 RSS 源并下载最新的未处理单集"""
    conn = init_db()
    cursor = conn.cursor()
    
    rss_url = get_official_rss_by_name(podcast_name)
    if not rss_url:
        print(f"未能找到 {podcast_name} 的 RSS 源。")
        return
        
    print(f"[{podcast_name}] 成功获取 RSS 源: {rss_url}")
    feed = feedparser.parse(rss_url)
    if feed.bozo and not feed.entries:
        print(f"解析 RSS 失败: {feed.bozo_exception}")
        return
        
    new_episodes = []
    
    for entry in feed.entries[:limit]:
        title = entry.title
        published = entry.published
        audio_url = ""
        
        if 'enclosures' in entry and len(entry.enclosures) > 0:
            audio_url = entry.enclosures[0].get('href', '')
            
        if not audio_url:
            continue
            
        # 检查是否已下载
        cursor.execute("SELECT id FROM episodes WHERE audio_url = ?", (audio_url,))
        if cursor.fetchone():
            print(f"跳过已处理: {title}")
            continue
            
        new_episodes.append({
            "title": title,
            "published": published,
            "audio_url": audio_url
        })
        
    for ep in reversed(new_episodes): # 从旧到新下载
        title = ep['title']
        audio_url = ep['audio_url']
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        filename = f"{safe_title}.mp3"
        local_path = AUDIO_DIR / filename
        
        print(f"开始下载: {title}")
        try:
            # 下载大文件，使用 stream
            with requests.get(audio_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            # 记录到数据库
            cursor.execute('''
                INSERT INTO episodes (podcast_name, title, published, audio_url, local_path, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (podcast_name, title, ep['published'], audio_url, str(local_path), 'DOWNLOADED'))
            conn.commit()
            print(f"下载成功: {local_path}")
            
        except Exception as e:
            print(f"下载失败 {title}: {e}")

if __name__ == "__main__":
    fetch_and_download("Talk三联", limit=2)
