
import { verifyKey } from "discord-interactions";
export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("OK");
    const sig = request.headers.get("X-Signature-Ed25519");
    const ts  = request.headers.get("X-Signature-Timestamp");
    const body = await request.text();
    const ok = verifyKey(body, sig, ts, env.DISCORD_PUBLIC_KEY);
    if (!ok) return new Response("Bad signature", { status: 401 });
    const i = JSON.parse(body);
    if (i?.type === 1) return Response.json({ type: 1 });
    const opts = Object.fromEntries((i?.data?.options || []).map(o => [o.name, o.value]));
    const payload = {
      prompt: opts.prompt || opts.topic || "",
      duration: Number(opts.duration || 55),
      platforms: (opts.platforms || "tiktok,ig,yt").split(/[\s,]+/).reduce((m,k)=>{ if(k){ m[k.trim()] = true; } return m; },{}),
      ab: opts.ab !== "false",
      interaction: { id: i.id, token: i.token },
    };
    ctx.waitUntil(fetch(env.N8N_WEBHOOK_URL, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) }));
    return Response.json({ type: 5 });
  }
}
