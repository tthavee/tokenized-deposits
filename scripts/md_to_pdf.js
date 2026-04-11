#!/usr/bin/env node
/**
 * Converts ARCHITECTURE.md → ARCHITECTURE.pdf
 *
 * Strategy:
 *   1. Read the markdown file
 *   2. Build a self-contained HTML page with:
 *        - GitHub-flavoured CSS
 *        - Mermaid.js (CDN) for diagram rendering
 *        - highlight.js for code blocks
 *   3. Write the HTML to a temp file
 *   4. Use Chrome headless to print it to PDF
 */

const fs   = require('fs');
const path = require('path');
const os   = require('os');
const { execSync, spawnSync } = require('child_process');

// ---------------------------------------------------------------------------
// Minimal markdown → HTML  (no external deps — handles the subset we use)
// ---------------------------------------------------------------------------
function mdToHtml(md) {
  let html = md
    // Mermaid fenced blocks — wrap in <pre class="mermaid">
    .replace(/```mermaid\n([\s\S]*?)```/g, (_, code) =>
      `<pre class="mermaid">${esc(code.trim())}</pre>`)

    // Other fenced code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code class="language-${lang}">${esc(code.trim())}</code></pre>`)

    // Inline code
    .replace(/`([^`]+)`/g, (_, c) => `<code>${esc(c)}</code>`)

    // Headings
    .replace(/^###### (.+)$/gm, (_, t) => `<h6>${t}</h6>`)
    .replace(/^##### (.+)$/gm,  (_, t) => `<h5>${t}</h5>`)
    .replace(/^#### (.+)$/gm,   (_, t) => `<h4>${t}</h4>`)
    .replace(/^### (.+)$/gm,    (_, t) => `<h3>${t}</h3>`)
    .replace(/^## (.+)$/gm,     (_, t) => `<h2>${t}</h2>`)
    .replace(/^# (.+)$/gm,      (_, t) => `<h1>${t}</h1>`)

    // Horizontal rules
    .replace(/^---$/gm, '<hr>')

    // Bold / italic
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g,     '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,         '<em>$1</em>')

    // Tables
    .replace(/(\|.+\|\n)(\|[-| :]+\|\n)((?:\|.+\|\n)*)/g, buildTable)

    // Unordered lists
    .replace(/((?:^- .+\n?)+)/gm, buildUl)

    // Ordered lists
    .replace(/((?:^\d+\. .+\n?)+)/gm, buildOl)

    // Blockquotes (unused but safe)
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // Paragraphs: wrap non-block lines
  html = html
    .split('\n')
    .map(line => {
      const trimmed = line.trim();
      if (!trimmed) return '';
      if (/^<(h[1-6]|hr|pre|ul|ol|li|table|thead|tbody|tr|th|td|blockquote|div)/.test(trimmed)) return line;
      return `<p>${trimmed}</p>`;
    })
    .join('\n');

  return html;
}

function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function buildTable(match, header, sep, body) {
  const parseRow = row =>
    row.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());

  const aligns = parseRow(sep).map(c => {
    if (c.startsWith(':') && c.endsWith(':')) return 'center';
    if (c.endsWith(':')) return 'right';
    return 'left';
  });

  const thCells = parseRow(header)
    .map((c, i) => `<th style="text-align:${aligns[i]}">${c}</th>`)
    .join('');

  const rows = body.trim().split('\n').map(row => {
    const cells = parseRow(row)
      .map((c, i) => `<td style="text-align:${aligns[i]}">${c}</td>`)
      .join('');
    return `<tr>${cells}</tr>`;
  }).join('\n');

  return `<table><thead><tr>${thCells}</tr></thead><tbody>${rows}</tbody></table>\n`;
}

function buildUl(block) {
  const items = block.trim().split('\n')
    .map(l => `<li>${l.replace(/^- /, '')}</li>`)
    .join('');
  return `<ul>${items}</ul>\n`;
}

function buildOl(block) {
  const items = block.trim().split('\n')
    .map(l => `<li>${l.replace(/^\d+\. /, '')}</li>`)
    .join('');
  return `<ol>${items}</ol>\n`;
}

// ---------------------------------------------------------------------------
// HTML template
// ---------------------------------------------------------------------------
function buildPage(content) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Tokenized Deposits — Architecture</title>
<style>
  /* ---- Page setup ---- */
  @page {
    margin: 18mm 20mm 18mm 20mm;
    size: A4;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.6;
    color: #24292f;
    max-width: 860px;
    margin: 0 auto;
    padding: 0;
  }

  /* ---- Headings ---- */
  h1 { font-size: 2em;   border-bottom: 2px solid #0969da; padding-bottom: .3em; color: #0969da; margin-top: 1.2em; }
  h2 { font-size: 1.5em; border-bottom: 1px solid #d0d7de; padding-bottom: .3em; margin-top: 1.2em; }
  h3 { font-size: 1.2em; margin-top: 1em; color: #0969da; }
  h4 { font-size: 1em;   font-weight: 600; }

  /* ---- Horizontal rule ---- */
  hr { border: none; border-top: 1px solid #d0d7de; margin: 1.5em 0; }

  /* ---- Inline code ---- */
  code {
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: .15em .35em;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: .9em;
    color: #cf222e;
  }

  /* ---- Code blocks ---- */
  pre {
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 14px 16px;
    overflow-x: auto;
    font-size: .88em;
    line-height: 1.5;
    page-break-inside: avoid;
  }
  pre code {
    background: none;
    border: none;
    padding: 0;
    color: #24292f;
    font-size: 1em;
  }

  /* ---- Mermaid diagrams ---- */
  pre.mermaid {
    background: #f0f6ff;
    border: 1px solid #b6d4fe;
    text-align: center;
    padding: 18px;
    page-break-inside: avoid;
  }
  .mermaid svg {
    max-width: 100%;
    height: auto;
  }

  /* ---- Tables ---- */
  table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: .95em;
    page-break-inside: avoid;
  }
  th {
    background: #0969da;
    color: #fff;
    padding: 8px 12px;
    text-align: left;
  }
  td {
    padding: 7px 12px;
    border: 1px solid #d0d7de;
  }
  tr:nth-child(even) td { background: #f6f8fa; }

  /* ---- Lists ---- */
  ul, ol { padding-left: 1.8em; margin: .5em 0; }
  li { margin: .2em 0; }

  /* ---- Blockquote ---- */
  blockquote {
    border-left: 4px solid #0969da;
    padding: .5em 1em;
    margin: 1em 0;
    color: #57606a;
    background: #f6f8fa;
  }

  /* ---- Paragraphs ---- */
  p { margin: .6em 0; }

  /* ---- Print ---- */
  @media print {
    h1, h2, h3 { page-break-after: avoid; }
    pre, table, figure { page-break-inside: avoid; }
  }
</style>
</head>
<body>
${content}

<!-- Mermaid -->
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({
    startOnLoad: true,
    theme: 'default',
    securityLevel: 'loose',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  });
</script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const root    = path.join(__dirname, '..');
const mdPath  = path.join(root, 'ARCHITECTURE.md');
const htmlPath = path.join(os.tmpdir(), 'architecture_tmp.html');
const pdfPath  = path.join(root, 'ARCHITECTURE.pdf');

console.log('Reading markdown…');
const md   = fs.readFileSync(mdPath, 'utf8');
const body = mdToHtml(md);
const html = buildPage(body);

console.log('Writing temp HTML…');
fs.writeFileSync(htmlPath, html, 'utf8');

// Find Chrome
const chrome = [
  'google-chrome',
  'google-chrome-stable',
  'chromium-browser',
  'chromium',
].find(bin => {
  try { execSync(`which ${bin}`, { stdio: 'ignore' }); return true; } catch { return false; }
});

if (!chrome) {
  console.error('Chrome / Chromium not found.');
  process.exit(1);
}

console.log(`Rendering with ${chrome}…`);
const result = spawnSync(chrome, [
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  '--disable-dev-shm-usage',
  '--run-all-compositor-stages-before-draw',
  '--virtual-time-budget=8000',       // wait 8s for Mermaid JS to render
  `--print-to-pdf=${pdfPath}`,
  `--print-to-pdf-no-header`,
  `file://${htmlPath}`,
], { stdio: 'inherit', timeout: 60000 });

if (result.status !== 0) {
  console.error('Chrome exited with status', result.status);
  process.exit(result.status);
}

const size = (fs.statSync(pdfPath).size / 1024).toFixed(1);
console.log(`\nDone → ${pdfPath}  (${size} KB)`);
