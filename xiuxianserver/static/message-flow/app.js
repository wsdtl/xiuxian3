(function () {
  const config = window.MESSAGE_FLOW_CONFIG || {};
  const state = {
    records: new Map(),
    source: null,
    userLockedScroll: false,
    pendingAutoScroll: false,
    fontScale: 0,
  };

  const nodes = {
    statusBadge: document.getElementById("statusBadge"),
    flowList: document.getElementById("flowList"),
    jumpBottom: document.getElementById("jumpBottom"),
    fontSizeDown: document.getElementById("fontSizeDown"),
    fontSizeUp: document.getElementById("fontSizeUp"),
    fontSizeLabel: document.getElementById("fontSizeLabel"),
  };

  function init() {
    bindScrollSignals();
    bindJumpBottom();
    bindFontControls();
    applyFontScale();
    loadRecent().then(connectStream);
  }

  function bindFontControls() {
    if (nodes.fontSizeDown) {
      nodes.fontSizeDown.addEventListener("click", () => adjustFontScale(-1));
    }
    if (nodes.fontSizeUp) {
      nodes.fontSizeUp.addEventListener("click", () => adjustFontScale(1));
    }
  }

  function bindJumpBottom() {
    if (!nodes.jumpBottom) {
      return;
    }
    nodes.jumpBottom.addEventListener("click", () => {
      state.userLockedScroll = false;
      scheduleAutoScroll(true);
      nodes.flowList.focus?.();
    });
  }

  function bindScrollSignals() {
    const viewport = nodes.flowList;
    viewport.addEventListener("scroll", syncScrollLock, { passive: true });
    viewport.addEventListener("pointerdown", () => {
      state.userLockedScroll = true;
    });
    viewport.addEventListener("pointerup", () => {
      state.userLockedScroll = !isNearBottom();
      flushAutoScroll();
    });
    viewport.addEventListener("pointerleave", () => {
      flushAutoScroll();
    });
    viewport.addEventListener("touchstart", () => {
      state.userLockedScroll = true;
    }, { passive: true });
    viewport.addEventListener("touchend", () => {
      state.userLockedScroll = !isNearBottom();
      flushAutoScroll();
    }, { passive: true });
  }

  async function loadRecent() {
    setStatus("读取中", "is-idle");
    try {
      const response = await fetch(config.recentUrl || "/xiuxian/message-flow/api/recent?limit=160");
      if (!response.ok) {
        setStatus("读取失败", "is-bad");
        return;
      }
      const data = await response.json();
      (data.records || []).forEach(appendRecord);
      setStatus("等待实时", "is-warn");
      scheduleAutoScroll(true);
    } catch (_error) {
      setStatus("读取失败", "is-bad");
    }
  }

  function connectStream() {
    const streamUrl = config.streamUrl || "/xiuxian/message-flow/stream";
    state.source = new EventSource(streamUrl);

    state.source.onopen = () => setStatus("实时连接", "is-live");
    state.source.onerror = () => setStatus("重连中", "is-warn");
    state.source.onmessage = (event) => {
      try {
        appendRecord(JSON.parse(event.data));
        scheduleAutoScroll(false);
      } catch (_error) {
        setStatus("解析失败", "is-bad");
      }
    };
  }

  function appendRecord(record) {
    const flowId = String(record && record.flow_id ? record.flow_id : "");
    if (!flowId || state.records.has(flowId)) {
      return;
    }

    const direction = record.direction === "outgoing" ? "outgoing" : "incoming";
    const row = document.createElement("article");
    row.className = `flow-row ${direction}`;
    row.dataset.direction = direction;
    row.dataset.flowId = flowId;

    const stack = document.createElement("div");
    stack.className = "message-stack";

    const sender = document.createElement("div");
    sender.className = "sender";
    sender.textContent = record.sender_name || (direction === "outgoing" ? "修仙服务" : record.display_name || "未知");

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.appendChild(renderContent(record));

    stack.appendChild(sender);
    stack.appendChild(bubble);
    row.appendChild(stack);
    nodes.flowList.appendChild(row);
    state.records.set(flowId, { record, row });
    trimVisibleRecords();
    applyVisibility(row);
  }

  function renderContent(record) {
    const content = document.createElement("div");
    content.className = "content";
    content.innerHTML = record.content_html || escapeHtml(record.content || "");
    hardenLinks(content);
    return content;
  }

  function syncScrollLock() {
    state.userLockedScroll = !isNearBottom();
    if (!state.userLockedScroll) {
      flushAutoScroll();
    }
  }

  function scheduleAutoScroll(force) {
    if (!force && state.userLockedScroll) {
      state.pendingAutoScroll = true;
      return;
    }
    requestAnimationFrame(() => {
      if (force || !state.userLockedScroll) {
        nodes.flowList.scrollTop = nodes.flowList.scrollHeight;
        state.pendingAutoScroll = false;
      }
    });
  }

  function flushAutoScroll() {
    if (state.pendingAutoScroll && !state.userLockedScroll) {
      state.pendingAutoScroll = false;
      nodes.flowList.scrollTop = nodes.flowList.scrollHeight;
    }
  }

  function trimVisibleRecords() {
    const limit = Number(config.visibleLimit || 260);
    if (!Number.isFinite(limit) || limit < 50) {
      return;
    }
    while (state.records.size > limit) {
      const oldest = state.records.keys().next().value;
      if (!oldest) {
        break;
      }
      const entry = state.records.get(oldest);
      if (entry && entry.row && entry.row.parentNode) {
        entry.row.parentNode.removeChild(entry.row);
      }
      state.records.delete(oldest);
    }
  }

  function adjustFontScale(step) {
    state.fontScale = Math.max(-2, Math.min(2, state.fontScale + step));
    applyFontScale();
  }

  function applyFontScale() {
    const scaleMap = {
      "-2": 0.88,
      "-1": 0.94,
      "0": 1,
      "1": 1.06,
      "2": 1.12,
    };
    const labelMap = {
      "-2": "极小",
      "-1": "小",
      "0": "中",
      "1": "大",
      "2": "极大",
    };
    const scale = scaleMap[String(state.fontScale)] || 1;
    document.documentElement.style.setProperty("--message-font-scale", String(scale));
    if (nodes.fontSizeLabel) {
      nodes.fontSizeLabel.textContent = labelMap[String(state.fontScale)] || "中";
    }
  }

  function isNearBottom() {
    const el = nodes.flowList;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  function applyVisibility(row) {
    row.classList.remove("is-hidden");
  }

  function setStatus(text, className) {
    nodes.statusBadge.textContent = text;
    nodes.statusBadge.className = `status-badge ${className || "is-idle"}`;
  }

  function escapeHtml(text) {
    return String(text || "").replace(/[&<>"]/g, (char) => {
      if (char === "&") return "&amp;";
      if (char === "<") return "&lt;";
      if (char === ">") return "&gt;";
      return "&quot;";
    });
  }

  function hardenLinks(root) {
    root.querySelectorAll("a[href]").forEach((link) => {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    });
  }

  init();
}());
