(() => {
  "use strict";

  if (window.top !== window.self || document.getElementById("videoflow-lms-helper")) {
    return;
  }

  const button = document.createElement("button");
  button.id = "videoflow-lms-helper";
  button.textContent = "复制到 VideoFlow";
  Object.assign(button.style, {
    position: "fixed",
    right: "24px",
    bottom: "24px",
    zIndex: "2147483647",
    padding: "11px 16px",
    border: "0",
    borderRadius: "8px",
    background: "#f05a00",
    color: "#fff",
    fontSize: "14px",
    fontWeight: "600",
    cursor: "pointer",
    boxShadow: "0 4px 16px rgba(0,0,0,.25)"
  });
  document.body.appendChild(button);

  const setState = (text, failed = false) => {
    button.textContent = text;
    button.style.background = failed ? "#b42318" : "#16803c";
    window.setTimeout(() => {
      button.textContent = "复制到 VideoFlow";
      button.style.background = "#f05a00";
      button.disabled = false;
    }, 4000);
  };

  const replayCodeFrom = (activity) => {
    return activity.replay_code
      || activity.lesson_resource?.properties?.replay_code
      || activity.data?.external_live_detail?.replay_id
      || null;
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "正在获取短期任务…";
    try {
      const match = window.location.hash.match(/^#\/(\d+)/);
      if (!match) {
        throw new Error("当前地址中没有学习活动编号");
      }
      const activityId = Number(match[1]);
      const [activityResponse, playerResponse] = await Promise.all([
        fetch(`/api/activities/${activityId}`, { credentials: "include" }),
        fetch(`/api/lessons/${activityId}/player-url?from_page=course`, { credentials: "include" })
      ]);
      if (!activityResponse.ok || !playerResponse.ok) {
        throw new Error("LMS 未授权读取该回放，请确认已登录且可以播放");
      }
      const activity = await activityResponse.json();
      const player = await playerResponse.json();
      const replayCode = replayCodeFrom(activity);
      if (!replayCode || !player.url) {
        throw new Error("该活动没有可用的课程回放信息");
      }
      const payload = JSON.stringify({
        videoflow: 1,
        activity_id: activityId,
        replay_code: String(replayCode),
        player_url: String(player.url),
        title: String(activity.title || `lms-activity-${activityId}`)
      });
      await navigator.clipboard.writeText(payload);
      setState("已复制，请粘贴到 VideoFlow");
    } catch (error) {
      setState(`失败：${error?.message || "未知错误"}`, true);
    }
  });
})();
