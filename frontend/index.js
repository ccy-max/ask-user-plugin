const { React: t, antd: te, getApiUrl: ie } = window.QwenPaw.host, { Modal: J, Steps: ne, Radio: q, Checkbox: O, Input: L, Button: d, Space: ae, message: m } = te, { TextArea: K } = L, N = "qwenpaw-ask-user-plugin", se = 1e4, g = "__other__", v = window.fetch.bind(window);
function le() {
  const [c, E] = t.useState(null), [o, h] = t.useState(0), [T, $] = t.useState({}), [j, z] = t.useState(""), [I, B] = t.useState(!1), u = t.useRef(null), k = t.useRef(""), D = t.useRef(null);
  D.current = c, c && (k.current = c.session_id);
  const C = t.useCallback((e) => {
    E(e), h(0), z("");
    const n = {};
    (e.questions || []).forEach((l, r) => {
      n[`q${r}`] = {
        type: l.type,
        value: l.type === "multi" ? [] : "",
        other: ""
      };
    }), $(n);
  }, []), U = t.useCallback(
    async (e, n) => {
      try {
        const l = await v(
          `/api/ask-user/details?request_id=${encodeURIComponent(e)}`,
          { signal: n }
        );
        if (!l.ok) return null;
        const r = await l.json();
        return r.status === "pending" ? r : null;
      } catch {
        return null;
      }
    },
    []
  );
  if (t.useEffect(() => {
    const e = new AbortController();
    let n;
    async function l() {
      try {
        if (k.current)
          try {
            const P = `/api/console/push-messages?session_id=${encodeURIComponent(
              k.current
            )}`, G = await v(P, { signal: e.signal });
            if (G.ok) {
              const Z = await G.json();
              for (const ee of Z.messages || []) {
                const H = ee.text || "";
                if (H.startsWith("ask_user_question:")) {
                  const [, f, M] = H.split(":");
                  if (f && u.current !== f) {
                    u.current = f;
                    const w = await U(f, e.signal);
                    if (w) {
                      !w.secret && M && (w.secret = M), C(w);
                      return;
                    }
                  }
                }
              }
            }
          } catch {
          }
        const r = await v("/api/ask-user/pending", {
          signal: e.signal
        });
        if (!r.ok) return;
        const y = ((await r.json()).items || []).find(
          (P) => P.status === "pending"
        );
        if (!y) {
          D.current && E(null);
          return;
        }
        if (u.current === y.request_id) return;
        u.current = y.request_id, C(y);
      } catch (r) {
        r.name !== "AbortError" && console.warn("[ask-user] Poll:", r.message);
      }
    }
    return l(), n = setInterval(l, se), () => {
      e.abort(), clearInterval(n);
    };
  }, [C, U]), !c) return null;
  const { questions: i, title: W, request_id: b, session_id: S, secret: _ } = c, V = i.length + 1, x = o >= i.length, s = x ? null : i[o], F = `q${o}`, a = T[F] || { type: (s == null ? void 0 : s.type) || "text", value: "", other: "" }, p = (e) => {
    $((n) => ({ ...n, [F]: e }));
  }, A = async (e, n) => {
    B(!0);
    try {
      const l = await v(e, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(n)
      });
      if (!l.ok) {
        const r = await l.json().catch(() => ({}));
        throw new Error(r.detail || `HTTP ${l.status}`);
      }
    } finally {
      B(!1);
    }
  }, R = () => {
    E(null), u.current = null;
  }, X = async () => {
    try {
      await A("/api/ask-user/answer", {
        request_id: b,
        session_id: S,
        secret: _,
        answers: T,
        other: j
      }), m.success("✓ 已提交答案"), R();
    } catch (e) {
      m.error(`提交失败: ${e.message}`);
    }
  }, Y = async () => {
    try {
      await A("/api/ask-user/skip", { request_id: b, session_id: S, secret: _ }), m.info("已跳过问卷"), R();
    } catch (e) {
      m.error(`跳过失败: ${e.message}`);
    }
  }, Q = async () => {
    try {
      await A("/api/ask-user/skip", { request_id: b, session_id: S, secret: _ });
    } catch {
    }
    m.info("问卷已跳过"), R();
  };
  return i.length === 0 ? /* @__PURE__ */ t.createElement(
    J,
    {
      title: "❓ 问卷",
      open: !0,
      onCancel: Q,
      width: 560,
      footer: null,
      maskClosable: !1,
      keyboard: !1,
      destroyOnClose: !0
    },
    /* @__PURE__ */ t.createElement("div", { style: { textAlign: "center", padding: 32, color: "#999" } }, "加载中...")
  ) : /* @__PURE__ */ t.createElement(
    J,
    {
      title: /* @__PURE__ */ t.createElement("span", null, /* @__PURE__ */ t.createElement("span", { style: { marginRight: 8 } }, "❓"), W || "问卷"),
      open: !0,
      onCancel: Q,
      width: 560,
      footer: null,
      maskClosable: !1,
      keyboard: !1,
      destroyOnClose: !0
    },
    /* @__PURE__ */ t.createElement(
      ne,
      {
        current: o,
        size: "small",
        style: { marginBottom: 16 },
        items: [
          ...i.map(() => ({ title: "" })),
          { title: "其他" }
        ]
      }
    ),
    !x && s && /* @__PURE__ */ t.createElement("div", null, /* @__PURE__ */ t.createElement("div", { style: { fontSize: 13, color: "#999", marginBottom: 8 } }, o + 1, " / ", i.length), /* @__PURE__ */ t.createElement("h3", { style: { margin: "0 0 16px 0", fontSize: 16 } }, s.title), s.type === "single" && s.options && /* @__PURE__ */ t.createElement(
      q.Group,
      {
        value: a.value,
        onChange: (e) => p({ ...a, value: e.target.value }),
        style: { display: "flex", flexDirection: "column", gap: 10 }
      },
      s.options.map((e, n) => /* @__PURE__ */ t.createElement(q, { key: n, value: e }, e)),
      /* @__PURE__ */ t.createElement(q, { value: g }, "其他", a.value === g && /* @__PURE__ */ t.createElement(
        L,
        {
          size: "small",
          placeholder: "请填写",
          value: a.other,
          onChange: (e) => p({ ...a, other: e.target.value }),
          style: { marginLeft: 8, width: 200 },
          onClick: (e) => e.stopPropagation()
        }
      ))
    ), s.type === "multi" && s.options && /* @__PURE__ */ t.createElement(
      O.Group,
      {
        value: Array.isArray(a.value) ? a.value : [],
        onChange: (e) => {
          const n = e.includes(g);
          p({
            ...a,
            value: e,
            other: n ? a.other : ""
          });
        },
        style: { display: "flex", flexDirection: "column", gap: 10 }
      },
      s.options.map((e, n) => /* @__PURE__ */ t.createElement(O, { key: n, value: e }, e)),
      /* @__PURE__ */ t.createElement(O, { value: g }, "其他", Array.isArray(a.value) && a.value.includes(g) && /* @__PURE__ */ t.createElement(
        L,
        {
          size: "small",
          placeholder: "请填写",
          value: a.other,
          onChange: (e) => p({ ...a, other: e.target.value }),
          style: { marginLeft: 8, width: 200 },
          onClick: (e) => e.stopPropagation()
        }
      ))
    ), s.type === "text" && /* @__PURE__ */ t.createElement(
      K,
      {
        rows: 4,
        placeholder: "请输入...",
        value: typeof a.value == "string" ? a.value : "",
        onChange: (e) => p({ ...a, value: e.target.value, other: "" })
      }
    ), /* @__PURE__ */ t.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          marginTop: 20
        }
      },
      /* @__PURE__ */ t.createElement(d, { disabled: o === 0, onClick: () => h((e) => e - 1) }, "上一步"),
      /* @__PURE__ */ t.createElement(d, { type: "primary", onClick: () => h((e) => e + 1) }, "下一步")
    )),
    x && /* @__PURE__ */ t.createElement("div", null, /* @__PURE__ */ t.createElement("div", { style: { fontSize: 13, color: "#999", marginBottom: 8 } }, o + 1, " / ", V), /* @__PURE__ */ t.createElement("h3", { style: { margin: "0 0 12px 0", fontSize: 16 } }, "其他意见"), /* @__PURE__ */ t.createElement(
      K,
      {
        rows: 3,
        placeholder: "补充意见（可选）",
        value: j,
        onChange: (e) => z(e.target.value)
      }
    ), /* @__PURE__ */ t.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          marginTop: 16
        }
      },
      /* @__PURE__ */ t.createElement(d, { onClick: () => h((e) => e - 1) }, "上一步"),
      /* @__PURE__ */ t.createElement(ae, null, /* @__PURE__ */ t.createElement(d, { danger: !0, onClick: Y, loading: I }, "跳过"), /* @__PURE__ */ t.createElement(d, { type: "primary", onClick: X, loading: I }, "提交"))
    ))
  );
}
window.QwenPaw.slot.fill(
  N,
  "overlay.global",
  () => t.createElement(le),
  { id: `${N}.overlay` }
);
console.log("[qwenpaw-ask-user-plugin] Plugin ready (v2 - push+poll+secret)");
