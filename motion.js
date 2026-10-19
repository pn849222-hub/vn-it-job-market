// Scroll progress for the preview pages. Every [data-scroll] element gets --p, from 0 to 1:
//   track  progress through a tall section whose child is position: sticky
//   view   progress while the element crosses the viewport
//   leave  progress while the element scrolls off the top (the hero)
// The page itself gets --page for the progress bar; [data-step] children get .on once reached. [data-rail] sections get --travel, the
// distance their horizontal rail has to move. With reduced motion every --p is 1, so the CSS
// shows each element in its finished state and nothing moves.
(function () {
  var root = document.documentElement;
  var els = Array.prototype.slice.call(document.querySelectorAll('[data-scroll]'));
  var rails = Array.prototype.slice.call(document.querySelectorAll('[data-rail]'));
  var still = window.matchMedia('(prefers-reduced-motion: reduce)');
  var queued = false;

  function clamp(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

  function measure() {
    queued = false;
    var vh = window.innerHeight;
    rails.forEach(function (section) {
      var rail = section.querySelector('.rail');
      section.style.setProperty('--travel', Math.max(0, rail.scrollWidth - rail.clientWidth) + 'px');
    });
    els.forEach(function (el) {
      var p = 1;
      if (!still.matches) {
        var r = el.getBoundingClientRect(), mode = el.getAttribute('data-scroll');
        if (mode === 'track') p = -r.top / Math.max(1, r.height - vh);
        else if (mode === 'leave') p = -r.top / Math.max(1, r.height);
        else p = (vh - r.top) / (vh + r.height);
      }
      el.style.setProperty('--p', clamp(p).toFixed(4));
      // [data-step] children light up once the section's progress reaches their value.
      Array.prototype.forEach.call(el.querySelectorAll('[data-step]'), function (step) {
        step.classList.toggle('on', p >= parseFloat(step.getAttribute('data-step')) - 0.001);
      });
    });
    root.style.setProperty('--page', clamp(window.scrollY / Math.max(1, root.scrollHeight - vh)).toFixed(4));
  }

  function queue() { if (!queued) { queued = true; window.requestAnimationFrame(measure); } }

  // Keyboard users: when focus lands in a panel of a sideways rail, scroll the page to the
  // point where that panel has slid into view, so the focused link is never off-screen.
  rails.forEach(function (section) {
    section.addEventListener('focusin', function (event) {
      if (still.matches) return;
      var rail = section.querySelector('.rail');
      var panel = event.target.closest('.panel');
      var travel = rail.scrollWidth - rail.clientWidth;
      if (!panel || travel <= 0 || getComputedStyle(rail).flexDirection !== 'row') return;
      var p = clamp((panel.offsetLeft - rail.offsetLeft) / travel);
      var top = section.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: top + p * (section.offsetHeight - window.innerHeight), behavior: 'auto' });
    });
  });
  window.addEventListener('scroll', queue, { passive: true });
  window.addEventListener('resize', queue);
  if (still.addEventListener) still.addEventListener('change', queue);
  root.classList.add('js-motion');
  measure();
})();
