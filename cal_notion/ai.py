"""AI 智慧分析模組 — 使用 Claude API 進行事件分類、時間洞察、週報生成。"""

import json
import logging
import os
from datetime import date, datetime

log = logging.getLogger(__name__)

# Lazy import to avoid hard dependency
_client = None


def _get_client():
    """Get or create Anthropic client."""
    global _client
    if _client is None:
        try:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY 未設定。請在 .env 中加入你的 API key。")
            _client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("請安裝 anthropic SDK: pip install anthropic")
    return _client


def _call_claude(prompt: str, max_tokens: int = 1024, model: str = "claude-haiku-4-5-20251001") -> str:
    """Call Claude API and return text response."""
    client = _get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── 1. AI Auto-Classification ─────────────────────────

def classify_event(summary: str, description: str = "", available_categories: list[str] | None = None) -> str:
    """Use AI to classify an event into a category based on its title and description.

    Args:
        summary: Event title
        description: Event description
        available_categories: List of available categories. Defaults to common ones.

    Returns:
        Category name string
    """
    categories = available_categories or ["工作", "生活", "一般", "籃球比賽", "專案"]

    prompt = f"""你是一個行事曆事件分類助手。根據事件標題和描述，將事件分類到最合適的類別。

可用類別: {', '.join(categories)}

事件標題: {summary}
{"事件描述: " + description if description else ""}

請只回覆一個類別名稱，不要加任何其他文字。"""

    try:
        result = _call_claude(prompt, max_tokens=50)
        result = result.strip()
        # Validate result is one of the categories
        if result in categories:
            return result
        # Try fuzzy match
        for cat in categories:
            if cat in result:
                return cat
        return categories[0]  # fallback
    except Exception as e:
        log.warning(f"AI 分類失敗，使用預設: {e}")
        return "一般"


def batch_classify_events(events: list[dict], available_categories: list[str] | None = None) -> dict[str, str]:
    """Classify multiple events in a single API call for efficiency.

    Args:
        events: List of dicts with 'uid' and 'summary' keys
        available_categories: Available category names

    Returns:
        Dict mapping uid -> category
    """
    categories = available_categories or ["工作", "生活", "一般", "籃球比賽", "專案"]

    if not events:
        return {}

    event_list = "\n".join(f"- [{e['uid']}] {e['summary']}" for e in events[:50])  # limit batch size

    prompt = f"""你是一個行事曆事件分類助手。根據事件標題，將每個事件分類到最合適的類別。

可用類別: {', '.join(categories)}

事件列表:
{event_list}

請用 JSON 格式回覆，格式為 {{"uid": "類別"}}。只回覆 JSON，不要加任何其他文字。"""

    try:
        result = _call_claude(prompt, max_tokens=2048)
        # Extract JSON from response
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(result)
    except Exception as e:
        log.warning(f"AI 批次分類失敗: {e}")
        return {}


# ── 2. AI Time Insights ───────────────────────────────

def generate_time_insights(analytics_data: dict) -> str:
    """Generate AI-powered insights from time analytics data.

    Args:
        analytics_data: Output from TimeAnalytics.weekly_summary() or monthly_summary()

    Returns:
        Markdown-formatted insights string
    """
    prompt = f"""你是一個時間管理顧問。根據以下行事曆數據，提供 3-5 條具體、可行的時間管理建議。

數據:
{json.dumps(analytics_data, ensure_ascii=False, indent=2)}

請用繁體中文回覆，格式：
1. 每條建議用 emoji 開頭
2. 先說觀察，再給建議
3. 具體且可行動
4. 保持簡潔（每條不超過 2 句）"""

    try:
        return _call_claude(prompt, max_tokens=1024, model="claude-sonnet-4-6")
    except Exception as e:
        log.warning(f"AI 時間洞察生成失敗: {e}")
        return "⚠️ 無法生成 AI 洞察，請確認 ANTHROPIC_API_KEY 設定正確。"


# ── 3. AI Weekly Summary ──────────────────────────────

