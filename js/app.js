// app.js — Main application

// ---- Helpers ----
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
function escapeHTML(str) { const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }

// ---- Init ----
document.addEventListener('DOMContentLoaded', async () => {
  await loadData();
  renderAll();
  bindEvents();
});

function renderAll() {
  updateCounts();
  renderSourceFilters();
  renderCategoryFilters();
  renderCards();
  updateI18nUI();
}

// ---- Counts ----
function updateCounts() {
  $('#totalCount').textContent = `${AppState.items.length} ${t('totalPrompts')}`;
  const sc = getSourceCounts();
  $('#countAll').textContent = sc.all;
  $('#countEvo').textContent = sc.evolinkai;
  $('#countGpt2').textContent = sc['gpt-image2'];
}

// ---- Source Filters ----
function renderSourceFilters() {
  // Already in HTML, just update counts
}

// ---- Category Filters ----
function renderCategoryFilters() {
  const container = $('#categoryFilters');
  const counts = getCategoryCounts();
  const lang = AppState.lang;

  container.innerHTML = AppState.categories.map(cat => {
    const label = lang === 'zh' ? cat.zh : cat.en;
    const count = counts[cat.id] || 0;
    const active = AppState.activeCategory === cat.id ? ' active' : '';
    return `
      <button class="filter-item${active}" data-category="${cat.id}">
        <span class="filter-name">${label}</span>
        <span class="filter-count">${count}</span>
      </button>
    `;
  }).join('');
}

// ---- Cards ----
function renderCards() {
  AppState.currentPage = 1;
  renderPage();
}

function renderPage() {
  const { items, total, hasMore } = getPageItems(AppState.currentPage, AppState.pageSize);
  const grid = $('#cardGrid');
  const lang = AppState.lang;
  const query = AppState.searchQuery;

  if (AppState.currentPage === 1) {
    grid.innerHTML = '';
  }

  if (total === 0 && AppState.currentPage === 1) {
    $('#emptyState').classList.remove('hidden');
    $('#pagination').classList.add('hidden');
  } else {
    $('#emptyState').classList.add('hidden');
    if (hasMore) {
      $('#pagination').classList.remove('hidden');
      $('#loadMore').textContent = t('loadMore');
    } else {
      $('#pagination').classList.add('hidden');
    }
  }

  for (const item of items) {
    const card = createCard(item, lang, query);
    grid.appendChild(card);
  }

  updateResultInfo(total);
  lazyLoadImages();
}

function createCard(item, lang, query) {
  const div = document.createElement('div');
  div.className = 'card';
  div.dataset.id = item.id;

  const catLabel = lang === 'zh' ? item.category_zh : item.category_en;
  const title = (lang === 'zh' && item.title_zh) ? item.title_zh : (item.title || item.description);
  const desc = (lang === 'zh' && item.description_zh) ? item.description_zh : (item.description || '');
  const titleHtml = highlightText(title, query);
  const descHtml = highlightText(desc, query);

  const imageHtml = item.image
    ? `<img class="card-image" data-src="images/${item.image}" src="" alt="${escapeHTML(title)}" loading="lazy">`
    : `<div class="card-image-placeholder">🖼</div>`;

  div.innerHTML = `
    ${imageHtml}
    <div class="card-body">
      <h3 class="card-title">${titleHtml}</h3>
      <p class="card-desc">${descHtml}</p>
    </div>
    <div class="card-footer">
      <span class="card-category">${catLabel}</span>
      <button class="card-copy" data-zh="复制" data-en="Copy" title="Copy prompt">📋 <span>${t('copy')}</span></button>
    </div>
  `;

  // Click card → open modal
  div.querySelector('.card-body').addEventListener('click', (e) => {
    // Don't open modal if clicking the copy button
    if (e.target.closest('.card-copy')) return;
    openModal(item);
  });
  div.querySelector('.card-image')?.addEventListener('click', () => openModal(item));
  div.querySelector('.card-image-placeholder')?.addEventListener('click', () => openModal(item));

  // Copy button
  div.querySelector('.card-copy').addEventListener('click', (e) => {
    e.stopPropagation();
    copyPrompt(item);
    const btn = e.currentTarget;
    btn.classList.add('copied');
    btn.querySelector('span').textContent = t('copied');
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.querySelector('span').textContent = t('copy');
    }, 1500);
  });

  return div;
}

