import urllib.request
import urllib.parse
import json
import feedparser
import time

def get_official_rss_by_name(podcast_name):
    """
    通过 Apple Podcasts API 搜索播客名称，获取其官方 RSS 源
    这是目前最稳定且无需破解反爬的源数据获取途径
    """
    print(f"🔍 正在 Apple Podcasts 验证并搜索播客: 【{podcast_name}】 ...")
    term = urllib.parse.quote(podcast_name)
    url = f"https://itunes.apple.com/search?term={term}&entity=podcast&limit=1"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        data = json.loads(res)
        
        if data['resultCount'] > 0:
            podcast = data['results'][0]
            feed_url = podcast.get('feedUrl')
            if feed_url:
                print(f"✅ 成功找到匹配播客: {podcast.get('collectionName')}")
                print(f"🔗 官方 RSS 源: {feed_url}\n")
                return feed_url
    except Exception as e:
        print(f"❌ 搜索失败: {e}\n")
    
    print(f"❌ 未能找到 {podcast_name} 的官方 RSS 源\n")
    return None

def fetch_latest_episodes(rss_url, limit=3):
    """
    解析官方 RSS 源，获取最新的单集信息（含底层音频链接）
    """
    print(f"⏳ 正在拉取最新的播客 RSS 数据...")
    feed = feedparser.parse(rss_url)
    
    if feed.bozo and not feed.entries:
        print(f"❌ 解析 RSS 失败: {feed.bozo_exception}")
        return []
        
    print(f"✅ 成功加载 RSS 频道: 【{feed.feed.title}】\n")
    print("-" * 50)
    
    episodes = []
    for i, entry in enumerate(feed.entries[:limit]):
        title = entry.title
        published_time = entry.published
        
        # 提取底层音频直链 (Enclosure)
        audio_url = ""
        if 'enclosures' in entry and len(entry.enclosures) > 0:
            audio_url = entry.enclosures[0].get('href', '')
            
        if audio_url:
            episodes.append({
                "title": title,
                "published": published_time,
                "audio_url": audio_url
            })
            print(f"🎵 第 {i+1} 期: {title}")
            print(f"📅 发布: {published_time}")
            print(f"🔊 音频: {audio_url}\n")
        else:
            print(f"⚠️ 第 {i+1} 期 ({title}) 未找到音频链接\n")
            
    return episodes

if __name__ == "__main__":
    PODCAST_NAME = "Talk三联" # 想要提炼的播客名称
    
    # 1. 动态搜索获取官方无限制的 RSS 源
    rss_url = get_official_rss_by_name(PODCAST_NAME)
    
    # 2. 从官方源解析最新的单集数据
    if rss_url:
        episodes_data = fetch_latest_episodes(rss_url, limit=5)
        
        print("-" * 50)
        print(f"🎉 批量抓取完成！成功稳定拿到 {len(episodes_data)} 个首发音频源。")
        print("💡 这些数据现已可以直接对接「Python 下载脚本」，进行纯净的「增量入库与异步 ASR 转录」流程！")