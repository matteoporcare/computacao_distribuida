const express = require('express');
const bodyParser = require('body-parser');
const { v4: uuidv4 } = require('uuid');

const app = express();
app.use(bodyParser.json());

const locks = new Map();

function nowMs() { return Date.now(); }

app.post('/lock', (req, res) => {
  const { resource, ttl_ms } = req.body || {};
  if (!resource) return res.status(400).json({ error: 'resource is required' });

  const existing = locks.get(resource);

  if (existing && existing.expiresAt > nowMs()) {
    return res.status(409).json({
      error: 'locked',
      owner: existing.owner,
      expiresAt: existing.expiresAt
    });
  }

  const owner = uuidv4();
  const ttl = ttl_ms && ttl_ms > 0 ? ttl_ms : 30000;
  const expiresAt = nowMs() + ttl;

  if (existing && existing.timeoutId) clearTimeout(existing.timeoutId);

  const timeoutId = setTimeout(() => {
    locks.delete(resource);
    console.log(`[unlock][auto] resource=${resource}`);
  }, ttl);

  locks.set(resource, { owner, expiresAt, timeoutId });
  return res.status(200).json({ owner, expiresAt });
});

app.post('/unlock', (req, res) => {
  const { resource, owner } = req.body || {};

  if (!resource) return res.status(400).json({ error: 'resource is required' });

  const existing = locks.get(resource);

  if (!existing) return res.status(200).json({ result: 'no-lock' });

  if (owner && owner !== existing.owner) {
    return res.status(403).json({ error: 'owner-mismatch', owner: existing.owner });
  }

  clearTimeout(existing.timeoutId);
  locks.delete(resource);

  return res.status(200).json({ result: 'unlocked' });
});

app.get('/locks', (req, res) => {
  res.json(Array.from(locks.entries()));
});

app.listen(3000, () => {
  console.log("Coordenador rodando em http://localhost:3000");
});
