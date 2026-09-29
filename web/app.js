/**
 * FutureTxt 纯前端长篇小说创作与导出引擎 (Pure Vanilla ES6)
 * 具备 32 篇科幻知识库轻量检索、流式 SSE 请求、多阶段流水线、浏览器端生成 EPUB/HTML/TXT。
 */

import { generateEpub } from './epub_builder.js';

// 状态管理
const state = {
  kbBundle: null,
  projects: {},
  currentProjectId: null,
  config: {
    apiKey: '',
    baseUrl: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
  },
  isGenerating: false,
  fontSize: 16,
};

// 系统提示词
const SYSTEM_WRITER = `你是一位荣获雨果奖、星云奖水准的世界级中文科幻小说作家。吸收特德·姜的思想实验推演、刘慈欣的宏大宇宙冷酷张力与威廉·吉布森的粗粝通感白描。核心写作铁律：
1) 坚决破除说明文塑料感：严禁开篇设定讲座；世界观与硬科技必须通过人物身体的生理磨损、感官不适与生存代价隐形滴灌（Show, Don't Explain）。
2) 感官具象与电影质感：开篇第一段必须包含至少两种感官细节（气味、触觉、声音、温度）；科技道具充满工业磨损与细节真实感。
3) 人物动机与存在主义困境：拒绝脸谱化善恶，冲突源于客观宇宙法则与人类情感尊严的不可调和；对话具备鲜明语言指纹，杜绝汇报式对白。
4) 严格遵守世界观硬性设定编号（W1..Wn）与角色一致性铁律（C1..Cn）。
5) 纯 Markdown 正文输出，严禁任何前言、后记、免责声明或寒暄。`;

// 本地存储键
const STORAGE_KEYS = {
  CONFIG: 'futuretxt_config',
  PROJECTS: 'futuretxt_projects',
  CURRENT_PID: 'futuretxt_current_pid',
};

// ---------------------------------------------------------------- 初始化

document.addEventListener('DOMContentLoaded', async () => {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
  loadLocalSettings();
  bindNavigation();
  bindStudioEvents();
  bindSettingsEvents();
  bindExportEvents();
  await loadKnowledgeBase();
  initProjectsList();
});

function loadLocalSettings() {
  const savedCfg = localStorage.getItem(STORAGE_KEYS.CONFIG);
  if (savedCfg) {
    try {
      state.config = { ...state.config, ...jsonParseSafe(savedCfg) };
    } catch (e) {}
  }
  document.getElementById('cfg-api-key').value = state.config.apiKey || '';
  document.getElementById('cfg-base-url').value = state.config.baseUrl || 'https://api.deepseek.com/v1';
  document.getElementById('cfg-model').value = state.config.model || 'deepseek-chat';

  const savedProjs = localStorage.getItem(STORAGE_KEYS.PROJECTS);
  if (savedProjs) {
    try {
      state.projects = jsonParseSafe(savedProjs) || {};
    } catch (e) {}
  }

  // 默认如果无项目，内置示范项目
  if (Object.keys(state.projects).length === 0) {
    seedDefaultProject();
  }

  state.currentProjectId = localStorage.getItem(STORAGE_KEYS.CURRENT_PID) || Object.keys(state.projects)[0];
}

function saveProjects() {
  localStorage.setItem(STORAGE_KEYS.PROJECTS, JSON.stringify(state.projects));
}

function jsonParseSafe(str) {
  try { return JSON.parse(str); } catch (e) { return null; }
}

// ---------------------------------------------------------------- 知识库加载与轻量 RAG

async function loadKnowledgeBase() {
  try {
    const res = await fetch('knowledge_bundle.json');
    if (res.ok) {
      state.kbBundle = await res.json();
      document.getElementById('kb-stats-badge').innerText = `已载入 ${state.kbBundle.files.length} 篇文档`;
    }
  } catch (err) {
    console.warn('加载本地知识库包失败:', err);
  }
}

