"""
vectorizer.py — 第 5 步：向量化与知识库挂载

作用：读取 cleaned/ 目录下的结构化 Markdown 笔记，
      将其切块后存入本地 ChromaDB 向量数据库，供 Agent 检索使用。

使用方法：
  python vectorizer.py

依赖安装：
  pip install chromadb langchain langchain-openai langchain-chroma
  
环境变量（与 cleaner.py 共用）：
  LLM_API_KEY=your_key
  LLM_BASE_URL=https://api.deepseek.com/v1
"""

import os
import sqlite3
from pathlib import Path
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document

# ==== 配置区 ====
BASE_DIR = Path(__file__).parent
CLEANED_DIR = BASE_DIR / "cleaned"
DB_PATH = BASE_DIR / "podcast.db"
CHROMA_DB_PATH = str(BASE_DIR / "chroma_db")

# Embedding 服务（使用与清洗相同的 OpenAI 兼容接口）
LLM_API_KEY = os.getenv("LLM_API_KEY", "YOUR_API_KEY_HERE")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")

# ChromaDB 集合名称
COLLECTION_NAME = "podcast_knowledge_base"

def get_embeddings():
    """获取 Embedding 模型实例"""
    return OpenAIEmbeddings(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model="text-embedding-3-small"  # 根据你的 API 提供商修改
    )

def load_and_chunk_markdown(md_path: Path, podcast_name: str, episode_title: str):
    """读取 Markdown 文件并切块成 LangChain Document 列表"""
    with open(md_path, encoding="utf-8") as f:
        content = f.read()
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,    # 每块 500 字（中文）
        chunk_overlap=50,  # 块间重叠 50 字，保证上下文连贯
        separators=["\n## ", "\n\n", "\n", "。", "！", "？"]  # 优先按标题切块
    )
    chunks = splitter.split_text(content)
    
    # 包装成 LangChain Document，携带元数据
    return [
        Document(
            page_content=chunk,
            metadata={
                "source": str(md_path),
                "podcast": podcast_name,
                "episode": episode_title
            }
        )
        for chunk in chunks
    ]

def vectorize_cleaned_episodes():
    """将所有 CLEANED 状态的节目向量化并写入 ChromaDB"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, podcast_name, title FROM episodes WHERE status = 'CLEANED'")
    pending_records = cursor.fetchall()
    
    if not pending_records:
        print("没有等待向量化的清洗文件。请先运行 cleaner.py")
        return
    
    embeddings = get_embeddings()
    vectordb = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_PATH
    )
    
    for epid, podcast_name, title in pending_records:
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        cleaned_md_path = CLEANED_DIR / f"{safe_title}.md"
        
        if not cleaned_md_path.exists():
            print(f"找不到清洗文件: {cleaned_md_path}，跳过")
            continue
        
        print(f"正在向量化: {title}")
        docs = load_and_chunk_markdown(cleaned_md_path, podcast_name, title)
        print(f"  共切成 {len(docs)} 个文本块，写入 ChromaDB...")
        
        vectordb.add_documents(docs)
        
        cursor.execute("UPDATE episodes SET status = 'VECTORIZED' WHERE id = ?", (epid,))
        conn.commit()
        print(f"  向量化完成！")
    
    print(f"\n所有内容已写入知识库: {CHROMA_DB_PATH}")
    print("现在可以使用以下代码查询：")
    print("""
  from langchain_chroma import Chroma
  from langchain_openai import OpenAIEmbeddings
  db = Chroma(collection_name="podcast_knowledge_base", persist_directory="chroma_db", embedding_function=...)
  results = db.similarity_search("你的问题", k=4)
""")

if __name__ == "__main__":
    vectorize_cleaned_episodes()