function updateResultInfo(total) {
  const info = $('#resultInfo');
  if (AppState.searchQuery || AppState.activeCategory || AppState.activeSource !== 'all') {
    info.textContent = `${total} results`;
  } else {
    info.textContent = '';
  }
}

// ---- Image Retry ----
function loadImageWithRetry(img, src, retries = 3) {
  img.src = src;
  img._retries = retries;
  img.addEventListener('error', function onErr() {
    if (img._retries > 0) {
      img._retries--;
      const backoff = (3 - img._retries) * 300;
      setTimeout(() => { img.src = src; }, backoff);
    } else {
      img.removeEventListener('error', onErr);
    }
  });
}

// ---- Lazy Loading ----
function lazyLoadImages() {
  const imgs = $$('.card-image[data-src]');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target;
        loadImageWithRetry(img, img.dataset.src);
        img.removeAttribute('data-src');
        observer.unobserve(img);
      }
    });
  }, { rootMargin: '200px' });

  imgs.forEach(img => observer.observe(img));
}

// ---- Modal ----
function openModal(item) {
  const lang = AppState.lang;

  // Store current item for tab switching
  $('#modalOverlay')._currentItem = item;

  const modalTitle = (lang === 'zh' && item.title_zh) ? item.title_zh : (item.title || item.description);

  $('#modalImg').src = item.image ? `images/${item.image}` : '';
  $('#modalImg').alt = modalTitle;
  $('#modalImage').style.display = item.image ? '' : 'none';

  $('#modalTitle').textContent = modalTitle;
  $('#modalCategory').textContent = lang === 'zh' ? item.category_zh : item.category_en;
  $('#modalSource').textContent = item.source;

  const authorHtml = item.author?.link
    ? `<a href="${item.author.link}" target="_blank">${item.author.name}</a>`
    : (item.author?.name || '');
  $('#modalAuthor').innerHTML = authorHtml;

  // Prompt tabs
  $('#modalPrompt').textContent = item.prompt_en || item.prompt_zh || '';
  const tabEn = $$('.modal-tab[data-tab="en"]')[0];
  const tabZh = $$('.modal-tab[data-tab="zh"]')[0];

  if (item.prompt_zh && item.prompt_en) {
    tabZh.classList.remove('zh-hidden');
    // Default to current language
    $$('.modal-tab').forEach(t => t.classList.remove('active'));
    if (lang === 'zh') {
      tabZh.classList.add('active');
      $('#modalPrompt').textContent = item.prompt_zh;
    } else {
      tabEn.classList.add('active');
      $('#modalPrompt').textContent = item.prompt_en;
    }
  } else if (item.prompt_zh) {
    tabEn.classList.add('zh-hidden');
    tabZh.classList.remove('zh-hidden');
    tabZh.classList.add('active');
    $('#modalPrompt').textContent = item.prompt_zh;
  } else {
    tabZh.classList.add('zh-hidden');
    tabEn.classList.add('active');
    $('#modalPrompt').textContent = item.prompt_en;
  }

  // Source link
  const linkEl = $('#modalLink');
  if (item.source_link) {
    linkEl.href = item.source_link;
    linkEl.style.display = '';
  } else {
    linkEl.style.display = 'none';
  }
  linkEl.textContent = t('viewSource');

  // Reset copy button
  $('#modalCopyBtn').classList.remove('copied');
  $('#modalCopyBtn').textContent = t('copy');

  $('#modalOverlay').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  $('#modalOverlay').classList.add('hidden');
  document.body.style.overflow = '';
  $('#modalImg').src = '';
}