def generate_weekly_report(
    events: list[dict],
    analytics_data: dict,
    week_start: str,
    week_end: str,
) -> str:
    """Generate a comprehensive AI weekly report.

    Args:
        events: List of event dicts with summary, start, end, calendar_name
        analytics_data: Output from TimeAnalytics.weekly_summary()
        week_start: ISO date string
        week_end: ISO date string

    Returns:
        Markdown-formatted weekly report
    """
    # Prepare event summary for the prompt
    event_lines = []
    for e in events[:100]:  # limit for token size
        event_lines.append(f"- {e.get('calendar_name', '?')} | {e.get('summary', '?')} | {e.get('start', '?')}")
    events_text = "\n".join(event_lines)

    prompt = f"""你是一個個人助理。根據以下行事曆資料，撰寫一份繁體中文的週報摘要。

期間: {week_start} ~ {week_end}

統計數據:
{json.dumps(analytics_data, ensure_ascii=False, indent=2)}

事件列表:
{events_text}

請產出以下格式的週報：

## 📅 本週摘要 ({week_start} ~ {week_end})

### 概覽
- 總事件數和時數的一句話摘要

### 各類別分析
- 列出每個類別的事件數和重點事件

### 時間洞察
- 2-3 條觀察和建議

### 下週建議
- 1-2 條基於本週模式的建議

保持簡潔專業，使用繁體中文。"""

    try:
        return _call_claude(prompt, max_tokens=2048, model="claude-sonnet-4-6")
    except Exception as e:
        log.warning(f"AI 週報生成失敗: {e}")
        return "⚠️ 無法生成 AI 週報，請確認 ANTHROPIC_API_KEY 設定正確。"


# ── 4. AI Duplicate Detection ─────────────────────────

def detect_duplicates(events: list[dict]) -> list[tuple[str, str, float]]:
    """Use AI to detect potentially duplicate events.

    Args:
        events: List of event dicts with uid, summary, start

    Returns:
        List of (uid1, uid2, confidence) tuples
    """
    if len(events) < 2:
        return []

    event_lines = []
    for e in events[:80]:
        event_lines.append(f"[{e['uid']}] {e['summary']} @ {e.get('start', '?')}")
    events_text = "\n".join(event_lines)

    prompt = f"""你是一個資料清理助手。檢查以下行事曆事件，找出可能重複的事件組合。

事件列表:
{events_text}

判斷標準：
1. 名稱相似（可能有錯字或大小寫差異）
2. 時間相同或重疊
3. 看起來是同一件事

請用 JSON 格式回覆，格式為:
[{{"uid1": "...", "uid2": "...", "confidence": 0.9, "reason": "..."}}]

如果沒有重複，回覆空陣列 []。只回覆 JSON。"""

    try:
        result = _call_claude(prompt, max_tokens=2048)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        duplicates = json.loads(result)
        return [(d["uid1"], d["uid2"], d.get("confidence", 0.8)) for d in duplicates]
    except Exception as e:
        log.warning(f"AI 重複偵測失敗: {e}")
        return []


# ── 5. Meeting Cost Calculator ────────────────────────

def calculate_meeting_costs(
    events: list[dict],
    hourly_rate: float = 500.0,  # Default NTD 500/hr
) -> list[dict]:
    """Calculate the cost of meetings based on hourly rate.

    This is a simple calculation, not AI-powered.

    Args:
        events: List of event dicts with summary, start, end
        hourly_rate: Cost per hour in local currency

    Returns:
        List of dicts with event info and cost
    """
    results = []
    total_cost = 0.0

    for e in events:
        start_str = e.get("start", "")
        end_str = e.get("end", "")

        hours = 1.0  # default
        if start_str and end_str and "T" in start_str and "T" in end_str:
            try:
                start_dt = datetime.fromisoformat(start_str)
                end_dt = datetime.fromisoformat(end_str)
                hours = max(0, (end_dt - start_dt).total_seconds() / 3600)
            except (ValueError, TypeError):
                pass

        cost = round(hours * hourly_rate, 0)
        total_cost += cost
        results.append({
            "summary": e.get("summary", "?"),
            "hours": round(hours, 1),
            "cost": cost,
            "start": start_str,
        })

    # Sort by cost descending
    results.sort(key=lambda x: -x["cost"])

    return results
