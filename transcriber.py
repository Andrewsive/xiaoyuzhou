import os
import sqlite3
from pathlib import Path

# 将刚用 winget 安装的 ffmpeg 目录动态加入 PATH，防止因控制台未重启而找不到
os.environ["PATH"] += os.pathsep + r"C:\Users\yichen\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"

# 配置路径
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPT_DIR = BASE_DIR / "transcripts"
DB_PATH = BASE_DIR / "podcast.db"

TRANSCRIPT_DIR.mkdir(exist_ok=True)

def transcribe_audio_whisper(audio_path, output_json_path):
    """使用本地 Whisper 模型将音频转换为带时间戳的 JSON"""
    try:
        import whisper
    except ImportError:
        print("缺少 whisper 核心依赖。请运行: pip install openai-whisper")
        return False

    print(f"[Whisper] 正在加载模型 (small)... 请耐心等待，首次运行需下载约 500MB 权重文件")
    # 为了演示速度优先，使用 'small'。如需高精度中文，请改为 'large-v3'
    model = whisper.load_model("small")
    
    print(f"[Whisper] 开始转录音频: {audio_path}")
    result = model.transcribe(str(audio_path), language="zh", fp16=False)
    
    import json
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        
    print(f"[Whisper] 转录完成，已保存至: {output_json_path}")
    return True

def process_pending_transcriptions():
    """扫描数据库中状态为 DOWNLOADED 的记录，执行 ASR"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, title, local_path FROM episodes WHERE status = 'DOWNLOADED'")
    pending_records = cursor.fetchall()
    
    if not pending_records:
        print("🎉 没有需要转写的新节目！")
        return
        
    for record in pending_records:
        epid, title, local_path = record
        
        # 定义输出的转录文件名
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        output_json_path = TRANSCRIPT_DIR / f"{safe_title}.json"
        
        # 调用 ASR (在此演示本地 Whisper 逻辑)
        success = transcribe_audio_whisper(local_path, output_json_path)
        
        if success:
            # 更新状态
            cursor.execute("UPDATE episodes SET status = 'TRANSCRIBED' WHERE id = ?", (epid,))
            conn.commit()

if __name__ == "__main__":
    process_pending_transcriptions()