function retrieveKnowledge(query, limitChars = 4000) {
  if (!state.kbBundle || !state.kbBundle.files) return '';
  const keywords = query.split(/[\s,，、]+/).filter(k => k.length >= 2);
  const scored = [];

  for (const f of state.kbBundle.files) {
    let score = 0;
    for (const kw of keywords) {
      if (f.title.includes(kw)) score += 10;
      const count = (f.content.match(new RegExp(kw, 'gi')) || []).length;
      score += Math.min(count, 5);
    }
    if (score > 0) {
      scored.push({ file: f, score });
    }
  }

  scored.sort((a, b) => b.score - a.score);
  let total = 0;
  const parts = [];

  for (const item of scored) {
    if (total >= limitChars) break;
    const piece = item.file.content.slice(0, Math.min(1000, limitChars - total));
    parts.push(`【${item.file.title}】\n${piece}`);
    total += piece.length;
  }
  return parts.join('\n\n');
}

// ---------------------------------------------------------------- UI 导航与交互

function bindNavigation() {
  const navBtns = document.querySelectorAll('.app-bottom-nav .nav-item');
  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      navBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-target');
      document.querySelectorAll('.app-view').forEach(v => v.classList.remove('active'));
      document.getElementById(targetId).classList.add('active');

      if (targetId === 'view-chapters') renderChaptersView();
      if (targetId === 'view-reader') renderReaderView();
    });
  });

  // 主题切换
  document.getElementById('btn-theme-toggle').addEventListener('click', () => {
    document.body.classList.toggle('light-theme');
  });

  // 设置跳转
  document.getElementById('btn-quick-config').addEventListener('click', () => {
    document.querySelector('.nav-item[data-target="view-settings"]').click();
  });
}

function bindStudioEvents() {
  document.getElementById('select-project').addEventListener('change', (e) => {
    state.currentProjectId = e.target.value;
    localStorage.setItem(STORAGE_KEYS.CURRENT_PID, state.currentProjectId);
    updateStudioView();
  });

  document.getElementById('btn-new-project').addEventListener('click', () => {
    document.getElementById('modal-new-project').style.display = 'flex';
  });

  document.getElementById('btn-close-modal').addEventListener('click', () => {
    document.getElementById('modal-new-project').style.display = 'none';
  });

  document.getElementById('btn-confirm-create').addEventListener('click', () => {
    const title = document.getElementById('new-title').value.trim() || '未命名科幻';
    const keywords = document.getElementById('new-keywords').value.trim();
    const premise = document.getElementById('new-premise').value.trim();
    const chapters = parseInt(document.getElementById('new-chapters').value) || 10;
    const words = parseInt(document.getElementById('new-words').value) || 2500;
    const tone = document.getElementById('new-tone').value.trim();

    const pid = 'proj_' + Date.now();
    state.projects[pid] = {
      id: pid,
      title,
      keywords,
      premise,
      target_chapters: chapters,
      words_per_chapter: words,
      tone,
      stage: 'concept',
      concept: '',
      world: '',
      characters: '',
      outline: '',
      chapters: {},
    };

    saveProjects();
    state.currentProjectId = pid;
    localStorage.setItem(STORAGE_KEYS.CURRENT_PID, pid);
    document.getElementById('modal-new-project').style.display = 'none';
    initProjectsList();
    alert(`✓ 小说《${title}》创建成功！`);
  });

  document.getElementById('btn-run-stage').addEventListener('click', executeCurrentStage);
  document.getElementById('btn-draft-single').addEventListener('click', () => {
    const ch = parseInt(document.getElementById('select-chapter-to-draft').value);
    draftChapter(ch);
  });

  document.getElementById('btn-copy-stream').addEventListener('click', () => {
    const text = document.getElementById('live-stream-box').innerText;
    navigator.clipboard.writeText(text).then(() => alert('已复制到剪贴板！'));
  });
}

