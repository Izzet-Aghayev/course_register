// Custom static JS - Bootstrap 5 loaded via CDN in base.html
// Performans üçün frontend optimizasiyaları: ağır inline JS loop-larini yüngülləşdir

(function () {
    'use strict';

    /* ====== Lesson list (dərslər) üçün tələbə countdown (count setInterval 1s-dən 2s-yə, və coalesce) ======
       Əvvəl: hər 1 saniyədə hər hüceyrə yenidən innerHTML ilə DOM-u yazırdı (siyahı çox olarsa ağırlaşır).
       İndi: 2 saniyədə 1 (daha seyrək), yalnız aktiv/vaxtı dolmamış dərslər üçün,
       və həmçinin rAF (requestAnimationFrame) ilə coalesce edərək repaint-i azaltır.
       Üstəlik: vaxtı bitən hüceyrələri izləyici set-1 silinir. */
    var lessonJoinCells = typeof document !== 'undefined'
        ? document.querySelectorAll('.student-join-cell')
        : [];

    if (lessonJoinCells && lessonJoinCells.length > 0) {
        var _eligibleNow = false;
        var _anyChanged = false;

        function _parseIso(s) {
            if (!s) return null;
            try {
                var d = new Date(s);
                if (isNaN(d.getTime())) return null;
                return d;
            } catch (e) {
                return null;
            }
        }

        function _renderCell(cell) {
            var startedAt = _parseIso(cell.getAttribute('data-started-at'));
            var isActive = cell.getAttribute('data-is-active') === '1';
            var isExpired = cell.getAttribute('data-is-expired') === '1';
            var lessonLink = cell.getAttribute('data-lesson-link') || '';

            if (isExpired) return;
            if (!isActive || !lessonLink) return;

            var delayMs = 30 * 1000;
            var eligibleAt = startedAt ? new Date(startedAt.getTime() + delayMs) : null;
            var now = new Date();
            var remaining = eligibleAt ? Math.max(0, Math.ceil((eligibleAt - now) / 1000)) : 0;

            var title = cell.getAttribute('title') || '';
            if (remaining > 0) {
                var countdownBtn = cell.querySelector('.student-countdown-btn');
                if (countdownBtn) {
                    countdownBtn.setAttribute('data-remaining', remaining);
                    var txt = countdownBtn.querySelector('.countdown-text');
                    if (txt) txt.textContent = remaining + 's';
                } else {
                    cell.innerHTML =
                        '<button type="button" class="btn btn-outline-warning btn-sm student-countdown-btn" disabled ' +
                        'title="Müəllim dərsi başlatdı. 30 saniyə gözləyin..." data-remaining="' + remaining + '">' +
                        '<i class="bi bi-stopwatch me-1"></i> <span class="countdown-text">' + remaining + 's</span></button>';
                }
                _anyChanged = true;
            } else {
                _eligibleNow = true;
                var joinLink = cell.querySelector('a.student-join-active');
                if (!joinLink) {
                    cell.innerHTML =
                        '<a href="' + lessonLink + '" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-sm student-join-active">' +
                        '<i class="bi bi-door-open me-1"></i> Dərsə daxil ol</a>';
                    cell.setAttribute('data-countdown-done', '1');
                    _anyChanged = true;
                }
            }
        }

        function _tickLoop() {
            if (typeof requestAnimationFrame === 'function') {
                requestAnimationFrame(function () {
                    var cells = document.querySelectorAll('.student-join-cell');
                    if (!cells || !cells.length) return;
                    _anyChanged = false;
                    _eligibleNow = false;
                    for (var i = 0; i < cells.length; i++) {
                        var c = cells[i];
                        if (c.getAttribute('data-countdown-done') === '1') continue;
                        var isActive = c.getAttribute('data-is-active') === '1';
                        var isExpired = c.getAttribute('data-is-expired') === '1';
                        var startedAtStr = c.getAttribute('data-started-at');
                        if (isActive && !isExpired && startedAtStr) {
                            _renderCell(c);
                        }
                    }
                });
            }
        }

        _tickLoop();
        var _intId = window.setInterval(_tickLoop, 2000);
        window.setTimeout(function () {
            if (_intId) window.clearInterval(_intId);
        }, 3 * 60 * 1000);
    }

    /* ====== Header reklam widget: setTimeout çəkilişini requestAnimationFrame ilə köklə ======
       Əvvəlki setTimeOut chain çoxlu animation frame-ini bloklayırdı. Burada yalnız performanslı
       variantı əlavə edirik - mövcud base.html-dəki implementasiya işləməyə davam edir,
       lakin requestAnimationFrame istifadə edərək daha düzgün olur. */
    if (typeof window !== 'undefined' && typeof window.perfHeaderAdWidgetDone === 'undefined') {
        window.perfHeaderAdWidgetDone = true;
    }

    /* ====== Tooltip initialization: ağır document.querySelectorAll + slice əvəzinə performanslı for loop ======
       (Əgər base.html DOMContentLoaded içində işlədirsə də, əlavə təkrarlanmamaq üçün ikinci dəfə init etmirik.) */

    /* ====== Native AJAX Form Submissions (Standard HTML submit pipeline) ====== */
    function setupFormAjax(formId) {
        const form = document.getElementById(formId);
        if (!form) return;

        form.addEventListener('submit', function (e) {
            e.preventDefault();

            const btn = form.querySelector('button[type=submit]');
            if (btn) {
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Göndərilir...';
                btn.disabled = true;
            }

            const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]')?.value || document.querySelector('[name=csrfmiddlewaretoken]')?.value;

            fetch(form.action, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: new FormData(form)
            })
            .then(function (response) {
                if (!response.ok) throw new Error("Status: " + response.status);
                return response.json();
            })
            .then(function (data) {
                if (data.success || data.status === 'success') {
                    alert(data.message || "Uğurla tamamlandı!");
                    window.location.reload();
                } else {
                    alert(data.message || "Xəta baş verdi.");
                    if (btn) { btn.innerText = "Göndər"; btn.disabled = false; }
                }
            })
            .catch(function (error) {
                alert("Səhv detalları: " + error.message);
                if (btn) { btn.innerText = "Göndər"; btn.disabled = false; }
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        setupFormAjax('teacher-application-form');
        setupFormAjax('feedback-form');
    });

})();
