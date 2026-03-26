"""
cleaner.py — 第 4 步：大模型数据清洗与结构化

作用：读取 Whisper 输出的生肉 JSON，分段调用大模型（OpenAI 接口兼容），
      输出干净的、结构化的 Markdown 格式播客笔记。

使用方法：
  python cleaner.py
  
环境变量：在项目根目录创建 .env 文件，或直接在此处填写：
  LLM_API_KEY=your_key
  LLM_BASE_URL=https://api.deepseek.com/v1   # DeepSeek / OpenAI 等兼容接口
  LLM_MODEL=deepseek-chat
"""

import os
import json
import sqlite3
from pathlib import Path
from openai import OpenAI

# ==== 配置区 ====
BASE_DIR = Path(__file__).parent
TRANSCRIPT_DIR = BASE_DIR / "transcripts"
CLEANED_DIR = BASE_DIR / "cleaned"
DB_PATH = BASE_DIR / "podcast.db"

CLEANED_DIR.mkdir(exist_ok=True)

# 从环境变量读取（或在此直接填写）
LLM_API_KEY = os.getenv("LLM_API_KEY", "YOUR_API_KEY_HERE")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# 每次发给大模型的最大字符数（避免超出上下文限制）
MAX_CHUNK_CHARS = 6000

SYSTEM_PROMPT = """你是一位专业的播客内容编辑助理。
我将给你一段播客的自动语音识别（ASR）原始文本，请你完成以下三项任务：

1. 【去水与修正】消除口头语（"那个"、"就是说"、"嗯"等），修正同音字和明显的识别错误
2. 【段落重构】根据语义内容重新组织段落，使文本逻辑清晰、易于阅读，使用 Markdown 格式
3. 【提取摘要】在文章最后添加一个"## 本段核心要点"章节，用 3-5 条简洁的要点列出核心内容

只输出处理后的 Markdown 文本，不要输出任何其他解释。"""

def chunk_transcript(transcript_json_path: Path, max_chars=MAX_CHUNK_CHARS):
    """将 Whisper 输出的 JSON 转成文本，并按字数分块"""
    with open(transcript_json_path, encoding="utf-8") as f:
        data = json.load(f)
    
    full_text = data.get("text", "")
    
    # 分块
    chunks = []
    while len(full_text) > max_chars:
        # 在 max_chars 附近找到最近的句标点来切分，避免割断句子
        cut_at = max_chars
        for punct in ['。', '！', '？', '\n']:
            idx = full_text.rfind(punct, max_chars // 2, max_chars)
            if idx > 0:
                cut_at = idx + 1
                break
        chunks.append(full_text[:cut_at].strip())
        full_text = full_text[cut_at:]
    if full_text.strip():
        chunks.append(full_text.strip())
    
    return chunks

def clean_with_llm(text_chunk: str) -> str:
    """将单个文本块发给大模型清洗"""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text_chunk}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def process_pending_cleaning():
    """扫描数据库中 TRANSCRIBED 状态的记录，执行大模型清洗"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, title FROM episodes WHERE status = 'TRANSCRIBED'")
    pending_records = cursor.fetchall()
    
    if not pending_records:
        print("没有等待清洗的转录文件。请先运行 transcriber.py")
        return
    
    for epid, title in pending_records:
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        transcript_json_path = TRANSCRIPT_DIR / f"{safe_title}.json"
        cleaned_md_path = CLEANED_DIR / f"{safe_title}.md"
        
        if not transcript_json_path.exists():
            print(f"找不到转录文件: {transcript_json_path}，跳过")
            continue
        
        print(f"开始清洗: {title}")
        chunks = chunk_transcript(transcript_json_path)
        print(f"共分为 {len(chunks)} 个文本块，开始逐块调用大模型...")
        
        cleaned_parts = []
        for i, chunk in enumerate(chunks):
            print(f"  正在处理第 {i+1}/{len(chunks)} 块...")
            cleaned_text = clean_with_llm(chunk)
            cleaned_parts.append(cleaned_text)
        
        # 合并所有清洗后的文本并写入 Markdown 文件
        full_cleaned_md = f"# {title}\n\n" + "\n\n---\n\n".join(cleaned_parts)
        with open(cleaned_md_path, "w", encoding="utf-8") as f:
            f.write(full_cleaned_md)
        
        # 更新数据库状态
        cursor.execute("UPDATE episodes SET status = 'CLEANED' WHERE id = ?", (epid,))
        conn.commit()
        print(f"清洗完成，已保存至: {cleaned_md_path}\n")

if __name__ == "__main__":
    process_pending_cleaning()