function bindSettingsEvents() {
  document.getElementById('btn-save-config').addEventListener('click', async () => {
    const key = document.getElementById('cfg-api-key').value.trim();
    const url = document.getElementById('cfg-base-url').value.trim();
    const model = document.getElementById('cfg-model').value.trim();

    if (!key) {
      alert('请填写 API Key！');
      return;
    }

    state.config.apiKey = key;
    state.config.baseUrl = url;
    state.config.model = model;
    localStorage.setItem(STORAGE_KEYS.CONFIG, JSON.stringify(state.config));

    // 测试连通性
    const btn = document.getElementById('btn-save-config');
    btn.innerText = '正在测试 API 连通性...';
    try {
      const resp = await fetch(`${url.replace(/\/+$/, '')}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${key}`,
        },
        body: JSON.stringify({
          model: model,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 5,
        }),
      });
      if (resp.ok) {
        alert('✓ API 连通测试成功！');
      } else {
        const err = await resp.text();
        alert(`✗ 连接失败 (${resp.status}): ${err.slice(0, 150)}`);
      }
    } catch (e) {
      alert(`✗ 请求异常: ${e.message}`);
    } finally {
      btn.innerText = '保存设置并测试连通性';
    }
  });

  // 知识库搜索
  document.getElementById('kb-search-input').addEventListener('input', (e) => {
    const q = e.target.value.trim();
    const container = document.getElementById('kb-search-results');
    if (!q || !state.kbBundle) {
      container.innerHTML = '';
      return;
    }
    const hits = state.kbBundle.files.filter(f => f.title.includes(q) || f.content.includes(q));
    container.innerHTML = hits.slice(0, 8).map(h => `
      <div class="chapter-item">
        <div>
          <div class="chapter-item-title">${h.title}</div>
          <div class="chapter-item-meta">${h.category} · ${h.char_count} 字</div>
        </div>
      </div>
    `).join('');
  });
}

// ---------------------------------------------------------------- 项目列表与视图渲染

function initProjectsList() {
  const sel = document.getElementById('select-project');
  sel.innerHTML = '';
  const pids = Object.keys(state.projects);
  pids.forEach(pid => {
    const p = state.projects[pid];
    const opt = document.createElement('option');
    opt.value = pid;
    opt.innerText = p.title;
    if (pid === state.currentProjectId) opt.selected = true;
    sel.appendChild(opt);
  });
  updateStudioView();
}

function updateStudioView() {
  const proj = state.projects[state.currentProjectId];
  if (!proj) return;
  document.getElementById('current-project-title').innerText = `《${proj.title}》`;

  const stages = ['concept', 'world', 'characters', 'outline', 'draft', 'export'];
  const stageLabels = {
    concept: '创作概念',
    world: '世界观设定',
    characters: '角色体系',
    outline: '全书大纲',
    draft: '逐章正文',
    export: '成书交付',
  };

  let currIdx = stages.indexOf(proj.stage);
  if (currIdx === -1) currIdx = 0;

  document.querySelectorAll('.stage-stepper .step-node').forEach((node, idx) => {
    node.classList.remove('completed', 'current');
    if (idx < currIdx) node.classList.add('completed');
    else if (idx === currIdx) node.classList.add('current');
  });

  const btnLabel = document.getElementById('btn-run-label');
  const nextStage = stages[currIdx];
  btnLabel.innerText = `生成：${stageLabels[nextStage] || '已完成'}`;

  const draftRow = document.getElementById('draft-control-row');
  if (proj.stage === 'draft' || proj.outline) {
    draftRow.style.display = 'flex';
    populateDraftOptions(proj);
  } else {
    draftRow.style.display = 'none';
  }
}

function populateDraftOptions(proj) {
  const sel = document.getElementById('select-chapter-to-draft');
  sel.innerHTML = '';
  const total = proj.target_chapters || 10;
  for (let i = 1; i <= total; i++) {
    const opt = document.createElement('option');
    opt.value = i;
    const isDone = !!proj.chapters[i];
    opt.innerText = `第 ${i} 章 ${isDone ? '(已完成 ' + proj.chapters[i].length + '字)' : '(待写)'}`;
    sel.appendChild(opt);
  }
}

// ---------------------------------------------------------------- 流式 SSE 调用与流水线推进

async function chatStream(messages, onChunk) {
  if (!state.config.apiKey) {
    alert('请先进入「设置」配置 API Key！');
    document.querySelector('.nav-item[data-target="view-settings"]').click();
    throw new Error('Missing API Key');
  }

  const url = `${state.config.baseUrl.replace(/\/+$/, '')}/chat/completions`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${state.config.apiKey}`,
    },
    body: JSON.stringify({
      model: state.config.model,
      messages: messages,
      stream: true,
      temperature: 0.8,
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`API Error ${resp.status}: ${errText.slice(0, 120)}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let fullText = '';
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // 保持未满行

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) continue;
      const dataStr = trimmed.slice(5).trim();
      if (dataStr === '[DONE]') continue;
      try {
        const json = JSON.parse(dataStr);
        const delta = json.choices[0]?.delta?.content || '';
        if (delta) {
          fullText += delta;
          onChunk(delta, fullText);
        }
      } catch (e) {}
    }
  }
  return fullText;
}

