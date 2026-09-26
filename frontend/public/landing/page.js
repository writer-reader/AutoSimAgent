/* AutoSimAgent 落地页 · 回放控制器
   滚动 = 时间轴：7 个空 flow 标记发布进度，本文件把进度映射为台面状态
   （日志行、playhead、面板、真实累计遥测），并在 data-sc-verify-state 上
   发布渲染态签名供验收 harness 采样。引擎（scrollcraft.js）不做任何修改。 */
(function () {
  var R = window.REPLAY;
  if (!R || !R.phases || !R.phases.length) return;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var $ = function (s) { return document.querySelector(s); };
  var surface = $('#surface');
  var logList = $('#log');
  var logBox = $('#logBox');
  var logCount = $('#logCount');
  var capLabel = $('#capLabel');
  var capBody = $('#capBody');
  var play = $('#play');
  var rbBadge = $('#rbBadge');
  var arcs = { L2a: $('#arcL2a'), L2b: $('#arcL2b'), L3: $('#arcL3'), L4: $('#arcL4') };
  var ladder = { L1: $('#ladL1'), L2: $('#ladL2'), L3: $('#ladL3'), L4: $('#ladL4') };
  var cEls = {
    ph: $('[data-c=ph]'), calls: $('[data-c=calls]'), tok: $('[data-c=tok]'),
    crit: $('[data-c=crit]'), el: $('[data-c=el]')
  };
  var NODE_IDS = ['parse', 'knowledge', 'plan', 'generate', 'approval', 'execute', 'verify'];
  var nodeBtns = Array.prototype.map.call(document.querySelectorAll('.g-node'), function (b) { return b; });
  var PANEL_ALIAS = { l4: 'rounds' };
  var RB_TEXT = { L2: 'L2 · 重生成', L3: 'L3 · 重规划', L4: 'L4 · 重抽取' };

  var cards = {};
  Array.prototype.forEach.call(document.querySelectorAll('.p-card'), function (c) {
    cards[c.getAttribute('data-panel')] = c;
  });

  var fmt = function (n) { return formatN(n); };
  function formatN(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  function mmss(s) {
    s = Math.max(0, Math.round(s));
    var m = Math.floor(s / 60);
    return (m < 10 ? '0' + m : m) + ':' + ('0' + (s % 60)).slice(-2);
  }

  /* ── 日志行：boot 两行恒显 + 各阶段行 ─────────────────────────────── */
  var lineEls = [];
  function makeLine(ln, phaseIdx, idxInPhase) {
    var li = document.createElement('li');
    li.className = 'ln ln--' + ln.k;
    var t = document.createElement('span'); t.className = 'ln__t'; t.textContent = ln.t || '';
    var x = document.createElement('span'); x.className = 'ln__x'; x.textContent = ln.x || '';
    li.appendChild(t); li.appendChild(x);
    if (ln.s) { var sp = document.createElement('span'); sp.className = 'ln__s'; sp.textContent = ln.s; li.appendChild(sp); }
    li.__m = {
      phase: phaseIdx, j: idxInPhase, node: ln.node || null, rb: ln.rb || null,
      panel: ln.panel ? (PANEL_ALIAS[ln.panel] || ln.panel) : null, c: ln.c || { calls: 0, tok: 0, crit: 0, el: 0 }
    };
    logList.appendChild(li);
    return li;
  }
  (R.boot || []).forEach(function (b, i) {
    var li = makeLine(b, -1, i);
    li.classList.add('on');
    lineEls.push(li);
  });
  var offsets = [];
  R.phases.forEach(function (ph, k) {
    offsets[k] = lineEls.length;
    ph.lines.forEach(function (ln, j) { lineEls.push(makeLine(ln, k, j)); });
  });

  /* 阶段标记高度 = span × 100vh */
  var markers = Array.prototype.map.call(document.querySelectorAll('.mark'), function (m, k) {
    m.style.height = (R.phases[k].span * 100) + 'vh';
    return m;
  });

  /* 知识卡：真实验收标准 */
  var critList = $('#critList');
  if (critList && R.knowledge) {
    R.knowledge.criteria.forEach(function (c) {
      var li = document.createElement('li');
      var m = document.createElement('span'); m.className = 'm'; m.textContent = c.metric;
      var d = document.createElement('span'); d.className = 'd'; d.textContent = c.desc;
      li.appendChild(m); li.appendChild(d);
      critList.appendChild(li);
    });
  }
  var codeHead = $('#codeHead');
  if (codeHead) codeHead.textContent = R.codeHead || '';

  /* ── 滚动 → 状态 ─────────────────────────────────────────────────── */
  var last = { sig: '', n: -1, node: '', panel: '', ph: -2 };
  var totalLines = 0;
  R.phases.forEach(function (ph) { totalLines += ph.lines.length; });

  function lineThreshold(j, n) { return 0.10 + 0.80 * (j + 1) / (n + 1); }

  function tick() {
    var vh = window.innerHeight;
    var shownTotal = 0;
    var meta = null;          // 最近一条可见行
    var activePh = -1;        // 最近有可见行的阶段
    var anyLineNew = false;
    var changing = false;     // 处于行会继续出现的区间（非平坦区）

    markers.forEach(function (m, k) {
      var r = m.getBoundingClientRect();
      var p = (vh - r.top) / (r.height + vh);
      p = p < 0 ? 0 : p > 1 ? 1 : p;
      var n = R.phases[k].lines.length;
      var vis = Math.min(n, Math.max(0, Math.floor((p - 0.10) * (n + 1) / 0.80 + 1e-9)));
      if (p <= 0.001) vis = 0;
      if (p >= 0.999) vis = n;
      if (p >= lineThreshold(0, n) && p < lineThreshold(n - 1, n)) changing = true;
      for (var j = 0; j < n; j++) {
        var li = lineEls[offsets[k] + j];
        if (j < vis) {
          if (!li.classList.contains('on')) { li.classList.add('on'); anyLineNew = true; }
        } else if (li.classList.contains('on')) {
          li.classList.remove('on');
        }
      }
      if (vis > 0) {
        shownTotal += vis;
        meta = lineEls[offsets[k] + vis - 1].__m;
        activePh = k;
      }
    });

    var mMeta = meta || { node: 'parse', rb: null, panel: 'paper', phase: -1, c: { calls: 0, tok: 0, crit: 0, el: 0 } };

    /* 状态栏：真实累计遥测 */
    var c = mMeta.c;
    cEls.calls.textContent = fmt(c.calls || 0);
    cEls.tok.textContent = fmt(c.tok || 0);
    cEls.crit.textContent = (c.crit && c.crit > 0) ? String(c.crit) : '—';
    cEls.el.textContent = mmss(c.el || 0);
    cEls.ph.textContent = activePh >= 0 ? R.phases[activePh].label : '待机';

    /* 说明区 */
    if (activePh !== last.ph) {
      if (activePh >= 0) {
        capLabel.textContent = R.phases[activePh].label;
        capBody.textContent = R.phases[activePh].caption;
      } else {
        capLabel.textContent = '待机 · 真实运行回放';
        capBody.textContent = 'task_dbe9b64148a5 的完整回放：63 次 LLM 调用 · 318,376 tokens · 20 分 14 秒 · 195 条事件。数字全部来自本仓库事件库，无演示编排。';
      }
      last.ph = activePh;
    }

    /* playhead + 节点态（直接量测节点点位置，避免 flex 取整偏移） */
    var node = mMeta.node || 'parse';
    if (node !== last.node) {
      var idx = NODE_IDS.indexOf(node);
      if (idx >= 0) {
        var dot = nodeBtns[idx].querySelector('.g-dot');
        if (dot) {
          var rowR = play.offsetParent.getBoundingClientRect();
          var dR = dot.getBoundingClientRect();
          play.style.left = (dR.left + dR.width / 2 - rowR.left) + 'px';
        }
        nodeBtns.forEach(function (b, i) {
          b.classList.toggle('is-active', i === idx);
          b.classList.toggle('is-done', i < idx);
        });
      }
      last.node = node;
    }

    /* 回滚边 + 徽标 + 阶梯高亮 */
    var rb = mMeta.rb || null;
    for (var key in arcs) arcs[key].classList.remove('hot');
    for (var lk in ladder) ladder[lk].classList.remove('hot');
    if (rb) {
      var arcKey = rb === 'L2' ? (mMeta.phase <= 2 ? 'L2b' : 'L2a') : rb;
      if (arcs[arcKey]) arcs[arcKey].classList.add('hot');
      if (ladder[rb]) ladder[rb].classList.add('hot');
      rbBadge.textContent = RB_TEXT[rb] || rb;
      rbBadge.classList.add('is-on');
    } else {
      rbBadge.classList.remove('is-on');
    }

    /* 面板切换 */
    var panel = mMeta.panel || last.panel || 'paper';
    if (panel !== last.panel && cards[panel]) {
      if (cards[last.panel]) cards[last.panel].classList.remove('is-on');
      cards[panel].classList.add('is-on');
      last.panel = panel;
    }

    /* 日志跟随 + 计数 */
    if (shownTotal !== last.n) {
      logCount.textContent = shownTotal + ' / ' + totalLines + ' 条';
      if (anyLineNew || shownTotal > last.n) logBox.scrollTop = logBox.scrollHeight;
      last.n = shownTotal;
    }

    /* 验收签名：仅发布真实渲染态；平坦区（行不会变化的滚动区间）显式声明 hold */
    var sig = 'ph:' + (activePh >= 0 ? R.phases[activePh].id : 'boot') +
              '|ln:' + shownTotal + '|node:' + node + '|panel:' + panel + '|rb:' + (rb || '-');
    if (sig !== last.sig) {
      surface.setAttribute('data-sc-verify-state', sig);
      last.sig = sig;
    }
    if (changing) surface.removeAttribute('data-sc-verify-hold');
    else surface.setAttribute('data-sc-verify-hold', 'true');
  }

  var pending = false;
  function onScroll() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; tick(); });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', function () { last.node = ''; onScroll(); }, { passive: true });
  tick();

  /* ── 图即导航：点节点跳到该节点首次激活处 ────────────────────────── */
  function scrollToLine(k, j) {
    var m = markers[k];
    var n = R.phases[k].lines.length;
    var p = lineThreshold(j, n) - 0.02;
    var top = m.getBoundingClientRect().top + window.scrollY;
    var y = top - vh() + p * (m.offsetHeight + vh());
    window.scrollTo({ top: y, behavior: reduce ? 'auto' : 'smooth' });
  }
  function vh() { return window.innerHeight; }
  nodeBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var target = btn.getAttribute('data-node');
      for (var k = 0; k < R.phases.length; k++) {
        var lines = R.phases[k].lines;
        for (var j = 0; j < lines.length; j++) {
          if (lines[j].node === target) { scrollToLine(k, j); return; }
        }
      }
    });
  });

  /* 审批卡的「批准」：跳到 resume 行（真实交互位） */
  var approve = $('#btnApprove');
  if (approve) approve.addEventListener('click', function () {
    var lines = R.phases[1].lines;
    for (var j = 0; j < lines.length; j++) {
      if (lines[j].k === 'resume') { scrollToLine(1, j); return; }
    }
  });

  /* ── 收束表单：本地演示队列 ──────────────────────────────────────── */
  var qform = $('#qform');
  if (qform) qform.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var input = $('#qin');
    var v = (input.value || '').trim();
    if (!v) { input.focus(); return; }
    var h = 5381;
    for (var i = 0; i < v.length; i++) { h = ((h * 33) ^ v.charCodeAt(i)) >>> 0; }
    var out = $('#qout');
    out.hidden = false;
    out.textContent = '';
    var card = document.createElement('div'); card.className = 'q-card';
    var qid = document.createElement('span'); qid.className = 'qid'; qid.textContent = 'task_' + h.toString(16).padStart(10, '0');
    var qin = document.createElement('span'); qin.className = 'qin'; qin.textContent = v;
    var chip = document.createElement('span'); chip.className = 'chip chip--queue'; chip.textContent = '排队中（演示）';
    card.appendChild(qid); card.appendChild(qin); card.appendChild(chip);
    var hint = document.createElement('p'); hint.className = 'q-hint';
    hint.textContent = '已登记到本地演示队列。启动 python run_backend.py 后，任务进入真实流水线；也可以在';
    var a = document.createElement('a'); a.href = 'http://localhost:5173'; a.target = '_blank'; a.rel = 'noopener'; a.textContent = '工作台';
    hint.appendChild(a);
    hint.appendChild(document.createTextNode('里直接上传 PDF。'));
    out.appendChild(card); out.appendChild(hint);
  });
})();
