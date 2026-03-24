(function () {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor('#ffffff');
    tg.setBackgroundColor('#f5f7fb');
  }

  window.tgAppInitData = function () {
    if (tg && tg.initData) {
      return String(tg.initData);
    }

    const params = new URLSearchParams(window.location.search);
    return params.get('init_data') || '';
  };

  const initData = window.tgAppInitData();
  const path = window.location.pathname || '';
  if (path.startsWith('/app') && initData) {
    const current = new URL(window.location.href);
    if (!current.searchParams.get('init_data')) {
      current.searchParams.set('init_data', initData);
      window.location.replace(current.toString());
      return;
    }
  }

  window.tgAppUserId = function () {
    if (window.__TGAPP__ && window.__TGAPP__.userId) {
      return Number(window.__TGAPP__.userId);
    }

    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.id) {
      return Number(tg.initDataUnsafe.user.id);
    }

    return null;
  };

  const search = document.getElementById('packSearch');
  const cards = document.querySelectorAll('.pack-card-item');
  if (search && cards.length) {
    search.addEventListener('input', function () {
      const q = search.value.trim().toLowerCase();
      cards.forEach((el) => {
        const s = String(el.dataset.search || '');
        el.classList.toggle('d-none', q && !s.includes(q));
      });
    });
  }
})();