async function executeCurrentStage() {
  const proj = state.projects[state.currentProjectId];
  if (!proj || state.isGenerating) return;

  const streamBox = document.getElementById('live-stream-box');
  const wordCountSpan = document.getElementById('output-word-count');
  const indicator = document.getElementById('stream-indicator');

  state.isGenerating = true;
  indicator.style.display = 'inline-block';
  streamBox.innerText = '正在构思并检索科学知识库...';

  const onChunk = (delta, full) => {
    streamBox.innerText = full;
    wordCountSpan.innerText = `${full.length} 字`;
    streamBox.scrollTop = streamBox.scrollHeight;
  };

  try {
    if (proj.stage === 'concept') {
      const kbSnippets = retrieveKnowledge('思想实验 创新 前提 子类型', 3000);
      const prompt = `请为以下科幻项目生成「创作概念」：
书名：《${proj.title}》
题材关键词：${proj.keywords}
故事前提：${proj.premise}
文风基调：${proj.tone}
【方法论知识库】\n${kbSnippets}

输出 Markdown 格式：
# 创作概念
## 一句话卖点 (Logline)
## 核心冲突 (个人/社会/观念三层)
## 主题与思想实验
## 主角简述
## 结局走向与反套路创新点`;

      const res = await chatStream([
        { role: 'system', content: SYSTEM_WRITER },
        { role: 'user', content: prompt }
      ], onChunk);

      proj.concept = res;
      proj.stage = 'world';
    } else if (proj.stage === 'world') {
      const kbSnippets = retrieveKnowledge('世界观 硬性设定 科技原理 物理 天文', 4000);
      const prompt = `基于创作概念，写出完整的「世界观设定与铁律」：
书名：《${proj.title}》
【创作概念】\n${proj.concept}
【科学与世界观参考】\n${kbSnippets}

输出 Markdown 结构：
# 世界观设定
## 一、核心科技与物理图景
## 二、编年史与关键时间线
## 三、空间尺度与社会制度
## 四、硬性设定（编号 W1、W2... 至少10条，作为全书不得违背的铁律）`;

      const res = await chatStream([
        { role: 'system', content: SYSTEM_WRITER },
        { role: 'user', content: prompt }
      ], onChunk);

      proj.world = res;
      proj.stage = 'characters';
    } else if (proj.stage === 'characters') {
      const kbSnippets = retrieveKnowledge('角色 语言指纹 弧光 缺陷', 3000);
      const prompt = `基于创作概念与世界观，建立角色体系：
【世界观】\n${proj.world.slice(0, 3000)}
【角色写作指南】\n${kbSnippets}

输出 Markdown 结构：
# 角色体系
## 主要角色档案 (姓名、身份、欲望、深层需求、缺陷、语言指纹)
## 角色间关系网与核心对抗
## 角色行为一致性铁律 (编号 C1、C2... 至少6条)`;

      const res = await chatStream([
        { role: 'system', content: SYSTEM_WRITER },
        { role: 'user', content: prompt }
      ], onChunk);

      proj.characters = res;
      proj.stage = 'outline';
    } else if (proj.stage === 'outline') {
      const kbSnippets = retrieveKnowledge('三幕式 节奏 悬念 伏笔 钩子', 3500);
      const prompt = `创作全书三幕式大纲，精确包含 ${proj.target_chapters} 章：
【世界观】\n${proj.world.slice(0, 2500)}
【角色】\n${proj.characters.slice(0, 1500)}
【知识库】\n${kbSnippets}

每章严格按照如下格式输出：
## 第1章 章节标题
- 场景与核心任务：
- 冲突与转折：
- 伏笔/回收：
- 章末钩子：
（依次输出第1章至第${proj.target_chapters}章）`;

      const res = await chatStream([
        { role: 'system', content: SYSTEM_WRITER },
        { role: 'user', content: prompt }
      ], onChunk);

      proj.outline = res;
      proj.stage = 'draft';
    } else if (proj.stage === 'draft') {
      // 默认生成第 1 章
      await draftChapter(1);
      return;
    }

    saveProjects();
    updateStudioView();
  } catch (err) {
    alert('生成中断: ' + err.message);
  } finally {
    state.isGenerating = false;
    indicator.style.display = 'none';
  }
}

