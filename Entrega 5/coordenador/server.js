// coordenador/server.js
const express = require('express');
const { createClient } = require('redis');
const { v4: uuidv4 } = require('uuid');

const app = express();
app.use(express.json());

const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379";
const redis = createClient({ url: REDIS_URL });
redis.on("error", (e) => console.error("redis err", e));

(async () => { await redis.connect(); console.log("Redis connected", REDIS_URL); })();

function nowMs(){ return Date.now(); }

app.post('/lock', async (req, res) => {
  const { resource, ttl_ms } = req.body || {};
  if (!resource) return res.status(400).json({ error: 'resource required' });
  const ttl = (typeof ttl_ms === 'number' && ttl_ms>0) ? ttl_ms : 30000;
  const owner = uuidv4();
  try {
    const ok = await redis.set(resource, owner, { NX: true, PX: ttl });
    if (!ok) {
      const current = await redis.get(resource);
      const ttlLeft = await redis.pTTL(resource);
      return res.status(409).json({ error: 'locked', owner: current, expiresAt: nowMs() + (ttlLeft>0 ? ttlLeft : 0) });
    }
    console.log(`[lock granted] resource=${resource} owner=${owner} ttl=${ttl}`);
    return res.status(200).json({ owner, expiresAt: nowMs()+ttl });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ error: 'internal', detail: String(e) });
  }
});

const UNLOCK_SCRIPT = `
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
else
  return 0
end
`;

app.post('/unlock', async (req,res) => {
  const { resource, owner } = req.body || {};
  if (!resource) return res.status(400).json({ error:'resource required' });
  try {
    if (owner) {
      const r = await redis.eval(UNLOCK_SCRIPT, { keys: [resource], arguments: [owner] });
      if (r===1) { console.log(`[unlock] resource=${resource} owner=${owner}`); return res.json({ result:'unlocked' }); }
      else return res.status(403).json({ error:'owner-mismatch' });
    } else {
      await redis.del(resource);
      return res.json({ result:'unlocked' });
    }
  } catch (e) { console.error(e); return res.status(500).json({error:'internal', detail:String(e)}); }
});

app.get('/locks', async (req,res) => {
  try {
    const keys = await redis.keys('*');
    const out = [];
    for (const k of keys) {
      const v = await redis.get(k);
      const ttl = await redis.pTTL(k);
      out.push({ resource:k, owner:v, ttl_ms: ttl });
    }
    return res.json(out);
  } catch(e) { return res.status(500).json({ error: String(e) }); }
});

app.get('/health', (req,res) => res.json({ status:'ok', time: new Date().toISOString()}));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Coordenador listening ${PORT}`));
