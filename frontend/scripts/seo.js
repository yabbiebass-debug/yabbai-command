#!/usr/bin/env node
/**
 * Post-build SEO step.
 *
 * public/ and index.html are shared by both builds, so per-target crawler
 * rules cannot live in the source tree — they have to be written after webpack
 * has emitted, once REACT_APP_BUILD_TARGET is known.
 *
 *   npm run build           -> command console  -> Disallow: /   + noindex
 *   npm run build:holders   -> public holders   -> Allow: /      + index,follow + sitemap
 *
 * The direction of the default matters. index.html ships `noindex`, and only
 * the holders branch below clears it. If this script is skipped, dies, or the
 * build command is misconfigured, the failure mode is a public page that does
 * not get listed. The opposite default would put the treasury and withdrawal
 * screens of the director console into a search index, which is not something
 * you can take back once it is crawled.
 */

const fs = require('fs');
const path = require('path');

const IS_HOLDERS = process.env.REACT_APP_BUILD_TARGET === 'holders';
const BUILD_DIR = path.resolve(__dirname, '..', 'build');
const INDEX = path.join(BUILD_DIR, 'index.html');

const HOLDERS_ORIGIN = 'https://holders.yabbai.network';

if (!fs.existsSync(INDEX)) {
  console.error(`[seo] no build output at ${INDEX} — run this after craco build`);
  process.exit(1);
}

const target = IS_HOLDERS ? 'holders (public)' : 'command (private)';
console.log(`[seo] target: ${target}`);

/* ── robots.txt ──────────────────────────────────────────────────────────── */

if (IS_HOLDERS) {
  fs.writeFileSync(
    path.join(BUILD_DIR, 'robots.txt'),
    [
      '# Public holder view. Read-only token statistics, safe to index.',
      'User-agent: *',
      'Allow: /',
      '',
      `Sitemap: ${HOLDERS_ORIGIN}/sitemap.xml`,
      '',
    ].join('\n')
  );
  console.log('[seo] wrote robots.txt (Allow: /)');
} else {
  fs.writeFileSync(
    path.join(BUILD_DIR, 'robots.txt'),
    [
      '# Director console. Nothing here is public.',
      '#',
      '# Note that robots.txt is a request, not access control. The real gate is',
      '# ProtectedRoute on every route plus require_director on the API. This only',
      '# keeps well-behaved crawlers from listing the login shell.',
      'User-agent: *',
      'Disallow: /',
      '',
    ].join('\n')
  );
  console.log('[seo] wrote robots.txt (Disallow: /)');
}

/* ── sitemap.xml ─────────────────────────────────────────────────────────── */

if (IS_HOLDERS) {
  // Only the root. The holders build is a single public view, and listing
  // routes that do not resolve is worse than listing none — Search Console
  // reports them as errors and the whole sitemap loses trust.
  const today = new Date().toISOString().slice(0, 10);
  fs.writeFileSync(
    path.join(BUILD_DIR, 'sitemap.xml'),
    [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
      '  <url>',
      `    <loc>${HOLDERS_ORIGIN}/</loc>`,
      `    <lastmod>${today}</lastmod>`,
      '    <changefreq>daily</changefreq>',
      '    <priority>1.0</priority>',
      '  </url>',
      '</urlset>',
      '',
    ].join('\n')
  );
  console.log('[seo] wrote sitemap.xml');
} else {
  // Defensive: a stale sitemap left from a previous holders build in the same
  // directory would advertise the console's origin as crawlable.
  const stale = path.join(BUILD_DIR, 'sitemap.xml');
  if (fs.existsSync(stale)) {
    fs.unlinkSync(stale);
    console.log('[seo] removed stale sitemap.xml');
  }
}

/* ── flip the robots meta ────────────────────────────────────────────────── */

if (IS_HOLDERS) {
  const html = fs.readFileSync(INDEX, 'utf8');
  const before = '<meta name="robots" content="noindex, nofollow"';
  const after = '<meta name="robots" content="index, follow"';

  if (!html.includes(before)) {
    // Loud rather than silent: if the tag was renamed in index.html and this
    // string stopped matching, the holders site would ship noindex forever and
    // nothing would ever explain why it is absent from Google.
    console.error('[seo] FAILED: robots meta not found in built index.html.');
    console.error('[seo] public/index.html must contain exactly:');
    console.error(`[seo]   ${before} />`);
    process.exit(1);
  }

  fs.writeFileSync(INDEX, html.replace(before, after));
  console.log('[seo] index.html -> index, follow');
} else {
  console.log('[seo] index.html left at noindex (correct for the console)');
}

console.log('[seo] done');