async function draftChapter(chNum) {
  const proj = state.projects[state.currentProjectId];
  if (!proj || state.isGenerating) return;

  const streamBox = document.getElementById('live-stream-box');
  const wordCountSpan = document.getElementById('output-word-count');
  const indicator = document.getElementById('stream-indicator');

  state.isGenerating = true;
  indicator.style.display = 'inline-block';
  streamBox.innerText = `正在调配本章科学顾问，起草第 ${chNum} 章...`;

  const onChunk = (delta, full) => {
    streamBox.innerText = full;
    wordCountSpan.innerText = `${full.length} 字`;
    streamBox.scrollTop = streamBox.scrollHeight;
  };

  try {
    const prevChText = chNum > 1 ? (proj.chapters[chNum - 1] || '').slice(-800) : '';
    const dynKb = retrieveKnowledge(`第${chNum}章 大纲 ${proj.title}`, 2500);

    const prompt = `请创作第 ${chNum} 章正文。
书名：《${proj.title}》
目标字数：约 ${proj.words_per_chapter || 2500} 字
【世界观铁律】\n${proj.world.slice(0, 2000)}
【大纲参考】\n${proj.outline.slice(0, 3000)}
【上一章结尾衔接】\n${prevChText || '（本书首章开端）'}
【针对性科学与方法论参考】\n${dynKb}

要求：以「# 第${chNum}章 章节名」开头；迅速切入场景冲突，严格遵守世界观硬规则，章末留下悬念钩子。纯 Markdown 正文。`;

    const res = await chatStream([
      { role: 'system', content: SYSTEM_WRITER },
      { role: 'user', content: prompt }
    ], onChunk);

    proj.chapters[chNum] = res;
    saveProjects();
    updateStudioView();
    alert(`✓ 第 ${chNum} 章起草完成（${res.length} 字）！`);
  } catch (err) {
    alert('起草失败: ' + err.message);
  } finally {
    state.isGenerating = false;
    indicator.style.display = 'none';
  }
}

// ---------------------------------------------------------------- 章节目录与阅读视图

