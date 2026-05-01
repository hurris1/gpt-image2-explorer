// search.js — Search, filter, and pagination logic

function getFilteredItems() {
  const { items, activeSource, activeCategory, searchQuery } = AppState;

  return items.filter(item => {
    // Source filter
    if (activeSource !== 'all' && item.source !== activeSource) return false;

    // Category filter
    if (activeCategory && item.category !== activeCategory) return false;

    // Search
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const haystack = [
        item.title,
        item.title_zh,
        item.description,
        item.description_zh,
        item.prompt_en,
        item.prompt_zh,
        (item.tags || []).join(' '),
        item.category_en,
        item.category_zh,
      ].join(' ').toLowerCase();
      if (!haystack.includes(q)) return false;
    }

    return true;
  });
}

function getPageItems(page, pageSize) {
  const filtered = getFilteredItems();
  const start = (page - 1) * pageSize;
  return {
    items: filtered.slice(start, start + pageSize),
    total: filtered.length,
    hasMore: start + pageSize < filtered.length,
  };
}

function getCategoryCounts() {
  const counts = {};
  for (const cat of AppState.categories) {
    counts[cat.id] = 0;
  }
  for (const item of AppState.items) {
    if (counts[item.category] !== undefined) {
      counts[item.category]++;
    }
  }
  return counts;
}

function getSourceCounts() {
  const counts = { all: AppState.items.length, evolinkai: 0, 'gpt-image2': 0 };
  for (const item of AppState.items) {
    if (counts[item.source] !== undefined) {
      counts[item.source]++;
    }
  }
  return counts;
}

function highlightText(text, query) {
  if (!query) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(${escaped})`, 'gi');
  return text.replace(re, '<mark>$1</mark>');
}

let searchTimer = null;
function debouncedSearch(callback, delay = 300) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(callback, delay);
}
