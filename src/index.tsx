// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="./qwenpaw-host.d.ts" />

// ============================================================================
// Ask-User Plugin — Frontend (v6)
//
// Uses push notifications + fallback polling to detect pending questions.
// - Primary: push notification via /api/console/push-messages (near-instant)
// - Fallback: poll /api/ask-user/pending every 10s
// ============================================================================

const { React, antd, getApiUrl } = window.QwenPaw.host;
const { Modal, Steps, Radio, Checkbox, Input, Button, Space, message } = antd;
const { TextArea } = Input;
const pluginId = "ask-user";
const FALLBACK_POLL_MS = 10000;

const rawFetch = window.fetch.bind(window);

// ── Types ──────────────────────────────────────────────────────────
interface QDef {
  type: "single" | "multi" | "text";
  title: string;
  options?: string[];
}

interface QA {
  type: string;
  value: string | string[];
  other: string;
}

interface PendingItem {
  request_id: string;
  session_id: string;
  agent_id: string;
  title: string;
  questions: QDef[];
  question_count: number;
  status: string;
}

// ── Main Component ────────────────────────────────────────────────

function AskUserApp() {
  const [pending, setPending] = React.useState<PendingItem | null>(null);
  const [step, setStep] = React.useState(0);
  const [answers, setAnswers] = React.useState<Record<string, QA>>({});
  const [finalOther, setFinalOther] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  const processedRef = React.useRef<string | null>(null);
  const sessionIdRef = React.useRef<string>("");
  const pendingRef = React.useRef<PendingItem | null>(null);

  // Keep ref in sync
  pendingRef.current = pending;
  if (pending) sessionIdRef.current = pending.session_id;

  // Show question modal
  const showQuestion = React.useCallback((item: PendingItem) => {
    setPending(item);
    setStep(0);
    setFinalOther("");
    const init: Record<string, QA> = {};
    (item.questions || []).forEach((q: QDef, i: number) => {
      init[`q${i}`] = {
        type: q.type,
        value: q.type === "multi" ? [] : "",
        other: "",
      };
    });
    setAnswers(init);
  }, []);

  // Poll & push listener
  React.useEffect(() => {
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setInterval>;

    async function poll() {
      try {
        // 1. Check push notifications (primary)
        if (sessionIdRef.current) {
          try {
            const pushUrl = `/api/console/push-messages?session_id=${encodeURIComponent(sessionIdRef.current)}`;
            const pushResp = await rawFetch(pushUrl, { signal: ctrl.signal });
            if (pushResp.ok) {
              const pushData = await pushResp.json();
              for (const msg of (pushData.messages || [])) {
                const text: string = msg.text || "";
                if (text.startsWith("ask_user_question:")) {
                  const rid = text.split(":")[1];
                  if (rid && processedRef.current !== rid) {
                    processedRef.current = rid;
                    // Fetch full question details
                    const detailResp = await rawFetch(
                      `/api/ask-user/details?request_id=${encodeURIComponent(rid)}`,
                      { signal: ctrl.signal }
                    );
                    if (detailResp.ok) {
                      const detail = await detailResp.json();
                      if (detail.status === "pending") showQuestion(detail);
                      return;
                    }
                  }
                }
              }
            }
          } catch (_) { /* optional */ }
        }

        // 2. Fallback: poll pending endpoint
        const resp = await rawFetch("/api/ask-user/pending", { signal: ctrl.signal });
        if (!resp.ok) return;
        const data = await resp.json();
        const item = (data.items || []).find((i: PendingItem) => i.status === "pending");
        if (!item) {
          if (pendingRef.current) setPending(null);
          return;
        }
        if (processedRef.current === item.request_id) return;
        processedRef.current = item.request_id;
        showQuestion(item);
      } catch (e: any) {
        if (e.name !== "AbortError") {
          console.warn("[ask-user] Poll:", e.message);
        }
      }
    }

    poll();
    timer = setInterval(poll, FALLBACK_POLL_MS);
    return () => { ctrl.abort(); clearInterval(timer); };
  }, [showQuestion]);

  if (!pending) return null;

  const { questions, title, request_id, session_id } = pending;
  const total = questions.length + 1;
  const isLast = step >= questions.length;
  const q = !isLast ? questions[step] : null;
  const key = `q${step}`;
  const ans = answers[key];
  const safe_ans = ans || { type: q?.type || "text", value: "", other: "" };

  const onChange = (a: QA) => {
    setAnswers((prev: any) => ({ ...prev, [key]: a }));
  };

  const apiDo = async (path: string, body: object): Promise<void> => {
    setLoading(true);
    try {
      const resp = await rawFetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as any).detail || `HTTP ${resp.status}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    try {
      await apiDo("/api/ask-user/answer", {
        request_id, session_id, answers, other: finalOther,
      });
      message.success("✓ 已提交答案");
      setPending(null);
      processedRef.current = null;
    } catch (e: any) {
      message.error(`提交失败: ${e.message}`);
    }
  };

  const handleSkip = async () => {
    try {
      await apiDo("/api/ask-user/skip", { request_id, session_id });
      message.info("已跳过问卷");
      setPending(null);
      processedRef.current = null;
    } catch (e: any) {
      message.error(`跳过失败: ${e.message}`);
    }
  };

  const handleClose = async () => {
    try {
      await apiDo("/api/ask-user/skip", { request_id, session_id });
    } catch (_) { /* ignore */ }
    setPending(null);
    processedRef.current = null;
    message.info("问卷已跳过");
  };

  // ── Render ──────────────────────────────────────────────────────

  if (questions.length === 0) {
    return (
      <Modal title="❓ 问卷" open={true} onCancel={handleClose}
        width={560} footer={null} maskClosable={false} keyboard={false} destroyOnClose>
        <div style={{ textAlign: "center", padding: 32, color: "#999" }}>加载中...</div>
      </Modal>
    );
  }

  return (
    <Modal
      title={<span><span style={{ marginRight: 8 }}>❓</span>{title || "问卷"}</span>}
      open={true} onCancel={handleClose}
      width={560} footer={null} maskClosable={false} keyboard={false} destroyOnClose
    >
      <Steps current={step} size="small" style={{ marginBottom: 16 }}
        items={[...questions.map(() => ({ title: "" })), { title: "其他" }]}
      />

      {/* Question pages */}
      {!isLast && q && (
        <div>
          <div style={{ fontSize: 13, color: "#999", marginBottom: 8 }}>
            {step + 1} / {questions.length}
          </div>
          <h3 style={{ margin: "0 0 16px 0", fontSize: 16 }}>{q.title}</h3>

          {q.type === "single" && q.options && (
            <Radio.Group value={safe_ans.value} onChange={(e: any) => onChange({ ...safe_ans, value: e.target.value })}
              style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {q.options.map((opt: string, i: number) => (
                <Radio key={i} value={opt}>{opt}</Radio>
              ))}
              <Radio value="__other__">其他{
                safe_ans.value === "__other__" && (
                  <Input size="small" placeholder="请填写" value={safe_ans.other}
                    onChange={(e: any) => onChange({ ...safe_ans, other: e.target.value })}
                    style={{ marginLeft: 8, width: 200 }} onClick={(e: any) => e.stopPropagation()} />
                )
              }</Radio>
            </Radio.Group>
          )}

          {q.type === "multi" && q.options && (
            <Checkbox.Group value={Array.isArray(safe_ans.value) ? safe_ans.value : []}
              onChange={(vals: any) => {
                const hasOther = vals.includes("__other__");
                onChange({ ...safe_ans, value: vals, other: hasOther ? safe_ans.other : "" });
              }}
              style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {q.options.map((opt: string, i: number) => (
                <Checkbox key={i} value={opt}>{opt}</Checkbox>
              ))}
              <Checkbox value="__other__">其他{
                Array.isArray(safe_ans.value) && safe_ans.value.includes("__other__") && (
                  <Input size="small" placeholder="请填写" value={safe_ans.other}
                    onChange={(e: any) => onChange({ ...safe_ans, other: e.target.value })}
                    style={{ marginLeft: 8, width: 200 }} onClick={(e: any) => e.stopPropagation()} />
                )
              }</Checkbox>
            </Checkbox.Group>
          )}

          {q.type === "text" && (
            <TextArea rows={4} placeholder="请输入..."
              value={typeof safe_ans.value === "string" ? safe_ans.value : ""}
              onChange={(e: any) => onChange({ ...safe_ans, value: e.target.value, other: "" })} />
          )}

          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 20 }}>
            <Button disabled={step === 0} onClick={() => setStep((s) => s - 1)}>上一步</Button>
            <Button type="primary" onClick={() => setStep((s) => s + 1)}>下一步</Button>
          </div>
        </div>
      )}

      {/* Final "其他" page */}
      {isLast && (
        <div>
          <div style={{ fontSize: 13, color: "#999", marginBottom: 8 }}>
            {step + 1} / {total}
          </div>
          <h3 style={{ margin: "0 0 12px 0", fontSize: 16 }}>其他意见</h3>
          <TextArea rows={3} placeholder="补充意见（可选）" value={finalOther}
            onChange={(e: any) => setFinalOther(e.target.value)} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
            <Button onClick={() => setStep((s) => s - 1)}>上一步</Button>
            <Space>
              <Button danger onClick={handleSkip} loading={loading}>跳过</Button>
              <Button type="primary" onClick={handleSubmit} loading={loading}>提交</Button>
            </Space>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ── Mount ──────────────────────────────────────────────────────────

window.QwenPaw.slot.fill(
  pluginId, "overlay.global",
  () => React.createElement(AskUserApp),
  { id: `${pluginId}.overlay` }
);

console.log("[ask-user] Plugin ready (v6 - push+poll)");
