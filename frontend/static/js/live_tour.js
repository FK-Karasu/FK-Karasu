/* Обучение по странице «Трансляция»: подсвечивает блок пульта и объясняет, что с ним делать.
 * Ничего не нажимает и не меняет — только показывает. Работает и в приложении (APK), и на телефоне.
 */
(() => {
    const STORAGE_KEY = 'liveTourProgress.v1';
    const $ = (selector) => document.querySelector(selector);
    const card = (selector) => () => $(selector)?.closest('.card') || null;

    const STEPS = [
        {
            title: 'Пульт трансляции',
            text: 'Отсюда вы управляете табло поверх видео на YouTube: счёт и время, составы команд, '
                + 'голы и карточки. Табло сразу появляется в OBS у оператора.'
                + '<br><br>Листайте кнопкой <b>«Далее»</b>. Ничего не нажимается и не сохраняется.',
        },
        {
            target: '.preview-box',
            title: 'Так видят зрители',
            text: 'Здесь табло в том виде, в каком оно попадёт в эфир. Зелёный фон — только для примера: '
                + 'в OBS фон прозрачный, и табло ложится поверх видео.',
        },
        {
            target: '.url-row',
            title: 'Ссылка для OBS',
            text: 'Нажмите <b>«Копировать»</b> и отправьте ссылку оператору. В OBS: «Источники» → <b>+</b> → '
                + '<b>Браузер</b> → вставить ссылку.<br><br>Ширину и высоту источника ставят как у трансляции: '
                + '1920×1080, 2560×1440, 3840×2160 или 1080×1920 для вертикального видео. Табло само подстроится.',
            tip: 'Ссылку не публикуйте — по ней видно табло. Если надписи кажутся крупными, в конец ссылки можно '
                + 'добавить ?scale=0.8 (или 1.2 — крупнее).',
        },
        {
            target: card('#logoPrimaryImg'),
            title: 'Логотип в углу',
            text: 'Логотип KFL KIDS всё время висит в правом верхнем углу. Галочка <b>«Показывать логотип»</b> '
                + 'убирает его, если он мешает.',
        },
        {
            target: '#matchPick',
            title: '1. Выберите матч',
            text: 'Нажмите и выберите матч, который сейчас идёт. Команды по алфавиту, есть поиск — '
                + 'достаточно набрать пару букв названия.<br><br>При смене матча время сбрасывается на 00:00.',
        },
        {
            target: '.scenes',
            title: '2. Что показать',
            text: '<b>Встреча команд</b> — перед игрой: логотипы и составы с фото.<br>'
                + '<b>Счёт</b> — во время игры: маленькое табло в левом углу.<br>'
                + '<b>Итог матча</b> — после свистка: счёт и кто забил.<br>'
                + '<b>Скрыть всё</b> — чистое видео, например в перерыве.',
            tip: 'Голы и карточки всплывают на экране только в сцене «Счёт».',
        },
        {
            target: card('#clockText'),
            title: '3. Время матча',
            text: '<b>▶ Старт</b> запускает время, эта же кнопка ставит паузу. <b>±10 с</b> и <b>±1 мин</b> '
                + 'подгоняют время, если начали с опозданием.<br><br>В перерыве нажмите <b>›</b> — начнётся 2 тайм. '
                + 'Если указать длину тайма, второй тайм пойдёт с этой отметки (например, с 20:00).',
        },
        {
            target: '#eventActions',
            title: '4. Голы и карточки',
            text: 'Забили — нажмите <b>«+ Гол»</b> у нужной команды и выберите игрока. Минута подставится сама '
                + 'по времени. Есть отметки <b>пенальти</b> и <b>автогол</b>, а если автор неизвестен — '
                + '<b>«Без автора»</b>.<br><br><b>ЖК</b> и <b>КК</b> — жёлтая и красная карточки, так же.',
            tip: 'Это тот же протокол, что в разделе «Турниры»: счёт, таблица и статистика обновятся сами, '
                + 'второй раз вносить не нужно.',
        },
        {
            target: '#eventsList',
            fallback: '#eventActions',
            title: 'Ошиблись — удалите',
            text: 'Все голы и карточки матча — в этом списке, свежие сверху. Крестик <b>✕</b> удаляет запись; '
                + 'если это гол, счёт уменьшится сам.',
        },
        {
            title: 'Порядок на матч',
            text: '<ol class="lt-steps">'
                + '<li>Выбрать матч</li>'
                + '<li>До начала — <b>«Встреча команд»</b></li>'
                + '<li>Свисток — <b>«Счёт»</b> и <b>▶ Старт</b></li>'
                + '<li>Голы и карточки — кнопками</li>'
                + '<li>Перерыв — пауза и <b>›</b> 2 тайм</li>'
                + '<li>Конец — <b>«Итог матча»</b></li></ol>'
                + 'Урок можно открыть снова кнопкой <b>«Обучение»</b> вверху.',
        },
    ];

    const CSS = `
        .lt-launch {
            display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px;
            border-radius: 999px; border: 1px solid var(--line, #e6e1dc); background: #fff; color: inherit;
            font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap;
        }
        .lt-launch + .live-dot { margin-left: 8px; }
        header.top .lt-launch { margin-left: auto; }
        @media (max-width: 420px) { .lt-launch span { display: none; } .lt-launch { width: 34px; justify-content: center; padding: 0; } }
        .lt-root { position: fixed; inset: 0; z-index: 100; }
        .lt-root[hidden] { display: none; }
        .lt-blocker { position: absolute; inset: 0; }
        .lt-spot {
            position: fixed; border-radius: 14px; pointer-events: none;
            box-shadow: 0 0 0 3px var(--accent, #ff8a00), 0 0 0 9999px rgba(15, 17, 21, .62);
            transition: left .25s, top .25s, width .25s, height .25s;
        }
        .lt-root.no-target .lt-spot { box-shadow: 0 0 0 9999px rgba(15, 17, 21, .62); }
        .lt-tip {
            position: fixed; width: min(380px, calc(100vw - 24px)); padding: 16px 16px 14px;
            border-radius: 16px; background: #fff; color: #1d2026; box-shadow: 0 18px 50px rgba(0, 0, 0, .3);
            font-size: 15px; line-height: 1.45;
        }
        .lt-tip[data-side="center"] { left: 50%; top: 50%; transform: translate(-50%, -50%); }
        .lt-tip[data-side="sheet-bottom"], .lt-tip[data-side="sheet-top"] { left: 12px; right: 12px; width: auto; }
        .lt-tip[data-side="sheet-bottom"] { bottom: calc(12px + env(safe-area-inset-bottom)); }
        .lt-tip[data-side="sheet-top"] { top: calc(12px + env(safe-area-inset-top)); }
        .lt-tip.enter { animation: lt-in .22s ease-out; }
        @keyframes lt-in { from { opacity: 0; transform: translateY(6px); } }
        .lt-tip[data-side="center"].enter { animation: none; }
        .lt-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
        .lt-head small { color: #b35c00; font-weight: 750; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
        .lt-x { margin-left: auto; width: 30px; height: 30px; border: 0; border-radius: 8px; background: #f4f1ee;
            font-size: 18px; line-height: 1; cursor: pointer; color: #747b86; }
        .lt-tip h3 { margin: 0 0 6px; font-size: 18px; }
        .lt-text b { font-weight: 750; }
        .lt-hint { margin-top: 10px; padding: 9px 11px; border-radius: 10px; background: #fff4e6; color: #7a4300; font-size: 13.5px; }
        .lt-steps { margin: 4px 0 10px; padding-left: 22px; }
        .lt-steps li { margin: 3px 0; }
        .lt-bar { height: 4px; margin: 14px 0 12px; border-radius: 4px; background: #f0ece8; overflow: hidden; }
        .lt-bar span { display: block; height: 100%; background: var(--accent, #ff8a00); transition: width .25s; }
        .lt-foot { display: flex; align-items: center; gap: 8px; }
        .lt-foot .count { margin-right: auto; color: #747b86; font-size: 13px; font-weight: 600; }
        .lt-btn { height: 40px; padding: 0 16px; border-radius: 11px; border: 1px solid var(--accent, #ff8a00);
            background: var(--accent, #ff8a00); color: #fff; font: inherit; font-weight: 700; cursor: pointer; }
        .lt-btn.ghost { background: #fff; color: #1d2026; border-color: #e6e1dc; }
        .lt-btn:disabled { opacity: .4; cursor: default; }
        .lt-invite {
            position: fixed; left: 50%; bottom: calc(16px + env(safe-area-inset-bottom)); z-index: 90;
            transform: translateX(-50%); width: min(440px, calc(100vw - 24px));
            display: flex; align-items: center; gap: 10px; padding: 12px 12px 12px 16px; border-radius: 16px;
            background: #1d2026; color: #fff; box-shadow: 0 16px 40px rgba(0, 0, 0, .3); font-size: 14px;
        }
        .lt-invite div { flex: 1; min-width: 0; }
        .lt-invite b { display: block; font-size: 15px; }
        .lt-invite .lt-btn { height: 36px; padding: 0 12px; }
        .lt-invite .later { border: 0; background: none; color: rgba(255, 255, 255, .7); font: inherit; cursor: pointer; padding: 6px; }
    `;

    const state = { index: 0, active: false, target: null, frame: 0 };
    const ui = {};

    function el(tag, className, html) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (html !== undefined) node.innerHTML = html;
        return node;
    }

    function visible(node) {
        return Boolean(node && node.isConnected && node.getClientRects().length && node.offsetHeight > 0);
    }

    function resolve(target) {
        if (!target) return null;
        const node = typeof target === 'function' ? target() : $(target);
        return visible(node) ? node : null;
    }

    function buildUi() {
        if (ui.root) return;
        ui.root = el('div', 'lt-root');
        ui.root.hidden = true;
        ui.blocker = el('div', 'lt-blocker');
        ui.spot = el('div', 'lt-spot');
        ui.tip = el('div', 'lt-tip');
        ui.tip.setAttribute('role', 'dialog');
        ui.root.append(ui.blocker, ui.spot, ui.tip);
        document.body.appendChild(ui.root);
        ui.tip.addEventListener('click', (event) => {
            const action = event.target.closest('[data-lt]')?.dataset.lt;
            if (action === 'next') go(state.index + 1);
            if (action === 'prev') go(state.index - 1);
            if (action === 'close') finish();
        });
        document.addEventListener('keydown', (event) => {
            if (!state.active) return;
            if (event.key === 'Escape') { event.preventDefault(); finish(); }
            if (event.key === 'ArrowRight' || event.key === 'Enter') { event.preventDefault(); go(state.index + 1); }
            if (event.key === 'ArrowLeft') { event.preventDefault(); go(state.index - 1); }
        }, true);
        window.addEventListener('resize', place);
    }

    function go(index) {
        if (index >= STEPS.length) { finish(); return; }
        if (index < 0) return;
        state.index = index;
        const step = STEPS[index];
        const node = resolve(step.target) || resolve(step.fallback);
        state.target = node;
        const last = index === STEPS.length - 1;
        ui.tip.innerHTML = `
            <div class="lt-head"><small>Обучение</small>
                <button type="button" class="lt-x" data-lt="close" aria-label="Закрыть обучение">×</button></div>
            <h3>${step.title}</h3>
            <div class="lt-text">${step.text}</div>
            ${step.tip ? `<div class="lt-hint">💡 ${step.tip}</div>` : ''}
            <div class="lt-bar"><span style="width:${Math.round(((index + 1) / STEPS.length) * 100)}%"></span></div>
            <div class="lt-foot">
                <span class="count">${index + 1} / ${STEPS.length}</span>
                <button type="button" class="lt-btn ghost" data-lt="prev"${index === 0 ? ' disabled' : ''}>Назад</button>
                <button type="button" class="lt-btn" data-lt="next">${last ? 'Готово' : 'Далее'}</button>
            </div>`;
        ui.root.hidden = false;
        ui.root.classList.toggle('no-target', !node);
        if (node) {
            // На телефоне блок поднимаем к верху экрана — подсказка займёт низ и его не закроет.
            const phone = window.innerWidth < 700;
            node.style.scrollMarginTop = phone ? '12px' : '';
            node.scrollIntoView({ block: phone ? 'start' : 'center', behavior: phone ? 'auto' : 'smooth' });
        }
        ui.tip.classList.remove('enter');
        void ui.tip.offsetWidth;
        ui.tip.classList.add('enter');
        ui.tip.querySelector('[data-lt="next"]').focus({ preventScroll: true });
        place();
    }

    function place() {
        if (!state.active) return;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const node = state.target;
        if (!node || !visible(node)) {
            ui.spot.style.cssText = `left:${vw / 2}px;top:${vh / 2}px;width:0;height:0;`;
            ui.tip.style.cssText = '';
            ui.tip.dataset.side = 'center';
            return;
        }
        const pad = 6;
        const r = node.getBoundingClientRect();
        const box = {
            left: Math.max(4, r.left - pad), top: Math.max(4, r.top - pad),
            right: Math.min(vw - 4, r.right + pad), bottom: Math.min(vh - 4, r.bottom + pad),
        };
        ui.spot.style.cssText = `left:${box.left}px;top:${box.top}px;`
            + `width:${Math.max(0, box.right - box.left)}px;height:${Math.max(0, box.bottom - box.top)}px;`;
        if (vw < 700) {
            // На телефоне подсказка внизу; наверх — только если блок в конце страницы и выше не поднялся.
            const tipHeight = ui.tip.offsetHeight + 24;
            const coveredBelow = box.bottom > vh - tipHeight;
            ui.tip.dataset.side = coveredBelow && box.top > tipHeight ? 'sheet-top' : 'sheet-bottom';
            ui.tip.style.cssText = '';
            return;
        }
        const tip = ui.tip.getBoundingClientRect();
        const gap = 14;
        const options = [
            ['right', box.right + gap, box.top, vw - box.right - gap >= tip.width],
            ['left', box.left - gap - tip.width, box.top, box.left - gap >= tip.width],
            ['bottom', box.left, box.bottom + gap, vh - box.bottom - gap >= tip.height],
            ['top', box.left, box.top - gap - tip.height, box.top - gap >= tip.height],
        ];
        const [side, rawX, rawY] = options.find((o) => o[3]) || ['over', vw - tip.width - 16, vh - tip.height - 16];
        ui.tip.dataset.side = side;
        ui.tip.style.cssText = `left:${Math.min(Math.max(12, rawX), vw - tip.width - 12)}px;`
            + `top:${Math.min(Math.max(12, rawY), vh - tip.height - 12)}px;`;
    }

    function loop() {
        if (!state.active) return;
        place();
        state.frame = requestAnimationFrame(loop);
    }

    function start() {
        buildUi();
        hideInvite();
        document.querySelector('.sheet-backdrop')?.remove();
        state.active = true;
        // Запас снизу, чтобы и последние блоки страницы можно было поднять к верху экрана над подсказкой.
        document.body.style.paddingBottom = '70vh';
        state.frame = requestAnimationFrame(loop);
        go(0);
    }

    function finish() {
        if (!state.active) return;
        state.active = false;
        cancelAnimationFrame(state.frame);
        ui.root.hidden = true;
        document.body.style.paddingBottom = '';
        remember();
    }

    function remember() {
        try { localStorage.setItem(STORAGE_KEY, '1'); } catch (error) { /* приватный режим */ }
    }
    function seen() {
        try { return localStorage.getItem(STORAGE_KEY) === '1'; } catch (error) { return true; }
    }

    function hideInvite() {
        ui.invite?.remove();
        ui.invite = null;
    }

    function init() {
        const style = document.createElement('style');
        style.textContent = CSS;
        document.head.appendChild(style);

        const button = el('button', 'lt-launch', '🎓 <span>Обучение</span>');
        button.type = 'button';
        button.title = 'Как пользоваться пультом';
        button.addEventListener('click', start);
        const dot = document.getElementById('liveDot');
        if (dot) dot.before(button); else document.querySelector('header.top')?.appendChild(button);

        if (!seen()) {
            setTimeout(() => {
                if (state.active || seen()) return;
                ui.invite = el('div', 'lt-invite', `
                    <div><b>Впервые здесь?</b>Покажем пульт за 2 минуты.</div>
                    <button type="button" class="lt-btn" data-inv="start">Показать</button>
                    <button type="button" class="later" data-inv="later">Позже</button>`);
                document.body.appendChild(ui.invite);
                ui.invite.addEventListener('click', (event) => {
                    const action = event.target.closest('[data-inv]')?.dataset.inv;
                    if (action === 'start') start();
                    if (action === 'later') { remember(); hideInvite(); }
                });
            }, 1200);
        }
    }

    window.LiveTour = { start };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