// ---- Copy ----
function copyPrompt(item) {
  const lang = AppState.lang;
  const activeTab = document.querySelector('.modal-tab.active');
  let text;

  if (activeTab && activeTab.dataset.tab === 'zh' && item.prompt_zh) {
    text = item.prompt_zh;
  } else {
    text = item.prompt_en || item.prompt_zh || '';
  }

  navigator.clipboard.writeText(text).then(() => {
    showToast(t('copied'));
  }).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(t('copied'));
  });
}

function copyModalPrompt() {
  const text = $('#modalPrompt').textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = $('#modalCopyBtn');
    btn.classList.add('copied');
    btn.textContent = t('copied');
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.textContent = t('copy');
    }, 1500);
    showToast(t('copied'));
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(t('copied'));
  });
}

// ---- Toast ----
function showToast(msg) {
  const toast = $('#toast');
  toast.textContent = msg;
  toast.classList.remove('hidden');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.add('hidden'), 1800);
}

// ---- I18N Update ----
function updateI18nUI() {
  const lang = AppState.lang;

  // Update search placeholder
  const searchInput = $('#searchInput');
  searchInput.placeholder = lang === 'zh'
    ? searchInput.dataset.zhPlaceholder
    : searchInput.dataset.enPlaceholder;

  // Update load more text
  const loadMore = $('#loadMore');
  loadMore.textContent = t('loadMore');

  // Update sidebar titles
  $$('[data-zh]').forEach(el => {
    if (el.tagName === 'INPUT') return; // handled above
    const text = el.dataset[lang];
    if (text) el.textContent = text;
  });

  // Copy buttons
  $$('.card-copy span').forEach(el => el.textContent = t('copy'));

  // Re-render category filters
  renderCategoryFilters();
  // Re-render cards to update labels
  AppState.currentPage = 1;
  $('#cardGrid').innerHTML = '';
  renderPage();

  // Update badge texts
  updateBadgeTexts();
}

function updateBadgeTexts() {
  const lang = AppState.lang;
  const badgeSource = $('#badgeSource');
  if (AppState.activeSource !== 'all' && badgeSource.style.display !== 'none') {
    badgeSource.querySelector('.badge-text').textContent = AppState.activeSource;
  }
  const badgeCat = $('#badgeCategory');
  if (AppState.activeCategory && badgeCat.style.display !== 'none') {
    const cat = AppState.categories.find(c => c.id === AppState.activeCategory);
    if (cat) {
      badgeCat.querySelector('.badge-text').textContent = lang === 'zh' ? cat.zh : cat.en;
    }
  }
}