function renderChaptersView() {
  const proj = state.projects[state.currentProjectId];
  const container = document.getElementById('chapter-list-container');
  if (!proj) return;

  const chKeys = Object.keys(proj.chapters || {}).map(Number).sort((a, b) => a - b);
  document.getElementById('chapters-summary-badge').innerText = `已完成 ${chKeys.length} / ${proj.target_chapters || 10} 章`;

  if (chKeys.length === 0) {
    container.innerHTML = '<p class="placeholder-text">暂无正文章节，请在「创作」页面起草。</p>';
    return;
  }

  container.innerHTML = chKeys.map(num => {
    const text = proj.chapters[num];
    const firstLine = text.split('\n')[0].replace(/^#+\s*/, '') || `第 ${num} 章`;
    return `
      <div class="chapter-item" onclick="openChapterInReader(${num})">
        <div>
          <div class="chapter-item-title">${firstLine}</div>
          <div class="chapter-item-meta">${text.length} 字</div>
        </div>
        <button class="btn btn-ghost btn-xs">阅读 ▶</button>
      </div>
    `;
  }).join('');
}

window.openChapterInReader = function(num) {
  const proj = state.projects[state.currentProjectId];
  if (!proj || !proj.chapters[num]) return;
  document.querySelector('.nav-item[data-target="view-reader"]').click();
  document.getElementById('reader-chapter-title').innerText = `第 ${num} 章`;
  document.getElementById('reader-content-body').innerText = proj.chapters[num];
};

function renderReaderView() {
  const proj = state.projects[state.currentProjectId];
  if (!proj) return;
  const chKeys = Object.keys(proj.chapters || {}).map(Number).sort((a, b) => a - b);
  if (chKeys.length > 0 && document.getElementById('reader-content-body').innerText.includes('选择章节')) {
    openChapterInReader(chKeys[0]);
  }
}

// ---------------------------------------------------------------- 浏览器端直接导出 (EPUB / HTML / TXT)

function bindExportEvents() {
  document.getElementById('btn-export-txt').addEventListener('click', () => {
    const proj = state.projects[state.currentProjectId];
    if (!proj) return;
    let full = `《${proj.title}》\n\n【创作概念】\n${proj.concept}\n\n`;
    const chKeys = Object.keys(proj.chapters || {}).map(Number).sort((a, b) => a - b);
    chKeys.forEach(k => {
      full += `\n\n${proj.chapters[k]}\n\n`;
    });
    downloadBlob(new Blob([full], { type: 'text/plain;charset=utf-8' }), `${proj.title}.txt`);
  });

  document.getElementById('btn-export-html').addEventListener('click', () => {
    const proj = state.projects[state.currentProjectId];
    if (!proj) return;
    const chKeys = Object.keys(proj.chapters || {}).map(Number).sort((a, b) => a - b);
    let chHtml = '';
    chKeys.forEach(k => {
      chHtml += `<section><h2>第 ${k} 章</h2><pre style="white-space:pre-wrap;font-family:inherit;">${escapeHtml(proj.chapters[k])}</pre></section><hr/>`;
    });
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(proj.title)}</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>body{max-width:800px;margin:20px auto;padding:16px;font-family:sans-serif;line-height:1.8;background:#111;color:#eee;}</style>
      </head><body><h1>${escapeHtml(proj.title)}</h1><p><em>${escapeHtml(proj.premise || '')}</em></p><hr/>${chHtml}</body></html>`;
    downloadBlob(new Blob([html], { type: 'text/html;charset=utf-8' }), `${proj.title}.html`);
  });

  document.getElementById('btn-export-epub').addEventListener('click', () => {
    alert('正在打包 EPUB...（若章节较多需数秒）');
    // EPUB 由纯标准前端打包器导出
    exportEpubInBrowser();
  });
}

function escapeHtml(text) {
  return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------- 纯原生浏览器端 EPUB 3.0 打包实现

function exportEpubInBrowser() {
  const proj = state.projects[state.currentProjectId];
  if (!proj) return;

  const chKeys = Object.keys(proj.chapters || {}).map(Number).sort((a, b) => a - b);
  if (chKeys.length === 0) {
    alert('当前小说尚未生成任何正文章节！');
    return;
  }

  const chaptersData = chKeys.map(k => {
    const raw = proj.chapters[k];
    const firstLine = raw.split('\n')[0].replace(/^#+\s*/, '') || `第 ${k} 章`;
    return {
      title: firstLine,
      text: raw,
    };
  });

  try {
    const epubBytes = generateEpub(proj.title, 'FutureTxt 创作者', proj.premise, chaptersData);
    const blob = new Blob([epubBytes], { type: 'application/epub+zip' });
    downloadBlob(blob, `${proj.title}.epub`);
    alert(`✓ 出版级 EPUB 电子书已生成！可直接导入 Apple Books / 微信读书 / Kindle 阅读。`);
  } catch (err) {
    alert('EPUB 生成失败: ' + err.message);
  }
}

// ---------------------------------------------------------------- 内置示范项目

function seedDefaultProject() {
  const pid = 'proj_sample_01';
  state.projects[pid] = {
    id: pid,
    title: '意识纪元',
    keywords: '近未来,脑机接口,记忆编辑,社会分层',
    premise: '在记忆可以被任意买卖与修剪的近未来新港，一名记忆合规审计官在审查一起巨头猝死案时，发现自己深信不疑的十年记忆全是伪造的。',
    target_chapters: 20,
    words_per_chapter: 3000,
    tone: '冷峻、克制、富有电影画面感',
    stage: 'draft',
    concept: '# 创作概念\n## 一句话卖点\n当记忆能被修改，真相不过是最高权限者的出厂设置。',
    world: '# 世界观设定\n## 硬性设定\nW1: 记忆神经元只支持生物酶编码。\nW2: 脑机端口位于左侧颞叶。',
    characters: '# 角色体系\n林舒：合规审计官。\n何澄：记忆黑市程序员。',
    outline: '## 第1章 记忆残痕\n- 场景：新港雨夜\n- 钩子：死者眼球投影出的代码。',
    chapters: {
      1: '# 第1章 记忆残痕\n\n新港的雨永远带着冷却液的刺鼻味。林舒推开隔离室的大门，冰冷的淡蓝色光带从天花板一直延伸至手术台...',
    },
  };
  saveProjects();
}
