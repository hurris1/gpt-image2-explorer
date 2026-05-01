// data.js — Data loading and state management

const AppState = {
  items: [],
  categories: [],
  currentPage: 1,
  pageSize: 24,
  lang: 'zh',
  activeSource: 'all',
  activeCategory: null,
  searchQuery: '',
};

const I18N = {
  zh: {
    totalPrompts: '条提示词',
    allSources: '全部',
    searchPlaceholder: '搜索提示词、标题、标签...',
    loadMore: '加载更多',
    noResults: '没有找到匹配的提示词',
    copy: '复制',
    copied: '已复制',
    viewSource: '查看原始来源 →',
    categories: '分类',
    source: '数据来源',
    collapse: '收起侧边栏',
  },
  en: {
    totalPrompts: 'prompts',
    allSources: 'All',
    searchPlaceholder: 'Search prompts, titles, tags...',
    loadMore: 'Load More',
    noResults: 'No matching prompts found',
    copy: 'Copy',
    copied: 'Copied!',
    viewSource: 'View Source →',
    categories: 'Categories',
    source: 'Source',
    collapse: 'Collapse sidebar',
  }
};

function t(key) {
  return I18N[AppState.lang][key] || key;
}

async function loadData() {
  try {
    const resp = await fetch('data/prompts.json');
    const data = await resp.json();
    AppState.items = data.items || [];
    AppState.categories = data.categories || [];
    return AppState;
  } catch (err) {
    console.error('Failed to load prompts:', err);
    AppState.items = [];
    return AppState;
  }
}