// ---- Events ----
function bindEvents() {
  // Language switch
  $('#langSwitch').addEventListener('click', () => {
    AppState.lang = AppState.lang === 'zh' ? 'en' : 'zh';
    $('#langSwitch').textContent = AppState.lang === 'zh' ? 'EN' : '中文';
    updateI18nUI();
  });

  // Search
  $('#searchInput').addEventListener('input', () => {
    const val = $('#searchInput').value.trim();
    $('#searchClear').classList.toggle('hidden', !val);
    debouncedSearch(() => {
      AppState.searchQuery = val;
      AppState.currentPage = 1;
      $('#cardGrid').innerHTML = '';
      renderPage();
    });
  });

  $('#searchClear').addEventListener('click', () => {
    $('#searchInput').value = '';
    $('#searchClear').classList.add('hidden');
    AppState.searchQuery = '';
    AppState.currentPage = 1;
    $('#cardGrid').innerHTML = '';
    renderPage();
    $('#searchInput').focus();
  });

  // Enter key in search
  $('#searchInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      clearTimeout(searchTimer);
      AppState.searchQuery = $('#searchInput').value.trim();
      AppState.currentPage = 1;
      $('#cardGrid').innerHTML = '';
      renderPage();
    }
  });

  // Source filter
  $('#sourceFilters').addEventListener('click', (e) => {
    const btn = e.target.closest('.filter-item');
    if (!btn) return;
    $('#sourceFilters').querySelectorAll('.filter-item').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    AppState.activeSource = btn.dataset.source;
    AppState.currentPage = 1;
    updateBadge('badgeSource', AppState.activeSource !== 'all', AppState.activeSource);
    $('#cardGrid').innerHTML = '';
    renderPage();
  });

  // Category filter
  $('#categoryFilters').addEventListener('click', (e) => {
    const btn = e.target.closest('.filter-item');
    if (!btn) return;
    const isActive = btn.classList.contains('active');
    // Toggle
    $('#categoryFilters').querySelectorAll('.filter-item').forEach(b => b.classList.remove('active'));
    if (isActive) {
      AppState.activeCategory = null;
      updateBadge('badgeCategory', false, '');
    } else {
      btn.classList.add('active');
      AppState.activeCategory = btn.dataset.category;
      updateBadge('badgeCategory', true, AppState.activeCategory);
    }
    AppState.currentPage = 1;
    $('#cardGrid').innerHTML = '';
    renderPage();
  });

  // Badge remove
  $('#badgeSource').querySelector('.badge-remove').addEventListener('click', () => {
    AppState.activeSource = 'all';
    $('#sourceFilters').querySelectorAll('.filter-item').forEach(b => b.classList.remove('active'));
    $('#sourceFilters').querySelector('[data-source="all"]').classList.add('active');
    updateBadge('badgeSource', false, '');
    AppState.currentPage = 1;
    $('#cardGrid').innerHTML = '';
    renderPage();
  });

  $('#badgeCategory').querySelector('.badge-remove').addEventListener('click', () => {
    AppState.activeCategory = null;
    $('#categoryFilters').querySelectorAll('.filter-item').forEach(b => b.classList.remove('active'));
    updateBadge('badgeCategory', false, '');
    AppState.currentPage = 1;
    $('#cardGrid').innerHTML = '';
    renderPage();
  });

  function updateBadge(badgeId, show, text) {
    const badge = $(`#${badgeId}`);
    if (show) {
      badge.style.display = '';
      badge.querySelector('.badge-text').textContent = text;
    } else {
      badge.style.display = 'none';
    }
  }

  // Load more
  $('#loadMore').addEventListener('click', () => {
    AppState.currentPage++;
    renderPage();
  });

  // Infinite scroll
  let scrollTimer;
  window.addEventListener('scroll', () => {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      const { hasMore } = getPageItems(AppState.currentPage, AppState.pageSize);
      if (!hasMore) return;
      const scrollBottom = window.innerHeight + window.scrollY;
      const docBottom = document.documentElement.offsetHeight;
      if (docBottom - scrollBottom < 400) {
        AppState.currentPage++;
        renderPage();
      }
    }, 150);
  });

  // Modal close
  $('#modalClose').addEventListener('click', closeModal);
  $('#modalOverlay').addEventListener('click', (e) => {
    if (e.target === $('#modalOverlay')) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  // Modal copy
  $('#modalCopyBtn').addEventListener('click', copyModalPrompt);

  // Modal tabs
  $$('.modal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.modal-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      // Find current item
      const modalId = $('#modalTitle').textContent;
      // We need the current item reference - store on modal
      const item = $('#modalOverlay')._currentItem;
      if (item) {
        const prompt = tab.dataset.tab === 'zh' ? (item.prompt_zh || item.prompt_en) : (item.prompt_en || item.prompt_zh);
        $('#modalPrompt').textContent = prompt || '';
      }
    });
  });

  // Sidebar toggle
  $('#sidebarToggle').addEventListener('click', () => {
    $('#sidebar').classList.toggle('collapsed');
  });

}
