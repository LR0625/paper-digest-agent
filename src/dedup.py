"""
去重模块 —— 基于 SQLite 记录已推送论文 ID。
提供线程安全的基本 CRUD 操作。
"""

import sqlite3
import os
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "seen_ids.db")


def _get_conn():
    """获取数据库连接（自动创建目录和表）。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_papers (
            arxiv_id TEXT PRIMARY KEY,
            title TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'daily'
        )
    """)
    conn.commit()
    return conn


def is_seen(arxiv_id: str) -> bool:
    """检查论文是否已处理过。"""
    conn = _get_conn()
    row = conn.execute("SELECT 1 FROM seen_papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    conn.close()
    return row is not None


def mark_seen(arxiv_id: str, title: str = "", source: str = "daily"):
    """标记论文为已处理。"""
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO seen_papers (arxiv_id, title, source) VALUES (?, ?, ?)",
        (arxiv_id, title, source)
    )
    conn.commit()
    conn.close()


def mark_batch_seen(papers: list[dict], source: str = "daily"):
    """批量标记论文为已处理。每项含 arxiv_id 和 title。"""
    conn = _get_conn()
    conn.executemany(
        "INSERT OR IGNORE INTO seen_papers (arxiv_id, title, source) VALUES (?, ?, ?)",
        [(p["arxiv_id"], p.get("title", ""), source) for p in papers]
    )
    conn.commit()
    conn.close()


def get_seen_ids() -> set[str]:
    """返回所有已处理的论文 ID 集合。"""
    conn = _get_conn()
    rows = conn.execute("SELECT arxiv_id FROM seen_papers").fetchall()
    conn.close()
    return {r[0] for r in rows}


def get_stats() -> dict:
    """返回去重统计信息。"""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM seen_papers").fetchone()[0]
    recent = conn.execute(
        "SELECT COUNT(*) FROM seen_papers WHERE seen_at >= date('now', '-7 days')"
    ).fetchone()[0]
    conn.close()
    return {"total_seen": total, "seen_last_7_days": recent}
