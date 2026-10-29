/**
 * Rankaura SEO Keyword Explorer — Client Controller
 * Connects UI components to FastAPI backend endpoints.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const mainSearchForm = document.getElementById('main-search-form');
  const mainSearchInput = document.getElementById('main-search-input');
  const mainSubmitBtn = document.getElementById('main-submit-btn');
  const mainSpinner = document.getElementById('main-spinner');
  const clearSearchBtn = document.getElementById('clear-search-btn');

  const navSearchForm = document.getElementById('nav-search-form');
  const navSearchInput = document.getElementById('nav-search-input');
  const navDownloadCsv = document.getElementById('nav-download-csv');
  const resultsDownloadCsv = document.getElementById('results-download-csv');

  const loadingCard = document.getElementById('loading-card');
  const errorCard = document.getElementById('error-card');
  const errorMessage = document.getElementById('error-message');
  const errorRetryBtn = document.getElementById('error-retry-btn');

  const resultsContainer = document.getElementById('results-container');
  const resultsTopicName = document.getElementById('results-topic-name');
  const changeTopicBtn = document.getElementById('change-topic-btn');
  const highCompGrid = document.getElementById('high-comp-grid');
  const mediumCompGrid = document.getElementById('medium-comp-grid');

  const tableFilterInput = document.getElementById('table-filter-input');
  const filterTabs = document.querySelectorAll('.tab-btn');
  const keywordsTableTbody = document.getElementById('keywords-table-tbody');
  const paginationInfo = document.getElementById('pagination-info');
  const paginationNav = document.getElementById('pagination-nav');

  const topicsAccordionList = document.getElementById('topics-accordion-list');
  const topicChips = document.querySelectorAll('.topic-chip');

  // Application State
  let isSearching = false;
  let currentSeed = '';
  let allKeywords = [];
  let filteredKeywords = [];
  let currentTab = 'all';
  let currentPage = 1;
  const pageSize = 10;

  // ── Input Synchronization & Clear Button ───────────────────

  function syncSearchInputs(value) {
    if (mainSearchInput) mainSearchInput.value = value;
    if (navSearchInput) navSearchInput.value = value;
    toggleClearButton(value);
  }

  function toggleClearButton(val) {
    if (!clearSearchBtn) return;
    clearSearchBtn.style.display = val.trim().length > 0 ? 'inline-block' : 'none';
  }

  if (mainSearchInput) {
    mainSearchInput.addEventListener('input', (e) => {
      syncSearchInputs(e.target.value);
    });
  }

  if (navSearchInput) {
    navSearchInput.addEventListener('input', (e) => {
      syncSearchInputs(e.target.value);
    });
  }

  if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', () => {
      syncSearchInputs('');
      if (mainSearchInput) mainSearchInput.focus();
    });
  }

  // Topic suggestion chips
  topicChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const topic = chip.dataset.topic;
      if (!topic) return;
      syncSearchInputs(topic);
      executeSearch(topic);
    });
  });

  // Change topic button
  if (changeTopicBtn) {
    changeTopicBtn.addEventListener('click', () => {
      if (mainSearchInput) {
        mainSearchInput.focus();
        mainSearchInput.select();
      }
      const hero = document.getElementById('hero-welcome-section');
      if (hero) hero.scrollIntoView({ behavior: 'smooth' });
    });
  }

  // Retry button
  if (errorRetryBtn) {
    errorRetryBtn.addEventListener('click', () => {
      const seed = (mainSearchInput && mainSearchInput.value.trim()) || currentSeed;
      if (seed) executeSearch(seed);
    });
  }

  // Form Submissions
  if (mainSearchForm) {
    mainSearchForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const seed = mainSearchInput.value.trim();
      if (!seed) return;
      executeSearch(seed);
    });
  }

  if (navSearchForm) {
    navSearchForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const seed = navSearchInput.value.trim();
      if (!seed) return;
      executeSearch(seed);
    });
  }

  // ── Core Search Execution ──────────────────────────────────

  async function executeSearch(seed) {
    if (isSearching) return;
    isSearching = true;
    currentSeed = seed;
    syncSearchInputs(seed);

    // UI State: Loading
    setLoadingState(true);
    hideError();

    try {
      const formData = new FormData();
      formData.append('seed', seed);

      const response = await fetch('/api/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server returned error (${response.status})`);
      }

      const res = await response.json();
      if (!res || !res.data) {
        throw new Error('Invalid response structure received from server.');
      }

      renderResults(res);

    } catch (err) {
      console.error('Search failed:', err);
      showError(err.message || 'Unable to complete keyword exploration.');
    } finally {
      isSearching = false;
      setLoadingState(false);
    }
  }

  function setLoadingState(loading) {
    if (loading) {
      if (loadingCard) loadingCard.style.display = 'flex';
      if (mainSubmitBtn) mainSubmitBtn.disabled = true;
      if (mainSpinner) mainSpinner.style.display = 'inline-block';
      const btnText = mainSubmitBtn ? mainSubmitBtn.querySelector('.btn-text') : null;
      if (btnText) btnText.textContent = 'Exploring...';
    } else {
      if (loadingCard) loadingCard.style.display = 'none';
      if (mainSubmitBtn) mainSubmitBtn.disabled = false;
      if (mainSpinner) mainSpinner.style.display = 'none';
      const btnText = mainSubmitBtn ? mainSubmitBtn.querySelector('.btn-text') : null;
      if (btnText) btnText.textContent = 'Explore';
    }
  }

  function showError(msg) {
    if (errorCard) errorCard.style.display = 'flex';
    if (errorMessage) errorMessage.textContent = msg;
    if (resultsContainer) resultsContainer.style.display = 'none';
  }

  function hideError() {
    if (errorCard) errorCard.style.display = 'none';
  }

  // ── Render Complete Results ────────────────────────────────

  function renderResults(payload) {
    const data = payload.data;
    if (resultsContainer) resultsContainer.style.display = 'block';

    // 1. Topic Title
    if (resultsTopicName) {
      resultsTopicName.textContent = payload.seed || currentSeed;
    }

    // Enable CSV buttons
    if (navDownloadCsv) navDownloadCsv.classList.remove('disabled');
    if (resultsDownloadCsv) resultsDownloadCsv.classList.remove('disabled');

    // 2. Render Categorized Keywords
    renderRecommendations(data.high_competition_5 || [], highCompGrid);
    renderRecommendations(data.medium_competition_5 || [], mediumCompGrid);

    // 3. Flatten all queries for Related Keywords table
    extractAndPrepareKeywords(data.clusters || []);

    // 4. Render Related Topics Accordions
    renderTopicsAccordions(data.clusters || []);

    // Reset table filter & pagination
    if (tableFilterInput) tableFilterInput.value = '';
    currentTab = 'all';
    filterTabs.forEach(t => t.classList.toggle('active', t.dataset.tab === 'all'));
    currentPage = 1;
    applyTableFilters();

    // Smooth scroll down to results
    if (resultsContainer) {
      resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  // ── Render Recommended 5 Keywords Grid ─────────────────────

  function renderRecommendations(items, grid) {
    if (!grid) return;
    grid.innerHTML = '';

    if (!items || items.length === 0) {
      recommendationsGrid.innerHTML = `
        <div style="grid-column: 1/-1; padding: 2rem; text-align: center; color: var(--text-secondary);">
          No specific recommendations available for this topic.
        </div>
      `;
      return;
    }

    items.forEach((item, idx) => {
      const slotNum = String(item.slot || idx + 1).padStart(2, '0');
      const card = document.createElement('div');
      card.className = 'rec-card';

      // Qualitative activity label
      const activityText = item.activity ? `${item.activity} Search Activity` : 'High Search Activity';
      const activityClass = (item.activity || '').toLowerCase().includes('moderate') ? 'moderate' : 'high';

      // Competition pill
      const diffText = item.difficulty || 'Medium Competition';
      let diffClass = 'medium';
      if (diffText.toLowerCase().includes('low')) diffClass = 'low';
      else if (diffText.toLowerCase().includes('high')) diffClass = 'high';

      card.innerHTML = `
        <div class="rec-card-top">
          <span class="rec-slot-badge">${slotNum}</span>
          <span class="rec-placement-label">${escapeHtml(item.placement || item.role)}</span>
        </div>
        <div class="rec-keyword-text">${escapeHtml(item.keyword)}</div>
        <div class="rec-purpose-tip">${escapeHtml(item.purpose || '')}</div>
        <div class="rec-badges-row">
          <span class="pill-activity ${activityClass}">${escapeHtml(activityText)}</span>
          <span class="pill-competition ${diffClass}">${escapeHtml(diffText)}</span>
        </div>
        <div class="rec-card-actions">
          <button type="button" class="btn-rec-copy" onclick="copyText('${escapeJs(item.keyword)}', this)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>Copy keyword</span>
          </button>
          <button type="button" class="btn-view-related" onclick="filterRelatedTo('${escapeJs(item.keyword)}')">
            View related keywords →
          </button>
        </div>
      `;

      grid.appendChild(card);
    });
  }

  // ── Flatten Keywords for Table ─────────────────────────────

  function extractAndPrepareKeywords(clusters) {
    const map = new Map();

    clusters.forEach(cluster => {
      if (cluster.primary_keyword && cluster.primary_keyword.keyword) {
        const pk = cluster.primary_keyword;
        if (!map.has(pk.keyword.toLowerCase())) {
          map.set(pk.keyword.toLowerCase(), createKeywordItem(pk, true));
        }
      }
      (cluster.supporting_keywords || []).forEach(sk => {
        if (sk.keyword && !map.has(sk.keyword.toLowerCase())) {
          map.set(sk.keyword.toLowerCase(), createKeywordItem(sk, false));
        }
      });
    });

    allKeywords = Array.from(map.values());
  }

  function createKeywordItem(kwObj, isPrimary) {
    const text = kwObj.keyword;
    const comps = kwObj.components || {};
    const demand = comps.demand !== undefined ? comps.demand : 0.5;
    const competition = comps.competition !== undefined ? comps.competition : 0.5;
    const wc = kwObj.word_count || text.split(' ').length;

    // Qualitative Search Activity
    let activity = 'High';
    let activityClass = 'green';
    if (demand < 0.45) {
      activity = 'Moderate';
      activityClass = 'amber';
    }

    // Qualitative Competition
    let compLabel = 'Low';
    let compClass = 'green';
    if (wc <= 2 || competition >= 0.65) {
      compLabel = 'High';
      compClass = 'red';
    } else if (wc === 3 || competition >= 0.45) {
      compLabel = 'Medium';
      compClass = 'grey';
    }

    // Trend label (qualitative indicator)
    const isTrending = isPrimary || demand >= 0.55 || wc >= 4;

    return {
      keyword: text,
      activity: activity,
      activityClass: activityClass,
      competition: compLabel,
      compClass: compClass,
      isTrending: isTrending,
      isHighActivity: demand >= 0.50,
    };
  }

  // ── Table Filtering & Pagination ───────────────────────────

  function applyTableFilters() {
    const searchFilter = (tableFilterInput ? tableFilterInput.value : '').trim().toLowerCase();

    filteredKeywords = allKeywords.filter(item => {
      // Tab filter
      if (currentTab === 'trending' && !item.isTrending) return false;
      if (currentTab === 'high-activity' && !item.isHighActivity) return false;

      // Text query search
      if (searchFilter && !item.keyword.toLowerCase().includes(searchFilter)) {
        return false;
      }
      return true;
    });

    currentPage = 1;
    renderTablePage();
  }

  function renderTablePage() {
    if (!keywordsTableTbody) return;
    keywordsTableTbody.innerHTML = '';

    const total = filteredKeywords.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;

    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, total);
    const pageItems = filteredKeywords.slice(startIdx, endIdx);

    if (pageItems.length === 0) {
      keywordsTableTbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; padding: 2.5rem; color: var(--text-secondary);">
            No matching keywords found. Try clearing your filter.
          </td>
        </tr>
      `;
      if (paginationInfo) paginationInfo.textContent = 'Showing 0 keywords';
      if (paginationNav) paginationNav.innerHTML = '';
      return;
    }

    pageItems.forEach(item => {
      const tr = document.createElement('tr');
      const trendContent = item.isTrending 
        ? `<span class="trend-indicator">↗ Trending</span>` 
        : `<span style="color: var(--text-muted); font-size: 0.9rem;">—</span>`;

      tr.innerHTML = `
        <td class="kw-title-cell">${escapeHtml(item.keyword)}</td>
        <td>
          <span class="pill-sm ${item.activityClass}">${escapeHtml(item.activity)}</span>
        </td>
        <td>
          <span class="pill-sm ${item.compClass}">${escapeHtml(item.competition)}</span>
        </td>
        <td>${trendContent}</td>
        <td style="text-align: right;">
          <button type="button" class="btn-table-copy" onclick="copyText('${escapeJs(item.keyword)}', this)" title="Copy keyword">
            Copy
          </button>
        </td>
      `;
      keywordsTableTbody.appendChild(tr);
    });

    // Pagination summary
    if (paginationInfo) {
      paginationInfo.textContent = `Showing ${startIdx + 1}–${endIdx} of ${total} keywords`;
    }

    // Pagination controls
    renderPaginationControls(totalPages);
  }

  function renderPaginationControls(totalPages) {
    if (!paginationNav) return;
    paginationNav.innerHTML = '';
    if (totalPages <= 1) return;

    // Prev button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn';
    prevBtn.innerHTML = '‹';
    prevBtn.disabled = currentPage === 1;
    prevBtn.onclick = () => {
      if (currentPage > 1) {
        currentPage--;
        renderTablePage();
      }
    };
    paginationNav.appendChild(prevBtn);

    // Numbered pages (up to 5 buttons)
    const maxButtons = 5;
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    if (endPage - startPage < maxButtons - 1) {
      startPage = Math.max(1, endPage - maxButtons + 1);
    }

    for (let p = startPage; p <= endPage; p++) {
      const btn = document.createElement('button');
      btn.className = `page-btn ${p === currentPage ? 'active' : ''}`;
      btn.textContent = p;
      btn.onclick = () => {
        currentPage = p;
        renderTablePage();
      };
      paginationNav.appendChild(btn);
    }

    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn';
    nextBtn.innerHTML = '›';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.onclick = () => {
      if (currentPage < totalPages) {
        currentPage++;
        renderTablePage();
      }
    };
    paginationNav.appendChild(nextBtn);
  }

  // Live filter input
  if (tableFilterInput) {
    tableFilterInput.addEventListener('input', applyTableFilters);
  }

  // Filter tabs
  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentTab = tab.dataset.tab;
      applyTableFilters();
    });
  });

  // ── Render Related Topics (Accordions) ─────────────────────

  function renderTopicsAccordions(clusters) {
    if (!topicsAccordionList) return;
    topicsAccordionList.innerHTML = '';

    if (!clusters || clusters.length === 0) {
      topicsAccordionList.innerHTML = `
        <div style="padding: 1.5rem; text-align: center; color: var(--text-secondary); font-size: 0.85rem;">
          No related topic clusters generated.
        </div>
      `;
      return;
    }

    // Topic icons palette
    const icons = ['🎨', '🛠️', '🏠', '💡', '📈', '🔍', '⚙️', '📊', '💼', '🚀'];

    clusters.slice(0, 10).forEach((c, idx) => {
      const icon = icons[idx % icons.length];
      const primaryText = (c.primary_keyword && c.primary_keyword.keyword) || c.cluster_topic;
      const topicTitle = formatTopicName(c.cluster_topic || primaryText);
      const isExpanded = idx === 0 || idx === 1; // First two expanded by default

      const card = document.createElement('div');
      card.className = `topic-group-card ${isExpanded ? 'expanded' : ''}`;

      const supporting = c.supporting_keywords || [];
      const tagsHtml = supporting.length > 0 
        ? supporting.map(s => `
            <span class="keyword-tag-pill" onclick="copyTagText('${escapeJs(s.keyword)}', this)" title="Click to copy">
              ${escapeHtml(s.keyword)}
            </span>
          `).join('')
        : `<span style="font-size: 0.8rem; color: var(--text-secondary);">No additional supporting queries.</span>`;

      card.innerHTML = `
        <div class="topic-group-header">
          <div class="topic-header-left">
            <div class="topic-title-row">
              <span>${icon}</span>
              <span class="topic-name">${escapeHtml(topicTitle)}</span>
            </div>
            <div class="topic-primary-tag">Primary: <strong>${escapeHtml(primaryText)}</strong></div>
          </div>
          <span class="topic-chevron">▼</span>
        </div>
        <div class="topic-group-body">
          <div class="keywords-pill-wrap">
            ${tagsHtml}
          </div>
        </div>
      `;

      // Header click toggles expand/collapse
      const header = card.querySelector('.topic-group-header');
      header.addEventListener('click', () => {
        card.classList.toggle('expanded');
      });

      topicsAccordionList.appendChild(card);
    });
  }

  function formatTopicName(name) {
    if (!name) return 'General Topic';
    return name
      .split(' ')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  // ── Global Helper Functions ────────────────────────────────

  window.copyText = function(text, btn) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      const originalHtml = btn.innerHTML;
      btn.classList.add('copied');
      btn.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <span>Copied!</span>
      `;
      setTimeout(() => {
        btn.classList.remove('copied');
        btn.innerHTML = originalHtml;
      }, 1600);
    }).catch(err => {
      console.warn('Clipboard write failed:', err);
    });
  };

  window.copyTagText = function(text, pill) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      const originalText = pill.textContent;
      pill.style.backgroundColor = '#e6f4ea';
      pill.style.color = '#137333';
      pill.style.borderColor = '#a8dab5';
      pill.textContent = 'Copied!';
      setTimeout(() => {
        pill.style.backgroundColor = '';
        pill.style.color = '';
        pill.style.borderColor = '';
        pill.textContent = originalText;
      }, 1400);
    });
  };

  window.filterRelatedTo = function(keyword) {
    if (!keyword) return;
    // Extract first 2-3 words for useful related filtering
    const words = keyword.split(' ').slice(0, 2).join(' ');
    if (tableFilterInput) {
      tableFilterInput.value = words;
      applyTableFilters();
    }
    const tablePanel = document.querySelector('.table-panel');
    if (tablePanel) {
      tablePanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function escapeJs(str) {
    if (!str) return '';
    return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
  }

  // ── Auto-run initial exploration on first page load ─────────
  if (mainSearchInput && mainSearchInput.value.trim()) {
    executeSearch(mainSearchInput.value.trim());
  }
});
