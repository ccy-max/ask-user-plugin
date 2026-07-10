const { React: t, antd: X, getApiUrl: se } = window.QwenPaw.host, { Modal: Q, Steps: Y, Radio: x, Checkbox: A, Input: R, Button: m, Space: Z, message: h } = X, { TextArea: G } = R, M = "ask-user", ee = 1e4, v = window.fetch.bind(window);
function te() {
  const [u, p] = t.useState(null), [o, g] = t.useState(0), [P, L] = t.useState({}), [O, $] = t.useState(""), [j, q] = t.useState(!1), i = t.useRef(null), E = t.useRef(""), z = t.useRef(null);
  z.current = u, u && (E.current = u.session_id);
  const _ = t.useCallback((e) => {
    p(e), g(0), $("");
    const a = {};
    (e.questions || []).forEach((l, r) => {
      a[`q${r}`] = {
        type: l.type,
        value: l.type === "multi" ? [] : "",
        other: ""
      };
    }), L(a);
  }, []);
  if (t.useEffect(() => {
    const e = new AbortController();
    let a;
    async function l() {
      try {
        if (E.current)
          try {
            const f = `/api/console/push-messages?session_id=${encodeURIComponent(E.current)}`, B = await v(f, { signal: e.signal });
            if (B.ok) {
              const W = await B.json();
              for (const V of W.messages || []) {
                const U = V.text || "";
                if (U.startsWith("ask_user_question:")) {
                  const w = U.split(":")[1];
                  if (w && i.current !== w) {
                    i.current = w;
                    const D = await v(
                      `/api/ask-user/details?request_id=${encodeURIComponent(w)}`,
                      { signal: e.signal }
                    );
                    if (D.ok) {
                      const F = await D.json();
                      F.status === "pending" && _(F);
                      return;
                    }
                  }
                }
              }
            }
          } catch {
          }
        const r = await v("/api/ask-user/pending", { signal: e.signal });
        if (!r.ok) return;
        const y = ((await r.json()).items || []).find((f) => f.status === "pending");
        if (!y) {
          z.current && p(null);
          return;
        }
        if (i.current === y.request_id) return;
        i.current = y.request_id, _(y);
      } catch (r) {
        r.name !== "AbortError" && console.warn("[ask-user] Poll:", r.message);
      }
    }
    return l(), a = setInterval(l, ee), () => {
      e.abort(), clearInterval(a);
    };
  }, [_]), !u) return null;
  const { questions: c, title: H, request_id: k, session_id: C } = u, J = c.length + 1, S = o >= c.length, s = S ? null : c[o], I = `q${o}`, n = P[I] || { type: (s == null ? void 0 : s.type) || "text", value: "", other: "" }, d = (e) => {
    L((a) => ({ ...a, [I]: e }));
  }, b = async (e, a) => {
    q(!0);
    try {
      const l = await v(e, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(a)
      });
      if (!l.ok) {
        const r = await l.json().catch(() => ({}));
        throw new Error(r.detail || `HTTP ${l.status}`);
      }
    } finally {
      q(!1);
    }
  }, K = async () => {
    try {
      await b("/api/ask-user/answer", {
        request_id: k,
        session_id: C,
        answers: P,
        other: O
      }), h.success("✓ 已提交答案"), p(null), i.current = null;
    } catch (e) {
      h.error(`提交失败: ${e.message}`);
    }
  }, N = async () => {
    try {
      await b("/api/ask-user/skip", { request_id: k, session_id: C }), h.info("已跳过问卷"), p(null), i.current = null;
    } catch (e) {
      h.error(`跳过失败: ${e.message}`);
    }
  }, T = async () => {
    try {
      await b("/api/ask-user/skip", { request_id: k, session_id: C });
    } catch {
    }
    p(null), i.current = null, h.info("问卷已跳过");
  };
  return c.length === 0 ? /* @__PURE__ */ t.createElement(
    Q,
    {
      title: "❓ 问卷",
      open: !0,
      onCancel: T,
      width: 560,
      footer: null,
      maskClosable: !1,
      keyboard: !1,
      destroyOnClose: !0
    },
    /* @__PURE__ */ t.createElement("div", { style: { textAlign: "center", padding: 32, color: "#999" } }, "加载中...")
  ) : /* @__PURE__ */ t.createElement(
    Q,
    {
      title: /* @__PURE__ */ t.createElement("span", null, /* @__PURE__ */ t.createElement("span", { style: { marginRight: 8 } }, "❓"), H || "问卷"),
      open: !0,
      onCancel: T,
      width: 560,
      footer: null,
      maskClosable: !1,
      keyboard: !1,
      destroyOnClose: !0
    },
    /* @__PURE__ */ t.createElement(
      Y,
      {
        current: o,
        size: "small",
        style: { marginBottom: 16 },
        items: [...c.map(() => ({ title: "" })), { title: "其他" }]
      }
    ),
    !S && s && /* @__PURE__ */ t.createElement("div", null, /* @__PURE__ */ t.createElement("div", { style: { fontSize: 13, color: "#999", marginBottom: 8 } }, o + 1, " / ", c.length), /* @__PURE__ */ t.createElement("h3", { style: { margin: "0 0 16px 0", fontSize: 16 } }, s.title), s.type === "single" && s.options && /* @__PURE__ */ t.createElement(
      x.Group,
      {
        value: n.value,
        onChange: (e) => d({ ...n, value: e.target.value }),
        style: { display: "flex", flexDirection: "column", gap: 10 }
      },
      s.options.map((e, a) => /* @__PURE__ */ t.createElement(x, { key: a, value: e }, e)),
      /* @__PURE__ */ t.createElement(x, { value: "__other__" }, "其他", n.value === "__other__" && /* @__PURE__ */ t.createElement(
        R,
        {
          size: "small",
          placeholder: "请填写",
          value: n.other,
          onChange: (e) => d({ ...n, other: e.target.value }),
          style: { marginLeft: 8, width: 200 },
          onClick: (e) => e.stopPropagation()
        }
      ))
    ), s.type === "multi" && s.options && /* @__PURE__ */ t.createElement(
      A.Group,
      {
        value: Array.isArray(n.value) ? n.value : [],
        onChange: (e) => {
          const a = e.includes("__other__");
          d({ ...n, value: e, other: a ? n.other : "" });
        },
        style: { display: "flex", flexDirection: "column", gap: 10 }
      },
      s.options.map((e, a) => /* @__PURE__ */ t.createElement(A, { key: a, value: e }, e)),
      /* @__PURE__ */ t.createElement(A, { value: "__other__" }, "其他", Array.isArray(n.value) && n.value.includes("__other__") && /* @__PURE__ */ t.createElement(
        R,
        {
          size: "small",
          placeholder: "请填写",
          value: n.other,
          onChange: (e) => d({ ...n, other: e.target.value }),
          style: { marginLeft: 8, width: 200 },
          onClick: (e) => e.stopPropagation()
        }
      ))
    ), s.type === "text" && /* @__PURE__ */ t.createElement(
      G,
      {
        rows: 4,
        placeholder: "请输入...",
        value: typeof n.value == "string" ? n.value : "",
        onChange: (e) => d({ ...n, value: e.target.value, other: "" })
      }
    ), /* @__PURE__ */ t.createElement("div", { style: { display: "flex", justifyContent: "space-between", marginTop: 20 } }, /* @__PURE__ */ t.createElement(m, { disabled: o === 0, onClick: () => g((e) => e - 1) }, "上一步"), /* @__PURE__ */ t.createElement(m, { type: "primary", onClick: () => g((e) => e + 1) }, "下一步"))),
    S && /* @__PURE__ */ t.createElement("div", null, /* @__PURE__ */ t.createElement("div", { style: { fontSize: 13, color: "#999", marginBottom: 8 } }, o + 1, " / ", J), /* @__PURE__ */ t.createElement("h3", { style: { margin: "0 0 12px 0", fontSize: 16 } }, "其他意见"), /* @__PURE__ */ t.createElement(
      G,
      {
        rows: 3,
        placeholder: "补充意见（可选）",
        value: O,
        onChange: (e) => $(e.target.value)
      }
    ), /* @__PURE__ */ t.createElement("div", { style: { display: "flex", justifyContent: "space-between", marginTop: 16 } }, /* @__PURE__ */ t.createElement(m, { onClick: () => g((e) => e - 1) }, "上一步"), /* @__PURE__ */ t.createElement(Z, null, /* @__PURE__ */ t.createElement(m, { danger: !0, onClick: N, loading: j }, "跳过"), /* @__PURE__ */ t.createElement(m, { type: "primary", onClick: K, loading: j }, "提交"))))
  );
}
window.QwenPaw.slot.fill(
  M,
  "overlay.global",
  () => t.createElement(te),
  { id: `${M}.overlay` }
);
console.log("[ask-user] Plugin ready (v6 - push+poll)");
