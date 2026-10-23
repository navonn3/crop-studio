// Encrypts src/app.html behind a password into docs/index.html (served by GitHub Pages).
// Usage:  CROP_PASSWORD='...' node build.mjs
// The salt is kept in .salt so a rebuild with the same password keeps "remember me" logins valid.
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, rmSync } from 'node:fs';
import { webcrypto as crypto } from 'node:crypto';

const pw = process.env.CROP_PASSWORD;
if (!pw) { console.error('Set CROP_PASSWORD'); process.exit(1); }
const ITER = 250000;
const b64 = u => Buffer.from(u).toString('base64');

let salt;
if (existsSync('.salt')) salt = Buffer.from(readFileSync('.salt', 'utf8').trim(), 'base64');
else { salt = crypto.getRandomValues(new Uint8Array(16)); writeFileSync('.salt', b64(salt)); }
const iv = crypto.getRandomValues(new Uint8Array(12));

const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
const key = await crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: ITER, hash: 'SHA-256' },
  base, { name: 'AES-GCM', length: 256 }, false, ['encrypt']);
const seal = async bytes => { const v = crypto.getRandomValues(new Uint8Array(12));
  const c = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: v }, key, bytes));
  const o = new Uint8Array(12 + c.length); o.set(v); o.set(c, 12); return o; };
// build stamp shown in the header, so a phone can tell whether it runs the newest version (Pages caches 10 min)
const d = new Date(), pad = x => String(x).padStart(2, '0');
const stamp = `${d.getDate()}.${d.getMonth() + 1} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
const app = readFileSync('src/app.html', 'utf8').replace('__BUILD__', () => stamp);
const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(app));

const payload = JSON.stringify({ s: b64(salt), i: b64(iv), c: b64(new Uint8Array(ct)), n: ITER });
const page = readFileSync('src/gate.html', 'utf8').replace('__PAYLOAD__', () => payload);
mkdirSync('docs', { recursive: true });
writeFileSync('docs/index.html', page);
writeFileSync('docs/.nojekyll', '');

// game mode data (tools/export_games.py -> data/games/*.json), encrypted with the same key as iv(12) + ciphertext
rmSync('docs/g', { recursive: true, force: true });
if (existsSync('data/games')) {
  mkdirSync('docs/g', { recursive: true });
  const files = readdirSync('data/games').filter(f => f.endsWith('.json'));
  for (const f of files) writeFileSync('docs/g/' + f.replace(/\.json$/, '.bin'), await seal(readFileSync('data/games/' + f)));
  console.log(`docs/g: ${files.length} encrypted game files`);
}
console.log(`docs/index.html written (${(page.length / 1024).toFixed(0)} KB)`);
