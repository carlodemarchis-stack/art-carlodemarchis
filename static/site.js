/* Lightbox for every a[data-lightbox] — keyboard, swipe, grouped by the attribute value. */
(function () {
  var box = document.getElementById('lightbox');
  if (!box) return;
  var img = box.querySelector('img'), cap = box.querySelector('figcaption');
  var group = [], idx = 0, startX = 0;

  function show(i) {
    idx = (i + group.length) % group.length;
    var a = group[idx];
    img.src = a.getAttribute('href');
    img.alt = (a.querySelector('img') || {}).alt || '';
    cap.textContent = a.dataset.caption || '';
    box.hidden = false;
    document.body.style.overflow = 'hidden';
    // preload neighbours
    [idx + 1, idx - 1].forEach(function (j) { var n = new Image(); n.src = group[(j + group.length) % group.length].href; });
  }
  function close() { box.hidden = true; document.body.style.overflow = ''; img.src = ''; }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-lightbox]');
    if (!a) return;
    e.preventDefault();
    group = Array.prototype.slice.call(document.querySelectorAll('a[data-lightbox="' + a.dataset.lightbox + '"]'));
    show(group.indexOf(a));
  });
  box.querySelector('.lb-close').addEventListener('click', close);
  box.querySelector('.lb-prev').addEventListener('click', function () { show(idx - 1); });
  box.querySelector('.lb-next').addEventListener('click', function () { show(idx + 1); });
  box.addEventListener('click', function (e) { if (e.target === box) close(); });
  document.addEventListener('keydown', function (e) {
    if (box.hidden) return;
    if (e.key === 'Escape') close();
    if (e.key === 'ArrowRight') show(idx + 1);
    if (e.key === 'ArrowLeft') show(idx - 1);
  });
  box.addEventListener('touchstart', function (e) { startX = e.touches[0].clientX; }, { passive: true });
  box.addEventListener('touchend', function (e) {
    var dx = e.changedTouches[0].clientX - startX;
    if (Math.abs(dx) > 50) show(idx + (dx < 0 ? 1 : -1));
  });
})();

/* "This week" alert bar: shows upcoming events that are on now or start within 7 days, rotating every 5 s. */
(function () {
  var bar = document.getElementById('alert');
  if (!bar) return;
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var limit = new Date(today); limit.setDate(limit.getDate() + 7);
  var items = Array.prototype.filter.call(bar.querySelectorAll('.alert-item'), function (a) {
    var start = new Date(a.dataset.start + 'T00:00:00'), end = new Date((a.dataset.end || a.dataset.start) + 'T00:00:00');
    return !isNaN(start) && end >= today && start <= limit;
  });
  if (!items.length) return;
  bar.hidden = false;
  var i = 0;
  items[0].classList.add('on');
  if (items.length > 1) setInterval(function () {
    items[i].classList.remove('on'); i = (i + 1) % items.length; items[i].classList.add('on');
  }, 5000);
})();
