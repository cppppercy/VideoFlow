"""解析由本地浏览器助手生成的西交 LMS 短期回放任务。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import ipaddress
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit


_RMS_BASE_URL = "https://rms-v5.xjtu.edu.cn"
_REPLAY_CODE = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_MAX_PAYLOAD_LENGTH = 16_384


class XjtuLmsError(RuntimeError):
    """LMS 短期任务无效、过期或当前用户无访问权限。"""


@dataclass(frozen=True, slots=True)
class XjtuReplay:
    activity_id: int
    title: str
    stream_url: str
    label: str


JsonGetter = Callable[..., object]


def _default_get_json(url: str, **kwargs: Any) -> object:
    try:
        import httpx
    except ImportError as exc:
        raise XjtuLmsError("缺少 httpx 依赖，请重新安装 VideoFlow。") from exc
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        raise XjtuLmsError("课程回放服务请求失败；任务可能已过期，请重新复制。") from exc


def parse_lms_helper_payload(raw_payload: str) -> tuple[int, str, str, str]:
    """返回 activity_id、replay_code、播放器 token 和安全标题。"""
    text = raw_payload.strip()
    if not text:
        raise XjtuLmsError("请先使用 VideoFlow LMS 助手复制课程任务。")
    if len(text) > _MAX_PAYLOAD_LENGTH:
        raise XjtuLmsError("课程任务内容异常过长，已拒绝处理。")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise XjtuLmsError("课程任务格式无效，请回 LMS 页面重新复制。") from exc
    if not isinstance(payload, Mapping) or payload.get("videoflow") != 1:
        raise XjtuLmsError("这不是 VideoFlow LMS 助手生成的任务。")

    activity_id = payload.get("activity_id")
    if not isinstance(activity_id, int) or activity_id <= 0:
        raise XjtuLmsError("课程活动编号无效。")
    replay_code = str(payload.get("replay_code") or "").strip()
    if not _REPLAY_CODE.fullmatch(replay_code):
        raise XjtuLmsError("该活动没有可识别的课程回放编号。")
    player_url = str(payload.get("player_url") or "").strip()
    parts = urlsplit(player_url)
    hostname = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or not hostname.endswith(".xjtu.edu.cn")
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
    ):
        raise XjtuLmsError("课程播放器地址不属于受支持的西交 HTTPS 域名。")
    tokens = parse_qs(parts.query).get("token", [])
    if len(tokens) != 1 or not tokens[0] or len(tokens[0]) > 8192:
        raise XjtuLmsError("课程播放器任务缺少有效的短期 token。")
    title = str(payload.get("title") or f"lms-activity-{activity_id}").strip()
    return activity_id, replay_code, tokens[0], title[:160]


def resolve_lms_replay(raw_payload: str, *, get_json: JsonGetter = _default_get_json) -> XjtuReplay:
    """用短期播放器 token 换取当前账号获准访问的播放流。"""
    activity_id, replay_code, player_token, title = parse_lms_helper_payload(raw_payload)
    exchange = get_json(
        f"{_RMS_BASE_URL}/api/v1/auth/embed-token",
        params={"token": player_token},
    )
    if not isinstance(exchange, Mapping):
        raise XjtuLmsError("课程回放服务返回了无法识别的授权结果。")
    rms_token = exchange.get("data")
    if not isinstance(rms_token, str) or not rms_token:
        raise XjtuLmsError("课程短期授权已失效，请回 LMS 页面重新复制。")

    response = get_json(
        f"{_RMS_BASE_URL}/api/embed/lesson-activities/captures/{replay_code}",
        params={"lesson_activity_id": activity_id},
        headers={"Authorization": f"Bearer {rms_token}"},
    )
    videos = _extract_video_list(response)
    selected = _select_audio_video(videos)
    stream_url = str(selected.get("play_url") or "").strip()
    _validate_stream_url(stream_url)
    return XjtuReplay(
        activity_id=activity_id,
        title=title,
        stream_url=stream_url,
        label=str(selected.get("label") or "课程回放"),
    )


def _extract_video_list(response: object) -> list[Mapping[str, Any]]:
    if not isinstance(response, Mapping):
        raise XjtuLmsError("课程回放列表格式无法识别。")
    error = response.get("error")
    if isinstance(error, Mapping) and error.get("code") not in (None, 0):
        raise XjtuLmsError("当前账号无权访问该课程回放，或回放尚未生成。")
    candidates = response.get("lesson_videos")
    if not isinstance(candidates, list):
        nested = response.get("data")
        candidates = nested.get("lesson_videos") if isinstance(nested, Mapping) else None
    if not isinstance(candidates, list):
        raise XjtuLmsError("该课程未返回可用回放视频。")
    return [item for item in candidates if isinstance(item, Mapping)]


def _select_audio_video(videos: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    playable = [item for item in videos if isinstance(item.get("play_url"), str) and item.get("play_url")]
    if not playable:
        raise XjtuLmsError("该课程回放没有可用播放地址。")
    return sorted(
        playable,
        key=lambda item: (bool(item.get("is_best_audio")), not bool(item.get("mute"))),
        reverse=True,
    )[0]


def _validate_stream_url(url: str) -> None:
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    if parts.scheme != "https" or not hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise XjtuLmsError("课程回放服务返回了不安全的播放地址。")
    if hostname == "localhost" or hostname.endswith(".local"):
        raise XjtuLmsError("课程播放地址不能指向本机或局域网。")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise XjtuLmsError("课程播放地址不能指向私有或保留网络。")
